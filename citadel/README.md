# Citadel of Ricks — 1:1 3D model

A fan-made, dimensioned reconstruction of the Citadel of Ricks (Rick and Morty) at
1:1 scale in metres, with a four-sheet general-arrangement schematic, an interactive
3D viewer, and GLB/OBJ exports. Everything is generated from one file, `spec.json`,
so the drawing, the model and the exports can never disagree with each other.

Open **`viewer.html`** in any modern browser. It is a single self-contained file
(three.js is inlined) and needs no server and no network.

## What is in here

| Path | What it is |
| --- | --- |
| `spec.json` | Every dimension, angle, material and camera preset, in metres. The single source of truth. |
| `overall_dimensions.json` | Computed envelope (heights, widths, leg length, rake), written by the schematic tool. |
| `schematic/citadel_schematic.svg` | Sheet 1 plan, sheet 2 front elevation, sheet 3 hub section + leg detail, sheet 4 parts list, envelope, scale basis and references. |
| `viewer.html` | Interactive viewer: orbit/zoom/pan, view presets (the show's establishing angle, top, front, side, underside), per-layer visibility, dome-glass opacity, wireframe, part labels, hover-to-identify with dimensions, scale grid, and a Schematic and Spec tab. |
| `viewer.artifact.html` | Same page without the document wrapper, for embedding in a host page skeleton. |
| `exports/citadel.glb` | Binary glTF of the exact scene the viewer shows, 1 unit = 1 m, with materials. Opens in Blender, Windows 3D Viewer, macOS Preview/Quick Look, Godot, Unity, Unreal, three.js. |
| `exports/citadel.obj.zip` | Wavefront OBJ of the same scene (geometry only), zipped; the viewer can also export a fresh OBJ. |
| `qc/*.png` | Headless renders used for the quality check: each preset view, wireframe, opaque-glass with labels, and three close-ups. |
| `src/citadel_geometry.js` | Procedural geometry builder (three.js), driven by `spec.json`. |
| `src/viewer_template.html` | Viewer page and app code with placeholders the bundler fills. |
| `tools/make_schematic.py` | `spec.json` → schematic SVG + `overall_dimensions.json`. No dependencies beyond Python 3. |
| `tools/bundle.py` | Inlines three.js, the geometry builder, the spec and the schematic into `viewer.html`. |
| `tools/qc_render.js` | Playwright script: renders every view headlessly and writes the GLB/OBJ exports through the page's own exporters. |

## Key numbers

| Item | Value |
| --- | --- |
| Hub deck | Ø 17.0 km, 1.4 km thick |
| Main dome | Ø 15.2 km, 5.7 km high (ellipsoid), 12 ribs |
| Satellite districts (pods) | 3, Ø 6.6 km decks, centres 13.6 km out at 90°, 210°, 330° |
| Bridges | 3, 1.8 km clear span, ribbed transit tube + 1.25 km wide causeway |
| Metallic plates | 5, Ø 15.4 → 6.7 km, stacked 4.5 km deep under the deck |
| Keel | Ø 3.9 km, cone to Ø 1.4 km, emitter 13.2 km below deck |
| Legs | 3, 17.6 km long, 21° rake, at 30°, 150°, 270° (between the pods) |
| Antenna | 4.3 km mast on the dome apex, tip 10.0 km above deck |
| Overall | 30.7 km tall (leg feet to antenna tip), 34.0 km bounding circle in plan |

## Scale basis

The show never states the Citadel's size. The only in-universe yardstick is the
street-level material in *The Ricklantis Mixup* (S3E7): cars of ~4 m give building
widths and tower spacing, and extrapolating that to the exterior establishing shot
puts the central disc at roughly the size of Brooklyn (15–17 km across). The
community 1:200 000 print model reaches the same Brooklyn-sized centre disc by the
same route. Everything else is proportioned from the recurring exterior shot
(S1E10, S3E1, S3E7, S5E10): central glass dome city, three smaller domed districts
protruding from it, several metallic plates below, three legs, a single antenna.
The shot is always the same three-quarter angle, so the underside and the legs are
the least attested parts; they follow the wiki description and the silhouette.

## Regenerating

```bash
python3 citadel/tools/make_schematic.py              # schematic + overall_dimensions.json
npm install three@0.170.0 --prefix /some/dir         # once, anywhere
python3 citadel/tools/bundle.py --three /some/dir/node_modules/three
node citadel/tools/qc_render.js                      # renders qc/*.png and writes exports/
```

`qc_render.js` needs Playwright with Chromium (`npm i -g playwright && npx playwright install chromium`).

## Coordinate system

Metres, +Y up. Origin is the centre of the hub deck at its top surface (y = 0).
Azimuth 0° is +X and increases toward +Z (counter-clockwise seen from above).
In the exports this is the glTF convention (+Y up, right-handed), so the model
imports upright at true scale; scale by 0.001 if your tool works in kilometres.

This is a fan reconstruction and is not affiliated with or endorsed by Adult Swim
or the show's creators.
