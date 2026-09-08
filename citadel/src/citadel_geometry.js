/* Citadel of Ricks — procedural geometry builder (spec v2: revolved pods).
 *
 * buildCitadel(THREE, spec) -> { root, parts, stats, materials }
 *   root  : THREE.Group, 1 unit = 1 metre, +Y up, origin = main pod dome-base plane
 *   parts : [{ id, name, group, qty, dims }] — one entry per layer, matching the
 *           parts list on schematic sheet 4
 *
 * Every dimension comes from spec.json. The main pod and the three satellite
 * pods are the same body of revolution (spec.pod_profile) at scale 1.0 and
 * spec.satellite_pods.scale. Nothing is hard-coded here except tessellation
 * and a seeded random generator for the skylines.
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
    const PP = spec.pod_profile, MP = spec.main_pod, SP = spec.satellite_pods, B = spec.bridges, L = spec.legs, AN = spec.antenna;
    const M = {};
    for (const [k, m] of Object.entries(spec.materials)) {
      if (k === 'glass') {
        M[k] = new THREE.MeshPhysicalMaterial({ color: m.color, transparent: true, opacity: m.opacity, roughness: m.roughness, metalness: 0, side: THREE.DoubleSide, depthWrite: false, envMapIntensity: 0.6, name: k });
      } else {
        const opts = { color: m.color, roughness: m.roughness ?? 0.6, metalness: m.metalness ?? 0.4, name: k };
        if (m.emissive) { opts.emissive = m.emissive; opts.emissiveIntensity = m.emissiveIntensity ?? 1; }
        M[k] = new THREE.MeshStandardMaterial(opts);
      }
    }
    M.hull_ds = M.hull.clone(); M.hull_ds.side = THREE.DoubleSide; M.hull_ds.name = 'hull';

    const G = { box: new THREE.BoxGeometry(1, 1, 1), cyl: new THREE.CylinderGeometry(1, 1, 1, 24), sphere: new THREE.SphereGeometry(1, 24, 16) };
    const root = new THREE.Group(); root.name = 'Citadel of Ricks';
    const parts = [];
    const stats = { meshes: 0, triangles: 0 };

    function layer(id, name, qty, dims) {
      const g = new THREE.Group(); g.name = `${id} ${name}`; g.userData = { id, name, qty, dims };
      root.add(g); parts.push({ id, name, group: g, qty, dims }); return g;
    }
    function mesh(geo, mat, parent, name) {
      const m = new THREE.Mesh(geo, mat); if (name) m.name = name; parent.add(m); stats.meshes++;
      const idx = geo.index ? geo.index.count : geo.attributes.position.count; stats.triangles += Math.round(idx / 3); return m;
    }
    function box(parent, mat, w, h, d, x, y, z, name) { const m = mesh(G.box, mat, parent, name); m.scale.set(w, h, d); m.position.set(x, y, z); return m; }
    function cylY(parent, mat, rTop, rBot, h, x, yc, z, seg, name) {
      let m;
      if (rTop === rBot && (!seg || seg === 24)) { m = mesh(G.cyl, mat, parent, name); m.scale.set(rTop, h, rTop); }
      else m = mesh(new THREE.CylinderGeometry(rTop, rBot, h, seg || 24), mat, parent, name);
      m.position.set(x, yc, z); return m;
    }
    function sphere(parent, mat, r, x, y, z, name) { const m = mesh(G.sphere, mat, parent, name); m.scale.set(r, r, r); m.position.set(x, y, z); return m; }
    function tubeBetween(parent, mat, a, b, rA, rB, name) {
      const dir = new THREE.Vector3().subVectors(b, a); const len = dir.length();
      const m = mesh(new THREE.CylinderGeometry(rB, rA, len, 16), mat, parent, name);
      m.position.copy(a).addScaledVector(dir, 0.5); m.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.clone().normalize()); return m;
    }
    function disc(parent, r, h, yTop, sideMat, topMat, seg, name) {
      const m = mesh(new THREE.CylinderGeometry(r, r, h, seg || 128), [sideMat, topMat, sideMat], parent, name); m.position.y = yTop - h / 2; return m;
    }

    // ------------------------------------------------------------------ city
    function city(parent, c, seed, domeR, domeH, label) {
      const rnd = mulberry32(seed); const towers = []; let tries = 0;
      while (towers.length < c.tower_count && tries < c.tower_count * 40) {
        tries++;
        const r = Math.sqrt(rnd()) * c.max_radius, a = rnd() * Math.PI * 2, x = r * Math.cos(a), z = r * Math.sin(a);
        if (r < c.keepout_radius) continue;
        const fp = c.footprint_min + rnd() * (c.footprint_max - c.footprint_min);
        if (towers.some(t => Math.hypot(t.x - x, t.z - z) < (t.fp + fp) * 0.75)) continue;
        const centreBias = 1 - r / c.max_radius;
        let h = c.height_min + (c.height_max - c.height_min) * Math.pow(rnd(), 1.6) * (0.35 + 0.65 * centreBias);
        const domeLimit = domeH * Math.sqrt(Math.max(0, 1 - Math.pow((r + fp * 0.7) / domeR, 2))) - 120;
        h = Math.min(h, domeLimit);
        if (h < c.height_min * 0.6) continue;
        towers.push({ x, z, fp, h, round: rnd() < 0.22, step: rnd() < 0.35 });
      }
      towers.forEach((t, i) => {
        if (t.round) { const m = cylY(parent, M.city, t.fp * 0.5, t.fp * 0.55, t.h, t.x, t.h / 2, t.z, 20, `${label} tower ${i + 1}`); m.rotation.y = i; }
        else box(parent, M.city, t.fp, t.h, t.fp * (0.7 + 0.5 * ((i * 7) % 5) / 5), t.x, t.h / 2, t.z, `${label} tower ${i + 1}`);
        if (t.step) box(parent, M.city, t.fp * 0.6, t.h * 0.22, t.fp * 0.6, t.x, t.h + t.h * 0.11, t.z);
        box(parent, M.city_glow, t.fp * 0.5, 30, t.fp * 0.5, t.x, t.h + (t.step ? t.h * 0.22 : 0) + 15, t.z);
        box(parent, M.city_glow, t.fp * 1.04, t.h * 0.06, t.fp * 1.04, t.x, t.h * 0.5, t.z);
      });
      const rnd2 = mulberry32(seed + 99);
      for (let i = 0; i < c.lowrise_count; i++) {
        const r = Math.sqrt(rnd2()) * c.max_radius, a = rnd2() * Math.PI * 2, x = r * Math.cos(a), z = r * Math.sin(a);
        if (r < c.keepout_radius) continue;
        const w = 120 + rnd2() * 220, d = 120 + rnd2() * 220, h = c.lowrise_height_min + rnd2() * (c.lowrise_height_max - c.lowrise_height_min);
        const m = box(parent, M.city, w, h, d, x, h / 2, z); m.rotation.y = rnd2() * Math.PI;
      }
      return towers.length;
    }

    // ------------------------------------------------------------------- pod
    // Builds one revolved pod of dome radius R into the given layer groups.
    function buildPod(R, groups, opts) {
      const { gDome, gCollar, gHull, gPlates, gCore, gCity } = groups;
      const pos = new THREE.Vector3().fromArray(opts.position);
      const at = (g) => { const s = new THREE.Group(); s.name = opts.label; s.position.copy(pos); g.add(s); return s; };
      const sDome = at(gDome), sCollar = at(gCollar), sHull = at(gHull), sPlates = at(gPlates), sCore = at(gCore), sCity = at(gCity);

      // dome (ellipsoidal glass cap)
      const dh = PP.dome.height_frac * R;
      const dome = mesh(new THREE.SphereGeometry(R, PP.dome.segments, Math.round(PP.dome.segments / 2), 0, Math.PI * 2, 0, Math.PI / 2), M.glass, sDome, `${opts.label} dome`);
      dome.scale.y = dh / R; dome.position.y = PP.dome.base_y_frac * R; dome.renderOrder = 10;
      // deck floor under the dome (the city's ground plane)
      disc(sDome, R * 0.995, R * 0.02, PP.dome.base_y_frac * R, M.hull, M.hull_light, 128, `${opts.label} deck`);

      // ribs + hoops
      const ribs = opts.isMain ? PP.ribs.count_main : PP.ribs.count_satellite;
      for (let i = 0; i < ribs; i++) {
        const rib = mesh(new THREE.TorusGeometry(R, PP.ribs.tube_frac * R, 8, 48, Math.PI), M.hull_light, sCollar, `${opts.label} rib ${i + 1}`);
        rib.rotation.y = (i / ribs) * Math.PI * 2; rib.scale.y = dh / R; rib.position.y = PP.dome.base_y_frac * R;
      }
      for (const f of PP.ribs.hoops) {
        const y = PP.dome.base_y_frac * R + dh * f, r = R * Math.sqrt(1 - f * f);
        const hoop = mesh(new THREE.TorusGeometry(r, PP.ribs.tube_frac * R * 0.8, 8, 128), M.hull_light, sCollar, `${opts.label} hoop`);
        hoop.rotation.x = Math.PI / 2; hoop.position.y = y;
      }

      // collar: the raised band round the widest part
      const C = PP.collar, cr = C.radius_frac * R, ch = C.height_frac * R, ctop = C.top_y_frac * R;
      disc(sCollar, cr, ch, ctop, M.hull, M.hull_light, 160, `${opts.label} collar`);
      const band = mesh(new THREE.CylinderGeometry(cr + R * 0.002, cr + R * 0.002, C.light_band_frac * R, 160, 1, true), M.rim_light, sCollar, `${opts.label} collar light`);
      band.position.y = ctop - ch * 0.62;
      for (let i = 0; i < PP.greebles.collar_panels; i++) {
        const a = (i / PP.greebles.collar_panels) * Math.PI * 2;
        const p = box(sCollar, M.trim, R * 0.005, ch * 0.5, R * 0.08, Math.cos(a) * (cr + R * 0.002), ctop - ch * 0.28, Math.sin(a) * (cr + R * 0.002)); p.rotation.y = -a;
      }
      // hangar bays cut into the collar
      const hb = PP.hangar_bays;
      for (let i = 0; i < hb.count; i++) {
        const a = (i / hb.count) * Math.PI * 2 + hb.phase_deg * DEG, depth = hb.depth_frac * R, rr = cr - depth / 2 + R * 0.004;
        const bay = box(sCollar, M.trim, depth, hb.height_frac * R, hb.width_frac * R, Math.cos(a) * rr, hb.y_frac * R, Math.sin(a) * rr, `${opts.label} hangar ${i + 1}`); bay.rotation.y = -a;
        const glow = box(sCollar, M.rim_light, R * 0.004, hb.height_frac * R * 0.7, hb.width_frac * R * 0.92, Math.cos(a) * (cr - depth + R * 0.006), hb.y_frac * R, Math.sin(a) * (cr - depth + R * 0.006)); glow.rotation.y = -a;
      }

      // hull: revolved profile (r, y) — Lathe revolves points in the XY plane about Y
      const pts = PP.hull.map(([r, y]) => new THREE.Vector2(r * R, y * R));
      pts.unshift(new THREE.Vector2(cr * 0.985, ctop - ch)); // tuck under the collar
      const hull = mesh(new THREE.LatheGeometry(pts, 128), M.hull_ds, sHull, `${opts.label} hull`);
      // horizontal panel lines on the hull
      for (const [r, y] of PP.hull.slice(1, 5)) {
        const ring = mesh(new THREE.TorusGeometry(r * R + R * 0.004, R * 0.006, 6, 128), M.trim, sHull, `${opts.label} hull seam`);
        ring.rotation.x = Math.PI / 2; ring.position.y = y * R;
      }

      // plates
      PP.plates.forEach(([r, yTop, t], i) => {
        const pr = r * R, pt = t * R, py = yTop * R;
        disc(sPlates, pr, pt, py, M.hull_dark, M.hull, 128, `${opts.label} plate ${i + 1}`);
        const seam = mesh(new THREE.CylinderGeometry(pr + R * 0.001, pr + R * 0.001, pt * 0.18, 128, 1, true), M.rim_light, sPlates, `${opts.label} plate seam`);
        seam.position.y = py - pt * 0.5;
        for (let k = 0; k < 16; k++) {
          const b = (k / 16) * Math.PI * 2 + i * 0.13;
          const g = box(sPlates, M.hull, R * 0.05, pt + R * 0.012, R * 0.03, Math.cos(b) * (pr - R * 0.016), py - pt / 2, Math.sin(b) * (pr - R * 0.016)); g.rotation.y = -b;
        }
      });

      // core + fins + nub
      const K = PP.core, kTop = K.top_y_frac * R, kBot = K.bottom_y_frac * R, kr = K.radius_frac * R;
      cylY(sCore, M.hull_dark, kr, kr, kTop - kBot, 0, (kTop + kBot) / 2, 0, 64, `${opts.label} core`);
      for (let k = 0; k < PP.greebles.core_fins; k++) {
        const b = (k / PP.greebles.core_fins) * Math.PI * 2;
        const f = box(sCore, M.trim, R * 0.012, (kTop - kBot) * 0.92, R * 0.035, Math.cos(b) * (kr + R * 0.004), (kTop + kBot) / 2, Math.sin(b) * (kr + R * 0.004)); f.rotation.y = -b;
      }
      const N = PP.nub;
      cylY(sCore, M.hull_dark, N.radius_top_frac * R, N.radius_bottom_frac * R, N.height_frac * R, 0, N.top_y_frac * R - N.height_frac * R / 2, 0, 48, `${opts.label} nub`);
      const nubLight = mesh(new THREE.TorusGeometry(N.radius_top_frac * R * 0.8, R * 0.01, 8, 48), M.rim_light, sCore, `${opts.label} nub light`);
      nubLight.rotation.x = Math.PI / 2; nubLight.position.y = N.top_y_frac * R - N.height_frac * R * 0.45;

      // city under the dome
      const n = city(sCity, opts.city, opts.seed, R, dh, opts.label);
      sCity.position.y += PP.dome.base_y_frac * R;
      return { towers: n, dome_top: PP.dome.base_y_frac * R + dh, bottom: N.top_y_frac * R - N.height_frac * R, collar_radius: cr };
    }

    // ---------------------------------------------------------------- layers
    const R = MP.dome_radius, Rs = R * SP.scale;
    const podDims = (r) => `dome Ø ${Math.round(2 * r).toLocaleString()} m`;
    const main = {
      gDome: layer('M-01', 'Main dome (glass) + deck', 1, `Ø ${2 * R} × h ${Math.round(PP.dome.height_frac * R)} m`),
      gCollar: layer('M-02', 'Main collar, ribs, hangar bays', 1, `Ø ${Math.round(2 * PP.collar.radius_frac * R)} × ${Math.round(PP.collar.height_frac * R)} m; ${PP.hangar_bays.count} bays`),
      gHull: layer('M-03', 'Main hull (revolved)', 1, `Ø ${Math.round(2 * 1.09 * R)} → ${Math.round(2 * 0.68 * R)} m over ${Math.round(0.56 * R)} m`),
      gPlates: layer('M-04', 'Main metallic plates', PP.plates.length, 'Ø ' + PP.plates.map(p => Math.round(2 * p[0] * R).toLocaleString()).join(' / ')),
      gCore: layer('M-05', 'Main core + nub', 1, `Ø ${Math.round(2 * PP.core.radius_frac * R)} m, bottom at ${Math.round((PP.nub.top_y_frac - PP.nub.height_frac) * R)} m`),
      gCity: layer('M-06', 'Main city', MP.city.tower_count, `${MP.city.height_min}–${MP.city.height_max} m towers + ${MP.city.lowrise_count} low-rise`),
    };
    const mainInfo = buildPod(R, main, { position: MP.position, label: 'main', isMain: true, city: MP.city, seed: MP.city.seed });
    parts.find(p => p.id === 'M-06').qty = mainInfo.towers;

    // council spire at the centre of the main city
    const ct = MP.council_tower;
    const gCouncil = layer('M-07', 'Council spire', 1, `Ø ${2 * ct.radius_base} → ${2 * ct.radius_top}, h ${ct.height + ct.crown_height} m`);
    const cy = PP.dome.base_y_frac * R;
    cylY(gCouncil, M.city, ct.radius_top, ct.radius_base, ct.height, 0, cy + ct.height / 2, 0, 8, 'council spire');
    cylY(gCouncil, M.city_glow, 0, ct.radius_top, ct.crown_height, 0, cy + ct.height + ct.crown_height / 2, 0, 8, 'council crown');
    for (const f of [0.3, 0.55, 0.8]) { const r = ct.radius_base + (ct.radius_top - ct.radius_base) * f; cylY(gCouncil, M.city_glow, r + 25, r + 25, 40, 0, cy + ct.height * f, 0, 8); }
    disc(gCouncil, ct.radius_base * 1.35, 40, cy + 40, M.hull_light, M.hull_light, 48, 'council plaza');

    // satellite pods
    const sat = {
      gDome: layer('S-01', 'Satellite domes (glass) + decks', SP.count, `Ø ${Math.round(2 * Rs)} × h ${Math.round(PP.dome.height_frac * Rs)} m each`),
      gCollar: layer('S-02', 'Satellite collars, ribs, bays', SP.count, `Ø ${Math.round(2 * PP.collar.radius_frac * Rs)} m each`),
      gHull: layer('S-03', 'Satellite hulls (revolved)', SP.count, `${Math.round(SP.scale * 100)} % copies of the main hull`),
      gPlates: layer('S-04', 'Satellite metallic plates', SP.count * PP.plates.length, 'Ø ' + PP.plates.map(p => Math.round(2 * p[0] * Rs).toLocaleString()).join(' / ')),
      gCore: layer('S-05', 'Satellite cores + nubs', SP.count, `Ø ${Math.round(2 * PP.core.radius_frac * Rs)} m`),
      gCity: layer('S-06', 'Satellite cities', SP.count, `${SP.city.tower_count} towers + ${SP.city.lowrise_count} low-rise each`),
    };
    const satCentres = SP.azimuths_deg.map((a) => new THREE.Vector3(Math.cos(a * DEG) * SP.center_distance, SP.y_offset, Math.sin(a * DEG) * SP.center_distance));
    satCentres.forEach((c, i) => buildPod(Rs, sat, { position: c.toArray(), label: `pod ${i + 1}`, isMain: false, city: SP.city, seed: SP.city.seed_base + i * 17 }));

    // ---------------------------------------------------------------- bridges
    const gTube = layer('B-01', 'Bridge tubes (organic)', B.count, `Ø ${2 * B.tube_radius_main} → ${2 * B.tube_radius_satellite} m, sag ${B.sag} m, ${B.rib_count} ribs`);
    const gTruss = layer('B-02', 'Bridge trusses (technical)', B.count, `${B.truss.width} × ${B.truss.height} m rail`);
    const hullRadiusAt = (Rp, y) => { // radius of the revolved hull at height y (linear between profile points)
      const f = y / Rp; const h = PP.hull;
      for (let i = 0; i < h.length - 1; i++) { const [r0, y0] = h[i], [r1, y1] = h[i + 1]; if (f <= y0 && f >= y1) { const u = (y0 - f) / (y0 - y1 || 1); return (r0 + (r1 - r0) * u) * Rp; } }
      return h[0][0] * Rp;
    };
    satCentres.forEach((c, i) => {
      const dir = c.clone().setY(0).normalize();
      const A = dir.clone().multiplyScalar(hullRadiusAt(R, B.attach_y_main) - 250).setY(B.attach_y_main);
      const Bp = c.clone().sub(dir.clone().multiplyScalar(hullRadiusAt(Rs, B.attach_y_satellite) - 250)).setY(SP.y_offset + B.attach_y_satellite);
      const mid = A.clone().lerp(Bp, 0.5); mid.y -= B.sag * 2; // control point: bezier passes at half the control offset
      const curve = new THREE.QuadraticBezierCurve3(A, mid, Bp);
      const tube = mesh(new THREE.TubeGeometry(curve, 32, (B.tube_radius_main + B.tube_radius_satellite) / 2, 24, false), M.bridge_tube, gTube, `bridge ${i + 1} tube`);
      // flared sockets where the tube meets each hull
      const tA = curve.getTangentAt(0), tB = curve.getTangentAt(1);
      const sockA = mesh(new THREE.CylinderGeometry(B.tube_radius_main * 1.25, (B.tube_radius_main + B.tube_radius_satellite) / 2, 700, 24), M.hull_dark, gTube, 'bridge socket'); sockA.position.copy(A).addScaledVector(tA, 350); sockA.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), tA);
      const sockB = mesh(new THREE.CylinderGeometry((B.tube_radius_main + B.tube_radius_satellite) / 2, B.tube_radius_satellite * 1.25, 700, 24), M.hull_dark, gTube, 'bridge socket'); sockB.position.copy(Bp).addScaledVector(tB, -350); sockB.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), tB);
      for (let k = 0; k < B.rib_count; k++) {
        const u = (k + 0.5) / B.rib_count, p = curve.getPointAt(u), t = curve.getTangentAt(u);
        const r = (B.tube_radius_main + B.tube_radius_satellite) / 2 + B.rib_tube_radius * 0.6;
        const rib = mesh(new THREE.TorusGeometry(r, B.rib_tube_radius, 8, 32), M.hull_dark, gTube, 'bridge rib'); rib.position.copy(p); rib.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), t);
      }
      // technical truss: straight rail above the tube from collar to collar
      const T = B.truss;
      const a2 = dir.clone().multiplyScalar(PP.collar.radius_frac * R - 200).setY(T.y), b2 = c.clone().sub(dir.clone().multiplyScalar(PP.collar.radius_frac * Rs - 200)).setY(SP.y_offset + T.y);
      const len = a2.distanceTo(b2), midT = a2.clone().lerp(b2, 0.5);
      const deck = box(gTruss, M.hull_light, len, T.height * 0.25, T.width, midT.x, midT.y, midT.z, `bridge ${i + 1} truss deck`); deck.rotation.y = -Math.atan2(dir.z, dir.x);
      for (const s of [-1, 1]) {
        const rail = tubeBetween(gTruss, M.hull_dark, a2.clone().add(new THREE.Vector3(-dir.z, 0, dir.x).multiplyScalar(s * T.width / 2)).setY(T.y + T.height), b2.clone().add(new THREE.Vector3(-dir.z, 0, dir.x).multiplyScalar(s * T.width / 2)).setY(T.y + T.height), T.rail_radius, T.rail_radius, 'truss rail');
        const glow = box(gTruss, M.rim_light, len, 30, 30, midT.x + (-dir.z) * s * T.width / 2, T.y + T.height + T.rail_radius + 15, midT.z + dir.x * s * T.width / 2); glow.rotation.y = -Math.atan2(dir.z, dir.x);
        void rail;
      }
      for (let k = 0; k < 6; k++) {
        const u = (k + 0.5) / 6, p = a2.clone().lerp(b2, u);
        for (const s of [-1, 1]) box(gTruss, M.hull_dark, 90, T.height, 90, p.x + (-dir.z) * s * T.width / 2, T.y + T.height / 2, p.z + dir.x * s * T.width / 2);
      }
    });

    // ------------------------------------------------------------------ legs
    const gLegs = layer('L-01', 'Legs', L.count, `Ø ${2 * L.radius_attach} → ${2 * L.radius_foot} m`);
    const gKnee = layer('L-02', 'Knee joints + braces', L.count, `sphere R ${L.knee_radius}; brace Ø ${2 * L.brace.radius}`);
    const gFeet = layer('L-03', 'Foot pads', L.count, `Ø ${2 * L.foot_pad.radius} × ${L.foot_pad.thickness} m`);
    L.azimuths_deg.forEach((azDeg, i) => {
      const a = azDeg * DEG;
      const A = new THREE.Vector3(Math.cos(a) * L.attach.ring_radius, L.attach.y, Math.sin(a) * L.attach.ring_radius);
      const F = new THREE.Vector3(Math.cos(a) * L.foot.ring_radius, L.foot.y, Math.sin(a) * L.foot.ring_radius);
      tubeBetween(gLegs, M.hull_dark, A, F, L.radius_attach, L.radius_foot, `leg ${i + 1}`);
      for (const u of [0.15, 0.38, 0.6, 0.82]) {
        const p = A.clone().lerp(F, u), r = L.radius_attach + (L.radius_foot - L.radius_attach) * u;
        const c = mesh(new THREE.TorusGeometry(r + 30, 50, 8, 24), M.hull, gLegs, 'leg collar'); c.position.copy(p); c.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), F.clone().sub(A).normalize());
      }
      sphere(gKnee, M.hull, L.knee_radius, A.x, A.y, A.z, `knee ${i + 1}`);
      tubeBetween(gKnee, M.hull_dark, A, new THREE.Vector3(A.x * 0.6, PP.plates[2][1] * R, A.z * 0.6), L.radius_attach * 0.9, L.radius_attach * 0.9, 'leg root');
      const bp = A.clone().lerp(F, L.brace.leg_frac);
      tubeBetween(gKnee, M.hull_dark, bp, new THREE.Vector3(Math.cos(a) * PP.core.radius_frac * R, L.brace.core_y, Math.sin(a) * PP.core.radius_frac * R), L.brace.radius, L.brace.radius, `brace ${i + 1}`);
      cylY(gFeet, M.hull, L.foot_pad.radius, L.foot_pad.radius * 0.8, L.foot_pad.thickness, F.x, F.y - L.foot_pad.thickness / 2, F.z, 32, `foot ${i + 1}`);
    });

    // --------------------------------------------------------------- antenna
    const gAnt = layer('A-01', 'Central antenna (downward)', 1, `${AN.length.toLocaleString()} m long, Ø ${2 * AN.radius_top} → ${2 * AN.radius_tip} m`);
    const aTop = AN.top_y, aBot = AN.top_y - AN.length;
    cylY(gAnt, M.hull_dark, AN.radius_top, AN.radius_tip, AN.length, 0, (aTop + aBot) / 2, 0, 16, 'antenna mast');
    cylY(gAnt, M.hull_light, AN.radius_top * 2.4, AN.radius_top * 1.6, 260, 0, aTop - 130, 0, 24, 'antenna mount');
    for (const rg of AN.rings) {
      const y = aTop - AN.length * rg.y_frac;
      const t = mesh(new THREE.TorusGeometry(rg.radius, 40, 8, 40), M.hull_light, gAnt, 'antenna ring'); t.rotation.x = Math.PI / 2; t.position.y = y;
      for (let k = 0; k < 4; k++) { const s = box(gAnt, M.hull_dark, rg.radius, 24, 24, Math.cos(k * Math.PI / 2) * rg.radius / 2, y, Math.sin(k * Math.PI / 2) * rg.radius / 2); s.rotation.y = -k * Math.PI / 2; }
    }
    const dishPts = []; for (let i = 0; i <= 10; i++) { const u = i / 10; dishPts.push(new THREE.Vector2(u * AN.dish.radius, -u * u * AN.dish.depth)); }
    const dish = mesh(new THREE.LatheGeometry(dishPts, 40), new THREE.MeshStandardMaterial({ color: spec.materials.hull_light.color, side: THREE.DoubleSide, roughness: 0.5, metalness: 0.5 }), gAnt, 'antenna dish');
    dish.position.y = aTop - AN.length * AN.dish.y_frac;
    sphere(gAnt, M.beacon, AN.beacon_radius, 0, aBot, 0, 'antenna beacon');
    const halo = sphere(gAnt, M.glass, AN.beacon_radius * 1.6, 0, aBot, 0, 'beacon halo'); halo.material = new THREE.MeshBasicMaterial({ color: '#9fefff', transparent: true, opacity: 0.18, depthWrite: false });

    return { root, parts, stats, materials: M, info: { main: mainInfo } };
  }

  global.CitadelGeometry = { buildCitadel, mulberry32 };
})(typeof window !== 'undefined' ? window : globalThis);
