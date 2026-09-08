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

## Key numbers (spec v2)

| Item | Value |
| --- | --- |
| Main pod | one body of revolution: Ø 15.2 km glass dome (4.7 km high), Ø 16.7 km raised collar with 8 hangar bays, bowl hull, 5 stacked metallic plates, core and nub; 14.1 km tall overall |
| Satellite districts | 3 copies of the main pod at 60 % (Ø 9.1 km domes), centres 15.5 km out at 90°, 210°, 330° |
| Bridges | 3 organic ribbed tubes (Ø 2.5 → 1.8 km, 0.9 km sag, 2.6 km clear span) with a technical truss rail above |
| Legs | 3, 23.9 km long, 31° rake, from the main pod's lower plates at 30°, 150°, 270° (between the pods) |
| Central antenna | 12.4 km, running down the middle of the main pod, shorter than the legs |
| Overall | 32.1 km tall (leg feet to dome top), 41.0 km bounding circle in plan |

## What changed from v1 and why

v1 was a flat disc with a hemisphere, small pods on stalks, a separate keel and
an antenna on top. The written sources (`research.md`) describe something else:
one *revolved* main pod with a raised band round it, three *60 %* copies of that
pod on *sculpted, organic* bridges, three legs, and a single antenna that runs
*down the middle* of the main pod and is *shorter than the legs*. v2 follows that
description part for part. What could not be done is a frame-by-frame check
against the show: this environment's network policy blocks every image host
(the full list is in `research.md`). To get that check, commit reference stills
into `citadel/refs/` and re-run the QC.

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
