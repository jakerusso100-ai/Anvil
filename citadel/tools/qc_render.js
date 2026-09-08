#!/usr/bin/env node
/* Headless QC for the Citadel viewer.
 *
 *   node citadel/tools/qc_render.js [--out citadel/qc] [--no-export]
 *
 * Opens citadel/viewer.html in headless Chromium (software WebGL), waits for
 * the scene to build, then:
 *   1. screenshots every named view in spec.views (plus a wireframe and an
 *      opaque-glass variant of the show angle) into --out
 *   2. exports citadel/exports/citadel.glb and citadel.obj through the page's
 *      own GLTFExporter / OBJExporter, so the files are exactly the scene that
 *      is rendered
 *   3. prints the scene stats and the model's bounding box in metres
 *
 * Playwright is resolved from the global install if it is not a local dep.
 */
const fs = require('fs');
const path = require('path');

function requirePlaywright() {
  try { return require('playwright'); } catch (_) { /* fall through */ }
  const candidates = ['/opt/node22/lib/node_modules/playwright', '/usr/lib/node_modules/playwright', '/usr/local/lib/node_modules/playwright'];
  for (const c of candidates) { if (fs.existsSync(c)) return require(c); }
  throw new Error('playwright not found: npm i -g playwright');
}

(async () => {
  const args = process.argv.slice(2);
  const outDir = path.resolve(args.includes('--out') ? args[args.indexOf('--out') + 1] : path.join(__dirname, '..', 'qc'));
  const doExport = !args.includes('--no-export');
  const root = path.resolve(__dirname, '..');
  fs.mkdirSync(outDir, { recursive: true });

  const { chromium } = requirePlaywright();
  const browser = await chromium.launch({
    args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist', '--disable-gpu-sandbox'],
  });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: 1 });
  page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') console.log('[page]', m.type(), m.text()); });
  page.on('pageerror', (e) => console.log('[pageerror]', e.message));

  await page.goto('file://' + path.join(root, 'viewer.html'));
  await page.waitForFunction(() => window.__citadel && window.__citadel.ready, null, { timeout: 120000 });
  const info = await page.evaluate(() => window.__citadel.info());
  console.log('scene:', JSON.stringify(info, null, 1));

  const views = await page.evaluate(() => Object.keys(window.__citadel.views));
  const shots = [];
  for (const v of views) {
    await page.evaluate((name) => window.__citadel.setView(name), v);
    await page.evaluate(() => window.__citadel.renderNow());
    await page.waitForTimeout(150);
    const file = path.join(outDir, `view_${v}.png`);
    await page.screenshot({ path: file });
    shots.push(file);
  }
  // variants of the show angle
  await page.evaluate(() => { window.__citadel.setView('show_angle'); window.__citadel.setOption('wireframe', true); window.__citadel.renderNow(); });
  await page.screenshot({ path: path.join(outDir, 'view_show_angle_wireframe.png') });
  await page.evaluate(() => { window.__citadel.setOption('wireframe', false); window.__citadel.setOption('glass', 1); window.__citadel.setOption('labels', true); window.__citadel.renderNow(); });
  await page.screenshot({ path: path.join(outDir, 'view_show_angle_opaque_labels.png') });
  await page.evaluate(() => { window.__citadel.setOption('glass', null); window.__citadel.setOption('labels', false); });
  // close-ups
  await page.evaluate(() => window.__citadel.setCamera({ azimuth_deg: 122, elevation_deg: 12, distance: 26000, target: [0, 500, 0] }));
  await page.evaluate(() => window.__citadel.renderNow());
  await page.screenshot({ path: path.join(outDir, 'closeup_hub_dome.png') });
  await page.evaluate(() => window.__citadel.setCamera({ azimuth_deg: 60, elevation_deg: 10, distance: 22000, target: [4000, -1200, 9000] }));
  await page.evaluate(() => window.__citadel.renderNow());
  await page.screenshot({ path: path.join(outDir, 'closeup_pod_bridge.png') });
  await page.evaluate(() => window.__citadel.setCamera({ azimuth_deg: 140, elevation_deg: -14, distance: 34000, target: [0, -9000, 0] }));
  await page.evaluate(() => window.__citadel.renderNow());
  await page.screenshot({ path: path.join(outDir, 'closeup_understructure.png') });

  if (doExport) {
    const expDir = path.join(root, 'exports');
    fs.mkdirSync(expDir, { recursive: true });
    const glbB64 = await page.evaluate(() => window.__citadel.exportGLB().then((buf) => {
      let s = ''; const b = new Uint8Array(buf);
      for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode.apply(null, b.subarray(i, i + 0x8000));
      return btoa(s);
    }));
    fs.writeFileSync(path.join(expDir, 'citadel.glb'), Buffer.from(glbB64, 'base64'));
    const obj = await page.evaluate(() => window.__citadel.exportOBJ());
    fs.writeFileSync(path.join(expDir, 'citadel.obj'), obj); // zip this before committing (16 MB raw)
    for (const f of ['citadel.glb', 'citadel.obj']) {
      console.log(`export: ${f} ${(fs.statSync(path.join(expDir, f)).size / 1048576).toFixed(2)} MB`);
    }
  }
  await browser.close();
  console.log('screenshots:', shots.length + 5, 'in', outDir);
})().catch((e) => { console.error(e); process.exit(1); });
