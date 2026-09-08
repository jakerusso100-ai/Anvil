/* Citadel of Ricks — procedural geometry builder.
 *
 * buildCitadel(THREE, spec) -> { root, parts, stats }
 *   root  : THREE.Group, 1 unit = 1 metre, +Y up, origin = hub deck centre (top surface)
 *   parts : [{ id, name, group, qty, dims }] — one entry per layer, matching the
 *           parts list on schematic sheet 4
 *
 * Every dimension comes from spec.json; nothing is hard-coded here except the
 * mesh tessellation and a seeded random generator for the skyline so the city
 * is identical on every run.
 */
(function (global) {
  'use strict';

  function mulberry32(seed) {
    let a = seed >>> 0;
    return function () {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  const DEG = Math.PI / 180;

  function buildCitadel(THREE, spec) {
    const H = spec.hub, P = spec.pods, B = spec.bridges, U = spec.understructure, L = spec.legs;
    const M = {};
    for (const [k, m] of Object.entries(spec.materials)) {
      if (k === 'glass') {
        M[k] = new THREE.MeshPhysicalMaterial({
          color: m.color, transparent: true, opacity: m.opacity, roughness: m.roughness,
          metalness: 0, side: THREE.DoubleSide, depthWrite: false, envMapIntensity: 0.6,
          name: k,
        });
      } else {
        const opts = { color: m.color, roughness: m.roughness ?? 0.6, metalness: m.metalness ?? 0.4, name: k };
        if (m.emissive) { opts.emissive = m.emissive; opts.emissiveIntensity = m.emissiveIntensity ?? 1; }
        M[k] = new THREE.MeshStandardMaterial(opts);
      }
    }

    // Shared unit geometries (scaled per mesh) keep the GLB small.
    const G = {
      box: new THREE.BoxGeometry(1, 1, 1),
      cyl: new THREE.CylinderGeometry(1, 1, 1, 24),
      sphere: new THREE.SphereGeometry(1, 24, 16),
    };

    const root = new THREE.Group();
    root.name = 'Citadel of Ricks';
    const parts = [];
    const stats = { meshes: 0, triangles: 0 };

    function layer(id, name, qty, dims) {
      const g = new THREE.Group();
      g.name = `${id} ${name}`;
      g.userData = { id, name, qty, dims };
      root.add(g);
      parts.push({ id, name, group: g, qty, dims });
      return g;
    }
    function mesh(geo, mat, parent, name) {
      const m = new THREE.Mesh(geo, mat);
      if (name) m.name = name;
      parent.add(m);
      stats.meshes++;
      const idx = geo.index ? geo.index.count : geo.attributes.position.count;
      stats.triangles += Math.round(idx / 3);
      return m;
    }
    function box(parent, mat, w, h, d, x, y, z, name) {
      const m = mesh(G.box, mat, parent, name);
      m.scale.set(w, h, d); m.position.set(x, y, z);
      return m;
    }
    function cylY(parent, mat, rTop, rBot, h, x, yCenter, z, seg, name) {
      // tapered cylinders get their own geometry; straight ones share G.cyl
      let m;
      if (rTop === rBot && (!seg || seg === 24)) {
        m = mesh(G.cyl, mat, parent, name);
        m.scale.set(rTop, h, rTop);
      } else {
        m = mesh(new THREE.CylinderGeometry(rTop, rBot, h, seg || 24), mat, parent, name);
      }
      m.position.set(x, yCenter, z);
      return m;
    }
    function sphere(parent, mat, r, x, y, z, name) {
      const m = mesh(G.sphere, mat, parent, name);
      m.scale.set(r, r, r); m.position.set(x, y, z);
      return m;
    }
    function tubeBetween(parent, mat, a, b, rA, rB, name) {
      const dir = new THREE.Vector3().subVectors(b, a);
      const len = dir.length();
      const geo = new THREE.CylinderGeometry(rB, rA, len, 16);
      const m = mesh(geo, mat, parent, name);
      m.position.copy(a).addScaledVector(dir, 0.5);
      m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize());
      return m;
    }
    function disc(parent, r, h, yTop, sideMat, topMat, seg, name) {
      const geo = new THREE.CylinderGeometry(r, r, h, seg || 128);
      const m = mesh(geo, [sideMat, topMat, sideMat], parent, name);
      m.position.y = yTop - h / 2;
      return m;
    }
    function ellipsoidDome(parent, r, height, seg, name) {
      const geo = new THREE.SphereGeometry(r, seg, Math.round(seg / 2), 0, Math.PI * 2, 0, Math.PI / 2);
      const m = mesh(geo, M.glass, parent, name);
      m.scale.y = height / r;
      m.renderOrder = 10;
      return m;
    }

    // ------------------------------------------------------------------ city
    function city(parent, c, seed, domeR, domeH, offsetX, offsetZ, label) {
      const rnd = mulberry32(seed);
      const towers = [];
      let tries = 0;
      while (towers.length < c.tower_count && tries < c.tower_count * 40) {
        tries++;
        const r = Math.sqrt(rnd()) * c.max_radius;
        const a = rnd() * Math.PI * 2;
        const x = r * Math.cos(a), z = r * Math.sin(a);
        if (r < c.keepout_radius) continue;
        const fp = c.footprint_min + rnd() * (c.footprint_max - c.footprint_min);
        // clearance from other towers
        if (towers.some(t => Math.hypot(t.x - x, t.z - z) < (t.fp + fp) * 0.75)) continue;
        // taller toward the centre, never through the glass
        const centreBias = 1 - r / c.max_radius;
        let h = c.height_min + (c.height_max - c.height_min) * Math.pow(rnd(), 1.6) * (0.35 + 0.65 * centreBias);
        const domeLimit = domeH * Math.sqrt(Math.max(0, 1 - Math.pow((r + fp * 0.7) / domeR, 2))) - 120;
        h = Math.min(h, domeLimit);
        if (h < c.height_min * 0.6) continue;
        towers.push({ x, z, fp, h, round: rnd() < 0.22, step: rnd() < 0.35 });
      }
      towers.forEach((t, i) => {
        const gx = offsetX + t.x, gz = offsetZ + t.z;
        if (t.round) {
          const m = cylY(parent, M.city, t.fp * 0.5, t.fp * 0.55, t.h, gx, t.h / 2, gz, 20, `${label} tower ${i + 1}`);
          m.rotation.y = i;
        } else {
          box(parent, M.city, t.fp, t.h, t.fp * (0.7 + 0.5 * ((i * 7) % 5) / 5), gx, t.h / 2, gz, `${label} tower ${i + 1}`);
        }
        if (t.step) box(parent, M.city, t.fp * 0.6, t.h * 0.22, t.fp * 0.6, gx, t.h + t.h * 0.11, gz);
        // lit crown + lit window band near the base
        box(parent, M.city_glow, t.fp * 0.5, 30, t.fp * 0.5, gx, t.h + (t.step ? t.h * 0.22 : 0) + 15, gz);
        box(parent, M.city_glow, t.fp * 1.04, t.h * 0.06, t.fp * 1.04, gx, t.h * 0.5, gz);
      });
      // low-rise blocks fill the gaps
      const rnd2 = mulberry32(seed + 99);
      for (let i = 0; i < c.lowrise_count; i++) {
        const r = Math.sqrt(rnd2()) * c.max_radius;
        const a = rnd2() * Math.PI * 2;
        const x = r * Math.cos(a), z = r * Math.sin(a);
        if (r < c.keepout_radius) continue;
        const w = 120 + rnd2() * 220, d = 120 + rnd2() * 220;
        const h = c.lowrise_height_min + rnd2() * (c.lowrise_height_max - c.lowrise_height_min);
        const m = box(parent, M.city, w, h, d, offsetX + x, h / 2, offsetZ + z);
        m.rotation.y = rnd2() * Math.PI;
      }
      return towers.length;
    }

    // ------------------------------------------------------------------- hub
    const d = H.deck;
    const gDeck = layer('H-01', 'Hub deck', 1, `Ø ${2 * d.radius} × ${d.thickness} m`);
    disc(gDeck, d.radius, d.thickness, d.top_y, M.hull, M.hull_light, 160, 'hub deck');
    // deck edge panelling: shallow recesses around the side
    for (let i = 0; i < 40; i++) {
      const a = (i / 40) * Math.PI * 2;
      const m = box(gDeck, M.trim, 700, 260, 60, Math.cos(a) * (d.radius + 5), -d.thickness * 0.78, Math.sin(a) * (d.radius + 5));
      m.rotation.y = -a;
    }

    const rb = H.deck_rim_band, lip = H.deck_lip;
    const gRim = layer('H-02', 'Deck rim band + lip', 1, `Ø ${2 * rb.radius} × ${rb.height} m; lip Ø ${2 * lip.radius}`);
    disc(gRim, rb.radius, rb.height, rb.top_y, M.hull, M.hull_light, 160, 'rim band');
    disc(gRim, lip.radius, lip.height, lip.top_y, M.hull_light, M.hull_light, 160, 'deck lip');
    // orange light band
    const band = mesh(new THREE.CylinderGeometry(rb.radius + 12, rb.radius + 12, 150, 160, 1, true), M.rim_light, gRim, 'rim light band');
    band.position.y = rb.top_y - rb.height * 0.62;

    const hb = H.hangar_bays;
    const gHang = layer('H-03', 'Hangar bays', hb.count, `${hb.width} × ${hb.height} × ${hb.depth} m`);
    for (let i = 0; i < hb.count; i++) {
      const a = (i / hb.count) * Math.PI * 2 + 22.5 * DEG;
      const rr = rb.radius - hb.depth / 2 + 40;
      const m = box(gHang, M.trim, hb.depth, hb.height, hb.width, Math.cos(a) * rr, hb.y, Math.sin(a) * rr, `hangar bay ${i + 1}`);
      m.rotation.y = -a;
      const glow = box(gHang, M.rim_light, 40, hb.height * 0.7, hb.width * 0.92, Math.cos(a) * (rb.radius - hb.depth + 60), hb.y, Math.sin(a) * (rb.radius - hb.depth + 60));
      glow.rotation.y = -a;
    }

    const dm = H.dome;
    const gDome = layer('H-04', 'Main dome (glass)', 1, `Ø ${2 * dm.base_radius} × h ${dm.height} m`);
    ellipsoidDome(gDome, dm.base_radius, dm.height, dm.segments, 'main dome');

    const gCollar = layer('H-05', 'Dome collar + ribs', 1, `torus R ${H.dome_collar.ring_radius}; ${H.dome_ribs.count} ribs`);
    const collar = mesh(new THREE.TorusGeometry(H.dome_collar.ring_radius, H.dome_collar.tube_radius, 16, 160), M.hull_light, gCollar, 'dome collar');
    collar.rotation.x = Math.PI / 2; collar.position.y = H.dome_collar.y;
    for (let i = 0; i < H.dome_ribs.count; i++) {
      const rib = mesh(new THREE.TorusGeometry(dm.base_radius, H.dome_ribs.tube_radius, 8, 48, Math.PI), M.hull_light, gCollar, `dome rib ${i + 1}`);
      rib.rotation.y = (i / H.dome_ribs.count) * Math.PI * 2;
      rib.scale.y = dm.height / dm.base_radius;
    }
    // horizontal dome hoops (two) for the panelled-glass look
    for (const f of [0.45, 0.78]) {
      const y = dm.height * f;
      const r = dm.base_radius * Math.sqrt(1 - f * f);
      const hoop = mesh(new THREE.TorusGeometry(r, H.dome_ribs.tube_radius * 0.8, 8, 128), M.hull_light, gCollar, 'dome hoop');
      hoop.rotation.x = Math.PI / 2; hoop.position.y = y;
    }

    const ct = H.council_tower;
    const gCouncil = layer('H-06', 'Council spire', 1, `Ø ${2 * ct.radius_base} → ${2 * ct.radius_top}, h ${ct.height + ct.crown_height} m`);
    cylY(gCouncil, M.city, ct.radius_top, ct.radius_base, ct.height, 0, ct.height / 2, 0, 8, 'council spire');
    cylY(gCouncil, M.city_glow, 0, ct.radius_top, ct.crown_height, 0, ct.height + ct.crown_height / 2, 0, 8, 'council crown');
    for (const f of [0.3, 0.55, 0.8]) {
      const r = ct.radius_base + (ct.radius_top - ct.radius_base) * f;
      cylY(gCouncil, M.city_glow, r + 25, r + 25, 40, 0, ct.height * f, 0, 8);
    }
    // plaza ring around the spire
    disc(gCouncil, ct.radius_base * 1.35, 40, 40, M.hull_light, M.hull_light, 48, 'council plaza');

    const gCity = layer('H-07', 'Hub city towers', H.city.tower_count, `${H.city.height_min}–${H.city.height_max} m tall`);
    const nHub = city(gCity, H.city, H.city.seed, dm.base_radius, dm.height, 0, 0, 'hub');
    parts[parts.length - 1].qty = nHub;
    // H-08 low-rise blocks are generated inside city() into the same layer; keep the schematic ID visible:
    layer('H-08', 'Hub low-rise blocks', H.city.lowrise_count, `${H.city.lowrise_height_min}–${H.city.lowrise_height_max} m tall (in H-07 group)`);

    const an = H.antenna;
    const gAnt = layer('H-09', 'Antenna mast', 1, `h ${an.height} m, Ø ${2 * an.radius_base} → ${2 * an.radius_top}`);
    cylY(gAnt, M.hull_dark, an.radius_top, an.radius_base, an.height, 0, an.base_y + an.height / 2, 0, 12, 'antenna mast');
    // base mount on the dome apex
    cylY(gAnt, M.hull_light, an.radius_base * 2.2, an.radius_base * 3, 120, 0, an.base_y + 60, 0, 16, 'antenna base');
    for (const rg of an.rings) {
      const t = mesh(new THREE.TorusGeometry(rg.radius, 22, 8, 32), M.hull_light, gAnt, 'antenna ring');
      t.rotation.x = Math.PI / 2; t.position.y = an.base_y + an.height * rg.y_frac;
      for (let k = 0; k < 4; k++) {
        const s = box(gAnt, M.hull_dark, rg.radius, 14, 14, Math.cos(k * Math.PI / 2) * rg.radius / 2, an.base_y + an.height * rg.y_frac, Math.sin(k * Math.PI / 2) * rg.radius / 2);
        s.rotation.y = -k * Math.PI / 2;
      }
    }
    // dish: shallow paraboloid facing up-and-out
    const dishPts = [];
    for (let i = 0; i <= 10; i++) { const u = i / 10; dishPts.push(new THREE.Vector2(u * an.dish.radius, u * u * an.dish.depth)); }
    const dish = mesh(new THREE.LatheGeometry(dishPts, 32), M.hull_light, gAnt, 'antenna dish');
    dish.material = new THREE.MeshStandardMaterial({ color: spec.materials.hull_light.color, side: THREE.DoubleSide, roughness: 0.5, metalness: 0.5 });
    dish.position.set(an.dish.radius * 0.6, an.base_y + an.height * an.dish.y_frac, 0);
    dish.rotation.z = -35 * DEG;
    sphere(gAnt, M.beacon, an.beacon_radius, 0, an.base_y + an.height, 0, 'antenna beacon');

    // ------------------------------------------------------------------ pods
    const pd = P.deck, prb = P.deck_rim_band, pdm = P.dome, pu = P.understructure;
    const gPodDeck = layer('P-01', 'Pod decks', P.count, `Ø ${2 * pd.radius} × ${pd.thickness} m`);
    const gPodDome = layer('P-02', 'Pod domes (glass)', P.count, `Ø ${2 * pdm.base_radius} × h ${pdm.height} m`);
    const gPodCity = layer('P-03', 'Pod cities', P.count, `${P.city.tower_count} towers each`);
    const gPodUnder = layer('P-04', 'Pod understructure', P.count, `core R ${pu.core_radius}, spike h ${pu.spike.height} m`);
    P.azimuths_deg.forEach((azDeg, i) => {
      const a = azDeg * DEG;
      const cx = Math.cos(a) * P.center_distance, cz = Math.sin(a) * P.center_distance;
      const sub = new THREE.Group(); sub.name = `pod ${i + 1} deck`; sub.position.set(cx, 0, cz); gPodDeck.add(sub);
      disc(sub, pd.radius, pd.thickness, 0, M.hull, M.hull_light, 96, `pod ${i + 1} deck`);
      disc(sub, prb.radius, prb.height, prb.top_y, M.hull, M.hull_light, 96, `pod ${i + 1} rim`);
      const pb = mesh(new THREE.CylinderGeometry(prb.radius + 8, prb.radius + 8, 90, 96, 1, true), M.rim_light, sub, 'pod rim light');
      pb.position.y = prb.top_y - prb.height * 0.6;
      const cl = mesh(new THREE.TorusGeometry(P.dome_collar.ring_radius, P.dome_collar.tube_radius, 12, 96), M.hull_light, sub, 'pod collar');
      cl.rotation.x = Math.PI / 2; cl.position.y = P.dome_collar.y;
      for (let k = 0; k < 8; k++) {
        const rib = mesh(new THREE.TorusGeometry(pdm.base_radius, 36, 6, 32, Math.PI), M.hull_light, sub, 'pod rib');
        rib.rotation.y = (k / 8) * Math.PI * 2; rib.scale.y = pdm.height / pdm.base_radius;
      }
      const domeSub = new THREE.Group(); domeSub.position.set(cx, 0, cz); gPodDome.add(domeSub);
      ellipsoidDome(domeSub, pdm.base_radius, pdm.height, pdm.segments, `pod ${i + 1} dome`);
      city(gPodCity, P.city, P.city.seed_base + i * 17, pdm.base_radius, pdm.height, cx, cz, `pod ${i + 1}`);
      const us = new THREE.Group(); us.position.set(cx, 0, cz); gPodUnder.add(us);
      cylY(us, M.hull_dark, pu.core_radius, pu.core_radius, pu.core_height, 0, -pd.thickness - pu.core_height / 2, 0, 48, 'pod core');
      for (const pl of pu.plates) disc(us, pl.radius, pl.thickness, pl.top_y, M.hull_dark, M.hull, 64, 'pod plate');
      cylY(us, M.hull_dark, 0, pu.spike.radius, pu.spike.height, 0, pu.spike.top_y - pu.spike.height / 2, 0, 24, 'pod spike');
      for (let k = 0; k < 6; k++) {
        const b = (k / 6) * Math.PI * 2;
        cylY(us, M.trim, 60, 60, pu.core_height + 500, Math.cos(b) * (pu.core_radius + 80), -pd.thickness - pu.core_height / 2 - 250, Math.sin(b) * (pu.core_radius + 80), 8);
      }
    });

    // --------------------------------------------------------------- bridges
    const bt = B.tube, bc = B.causeway;
    const x1 = d.radius, x2 = P.center_distance - pd.radius;
    const span = x2 - x1;
    const gBrTube = layer('B-01', 'Bridge tubes (transit)', B.count, `Ø ${2 * bt.radius_hub} → ${2 * bt.radius_pod}, span ${span} m`);
    const gBrDeck = layer('B-02', 'Bridge causeways + rails', B.count, `${bc.width} wide × ${bc.thickness} m`);
    const gBrStrut = layer('B-03', 'Bridge struts', B.count * B.struts.count, `Ø ${2 * B.struts.radius}`);
    P.azimuths_deg.forEach((azDeg, i) => {
      const a = azDeg * DEG;
      const mk = (parent) => { const g = new THREE.Group(); g.rotation.y = -a; parent.add(g); return g; };
      const gt = mk(gBrTube), gd = mk(gBrDeck), gs = mk(gBrStrut);
      // tube runs along local +X from x1-300 (inside hub) to x2+300 (inside pod)
      const tube = mesh(new THREE.CylinderGeometry(bt.radius_pod, bt.radius_hub, span + 600, 24), M.bridge_tube, gt, `bridge ${i + 1} tube`);
      tube.rotation.z = -Math.PI / 2; tube.position.set((x1 + x2) / 2, bt.y, 0);
      for (let k = 0; k < bt.rib_count; k++) {
        const u = (k + 0.5) / bt.rib_count;
        const r = bt.radius_hub + (bt.radius_pod - bt.radius_hub) * u;
        const rib = mesh(new THREE.TorusGeometry(r + 40, bt.rib_tube_radius, 8, 24), M.hull_dark, gt, 'bridge rib');
        rib.rotation.y = Math.PI / 2; rib.position.set(x1 + span * u, bt.y, 0);
      }
      // causeway
      box(gd, M.hull_light, span + 400, bc.thickness, bc.width, (x1 + x2) / 2, bc.y - bc.thickness / 2, 0, `bridge ${i + 1} causeway`);
      for (const s of [-1, 1]) {
        box(gd, M.trim, span + 400, B.rails.height, B.rails.width, (x1 + x2) / 2, bc.y + B.rails.height / 2, s * (bc.width / 2 - B.rails.width / 2));
        // lit edge strip
        box(gd, M.rim_light, span + 400, 30, 30, (x1 + x2) / 2, bc.y + B.rails.height + 15, s * (bc.width / 2 - B.rails.width / 2));
      }
      // pillars between causeway and tube
      for (let k = 0; k < 5; k++) {
        const u = (k + 0.5) / 5;
        box(gd, M.hull_dark, 120, -bt.y, 120, x1 + span * u, bt.y / 2, 0);
      }
      // struts: V-brace from under the hub rim to the pod core
      for (let k = 0; k < B.struts.count; k++) {
        const s = k === 0 ? -1 : 1;
        const A = new THREE.Vector3(x1 - 100, -d.thickness + 100, s * B.struts.spread / 2);
        const Bv = new THREE.Vector3(x2 + pd.radius - pu.core_radius + 100, -pd.thickness - pu.core_height * 0.5, s * 200);
        tubeBetween(gs, M.hull_dark, A, Bv, B.struts.radius, B.struts.radius, `bridge ${i + 1} strut ${k + 1}`);
      }
    });

    // --------------------------------------------------------- understructure
    const uc = U.core;
    const gCore = layer('U-01', 'Understructure core', 1, `Ø ${2 * uc.radius} × ${uc.height} m`);
    cylY(gCore, M.hull_dark, uc.radius, uc.radius, uc.height, 0, uc.top_y - uc.height / 2, 0, 96, 'core');
    // vertical greebles on the core
    for (let k = 0; k < 24; k++) {
      const b = (k / 24) * Math.PI * 2;
      const m = box(gCore, M.trim, 90, uc.height * 0.9, 260, Math.cos(b) * (uc.radius + 30), uc.top_y - uc.height / 2, Math.sin(b) * (uc.radius + 30));
      m.rotation.y = -b;
    }
    const gPlates = layer('U-02', 'Metallic plates', U.plates.length, U.plates.map(p => `Ø ${2 * p.radius}`).join(' / '));
    U.plates.forEach((pl, i) => {
      disc(gPlates, pl.radius, pl.thickness, pl.top_y, M.hull_dark, M.hull, 128, `plate ${i + 1}`);
      // edge lip and underside light seam
      const seam = mesh(new THREE.CylinderGeometry(pl.radius + 6, pl.radius + 6, 40, 128, 1, true), M.rim_light, gPlates, 'plate seam');
      seam.position.y = pl.top_y - pl.thickness * 0.5;
      for (let k = 0; k < 16; k++) {
        const b = (k / 16) * Math.PI * 2 + i * 0.13;
        const m = box(gPlates, M.hull, 360, pl.thickness + 90, 220, Math.cos(b) * (pl.radius - 120), pl.top_y - pl.thickness / 2, Math.sin(b) * (pl.radius - 120));
        m.rotation.y = -b;
      }
    });
    const pp = U.pipes;
    const gPipes = layer('U-03', 'Service pipes', pp.count, `Ø ${2 * pp.radius} on R ${pp.ring_radius}`);
    for (let k = 0; k < pp.count; k++) {
      const b = (k / pp.count) * Math.PI * 2;
      cylY(gPipes, M.trim, pp.radius, pp.radius, pp.top_y - pp.bottom_y, Math.cos(b) * pp.ring_radius, (pp.top_y + pp.bottom_y) / 2, Math.sin(b) * pp.ring_radius, 12, `pipe ${k + 1}`);
    }
    const mb = U.machinery_blocks;
    const gMach = layer('U-04', 'Machinery blocks', mb.count, `${mb.width} × ${mb.height} × ${mb.depth} m`);
    for (let k = 0; k < mb.count; k++) {
      const b = (k / mb.count) * Math.PI * 2 + 30 * DEG;
      const m = box(gMach, M.hull, mb.depth, mb.height, mb.width, Math.cos(b) * mb.ring_radius, mb.top_y - mb.height / 2, Math.sin(b) * mb.ring_radius, `machinery ${k + 1}`);
      m.rotation.y = -b;
      const v = box(gMach, M.rim_light, 40, mb.height * 0.3, mb.width * 0.6, Math.cos(b) * (mb.ring_radius + mb.depth / 2 + 10), mb.top_y - mb.height / 2, Math.sin(b) * (mb.ring_radius + mb.depth / 2 + 10));
      v.rotation.y = -b;
    }
    const k = U.keel, kc = U.keel_cone;
    const gKeel = layer('U-05', 'Keel + cone', 1, `Ø ${2 * k.radius} × ${k.height}; cone to Ø ${2 * kc.radius_bottom}`);
    cylY(gKeel, M.hull_dark, k.radius, k.radius, k.height, 0, k.top_y - k.height / 2, 0, 64, 'keel');
    cylY(gKeel, M.hull_dark, kc.radius_top, kc.radius_bottom, kc.height, 0, kc.top_y - kc.height / 2, 0, 64, 'keel cone');
    for (let i = 0; i < 3; i++) {
      const ring = mesh(new THREE.TorusGeometry(k.radius + 60, 70, 8, 64), M.hull, gKeel, 'keel ring');
      ring.rotation.x = Math.PI / 2; ring.position.y = k.top_y - k.height * (0.2 + 0.3 * i);
    }
    for (let q = 0; q < 8; q++) {
      const b = (q / 8) * Math.PI * 2;
      const fin = box(gKeel, M.hull, 500, k.height * 0.7, 80, Math.cos(b) * (k.radius + 200), k.top_y - k.height / 2, Math.sin(b) * (k.radius + 200));
      fin.rotation.y = -b;
    }
    const gEm = layer('U-06', 'Keel emitter', 1, `sphere R ${U.keel_emitter.radius}`);
    sphere(gEm, M.beacon, U.keel_emitter.radius, 0, U.keel_emitter.y, 0, 'keel emitter');
    const em2 = sphere(gEm, M.glass, U.keel_emitter.radius * 1.5, 0, U.keel_emitter.y, 0, 'emitter halo');
    em2.material = new THREE.MeshBasicMaterial({ color: '#9fefff', transparent: true, opacity: 0.18, depthWrite: false });

    // ------------------------------------------------------------------ legs
    const gLegs = layer('L-01', 'Legs', L.count, `Ø ${2 * L.radius_attach} → ${2 * L.radius_foot}`);
    const gKnee = layer('L-02', 'Knee joints', L.count, `sphere R ${L.knee_radius}`);
    const gFeet = layer('L-03', 'Foot pads', L.count, `Ø ${2 * L.foot_pad.radius} × ${L.foot_pad.thickness}`);
    const gBrace = layer('L-04', 'Leg braces', L.count, `Ø ${2 * L.brace.radius}`);
    L.azimuths_deg.forEach((azDeg, i) => {
      const a = azDeg * DEG;
      const A = new THREE.Vector3(Math.cos(a) * L.attach.ring_radius, L.attach.y, Math.sin(a) * L.attach.ring_radius);
      const F = new THREE.Vector3(Math.cos(a) * L.foot.ring_radius, L.foot.y, Math.sin(a) * L.foot.ring_radius);
      tubeBetween(gLegs, M.hull_dark, A, F, L.radius_attach, L.radius_foot, `leg ${i + 1}`);
      // segment collars along the leg
      for (const u of [0.18, 0.42, 0.66, 0.88]) {
        const p = A.clone().lerp(F, u);
        const r = L.radius_attach + (L.radius_foot - L.radius_attach) * u;
        const c = mesh(new THREE.TorusGeometry(r + 30, 45, 8, 24), M.hull, gLegs, 'leg collar');
        c.position.copy(p);
        c.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), F.clone().sub(A).normalize());
      }
      sphere(gKnee, M.hull, L.knee_radius, A.x, A.y, A.z, `knee ${i + 1}`);
      // short upper stub from the knee up into the plate stack
      tubeBetween(gKnee, M.hull_dark, A, new THREE.Vector3(A.x * 0.92, U.plates[2].top_y, A.z * 0.92), L.radius_attach * 0.9, L.radius_attach * 0.9);
      const fp = cylY(gFeet, M.hull, L.foot_pad.radius, L.foot_pad.radius * 0.8, L.foot_pad.thickness, F.x, F.y - L.foot_pad.thickness / 2, F.z, 32, `foot ${i + 1}`);
      fp.rotation.y = 0;
      const bp = A.clone().lerp(F, L.brace.leg_frac);
      const kp = new THREE.Vector3(Math.cos(a) * k.radius, L.brace.keel_y, Math.sin(a) * k.radius);
      tubeBetween(gBrace, M.hull_dark, bp, kp, L.brace.radius, L.brace.radius, `brace ${i + 1}`);
    });

    return { root, parts, stats, materials: M };
  }

  global.CitadelGeometry = { buildCitadel, mulberry32 };
})(typeof window !== 'undefined' ? window : globalThis);
