#!/usr/bin/env python3
"""Sanity-check exports/citadel.glb and citadel.obj against overall_dimensions.json.

Loads both files with trimesh, prints mesh/triangle counts and the bounding box
in metres, and fails if the box disagrees with the schematic envelope by more
than 1 %.  Run:  python3 citadel/tools/validate_exports.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import trimesh

ROOT = Path(__file__).resolve().parents[1]
OV = json.loads((ROOT / "overall_dimensions.json").read_text())
SPEC = json.loads((ROOT / "spec.json").read_text())

expected = {
    "x": OV["width_x_extent"],
    "y": OV["height_total"],
    "z": OV["width_z_extent"],
}
# The antenna beacon and foot-pad radii add a little to the analytic envelope.
tolerance = 0.012

ok = True
for name in ("citadel.glb", "citadel.obj", "citadel.obj.zip"):
    path = ROOT / "exports" / name
    if not path.exists():
        if name == "citadel.obj" and (ROOT / "exports" / "citadel.obj.zip").exists():
            continue  # the raw OBJ is only kept zipped in the repo
        if name.endswith(".zip"):
            continue
        print(f"MISSING {path}")
        ok = False
        continue
    if name.endswith(".zip"):
        import io, zipfile
        with zipfile.ZipFile(path) as z:
            scene = trimesh.load(io.BytesIO(z.read("citadel.obj")), file_type="obj", force="scene")
    else:
        scene = trimesh.load(path, force="scene")
    geoms = list(scene.geometry.values())
    tris = sum(int(g.faces.shape[0]) for g in geoms)
    lo, hi = scene.bounds
    size = hi - lo
    print(f"{name}: {path.stat().st_size / 1048576:.2f} MB, {len(scene.graph.nodes_geometry)} nodes, "
          f"{len(geoms)} unique geometries, {tris:,} triangles")
    print(f"  bounds min {lo.round().tolist()}  max {hi.round().tolist()}  size {size.round().tolist()} m")
    for axis, idx in (("x", 0), ("y", 1), ("z", 2)):
        rel = abs(size[idx] - expected[axis]) / expected[axis]
        flag = "ok" if rel <= tolerance else "MISMATCH"
        if rel > tolerance:
            ok = False
        print(f"  {axis}: {size[idx]:,.0f} m vs envelope {expected[axis]:,.0f} m ({rel * 100:.2f} %) {flag}")
    # The top of the antenna and the bottom of the leg feet, as absolute checks.
    top_expected = SPEC["hub"]["antenna"]["base_y"] + SPEC["hub"]["antenna"]["height"] + SPEC["hub"]["antenna"]["beacon_radius"]
    bottom_expected = SPEC["legs"]["foot"]["y"] - SPEC["legs"]["foot_pad"]["thickness"]
    if abs(hi[1] - top_expected) > 50 or abs(lo[1] - bottom_expected) > 60:
        print(f"  Y range {lo[1]:.0f}..{hi[1]:.0f} does not match antenna tip {top_expected} / feet {bottom_expected}")
        ok = False

print("VALIDATION", "PASSED" if ok else "FAILED")
sys.exit(0 if ok else 1)
