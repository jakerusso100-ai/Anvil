#!/usr/bin/env python3
"""Bundle the Citadel viewer into self-contained HTML files.

Inputs
  src/viewer_template.html      page + UI + app code (placeholders below)
  src/citadel_geometry.js       geometry builder
  spec.json / overall_dimensions.json / schematic/citadel_schematic.svg
  three.js (module build + OrbitControls + GLTFExporter + OBJExporter),
  located via --three <node_modules/three> (default: ./qc/node_modules/three
  next to this repo, or $THREE_DIR)

Outputs
  citadel/viewer.html           standalone (has <!doctype html> wrapper) — open locally
  citadel/viewer.artifact.html  same page without the document wrapper, for hosting
                                 inside a page skeleton (claude.ai artifact)

three.js is converted from an ES module into a classic script that defines
window.THREE, so the page needs no module loader, no CDN and no network.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def three_as_global(src: str) -> str:
    """Turn three.module.min.js's trailing `export{a as B,...};` into window.THREE = {...}."""
    idx = src.rfind("export{")
    if idx < 0:
        raise SystemExit("three.module.min.js: export block not found")
    head, tail = src[:idx], src[idx + len("export{"):]
    end = tail.rfind("};")
    body = tail[:end]
    entries = []
    for item in body.split(","):
        item = item.strip()
        if not item:
            continue
        if " as " in item:
            local, exported = [x.strip() for x in item.split(" as ")]
            entries.append(f"{exported}:{local}")
        else:
            entries.append(item)
    if "import" in head[:200]:
        raise SystemExit("unexpected import statement at top of three build")
    return head + "window.THREE={" + ",".join(entries) + "};\n"


def addon_as_global(src: str, export_name: str) -> str:
    """Rewrite `import {A,B} from 'three'` -> `const {A,B} = THREE;` and drop the export."""
    m = re.search(r"import\s*\{([^}]*)\}\s*from\s*['\"]three['\"];?", src)
    if not m:
        raise SystemExit(f"{export_name}: import block not found")
    names = ",".join(n.strip() for n in m.group(1).split(",") if n.strip())
    src = src[:m.start()] + f"const {{{names}}} = THREE;" + src[m.end():]
    src = re.sub(r"export\s*\{\s*" + export_name + r"\s*\};?", f"window.{export_name} = {export_name};", src)
    if re.search(r"^\s*import\s", src, re.M):
        raise SystemExit(f"{export_name}: leftover import statements")
    # Each addon gets its own scope: classic scripts share one global lexical
    # scope, so two addons both declaring `const {Vector3} = THREE` would throw.
    return "(function () {\n" + src + "\n})();\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--three", default=os.environ.get("THREE_DIR", str(ROOT.parent / "qc" / "node_modules" / "three")))
    args = ap.parse_args()
    three = Path(args.three)
    if not (three / "build" / "three.module.min.js").exists():
        raise SystemExit(f"three.js not found under {three}; run `npm install three@0.170.0` somewhere and pass --three")

    core = three_as_global((three / "build" / "three.module.min.js").read_text())
    orbit = addon_as_global((three / "examples" / "jsm" / "controls" / "OrbitControls.js").read_text(), "OrbitControls")
    gltf = addon_as_global((three / "examples" / "jsm" / "exporters" / "GLTFExporter.js").read_text(), "GLTFExporter")
    obj = addon_as_global((three / "examples" / "jsm" / "exporters" / "OBJExporter.js").read_text(), "OBJExporter")
    version = json.loads((three / "package.json").read_text())["version"]

    tpl = (ROOT / "src" / "viewer_template.html").read_text()
    geometry = (ROOT / "src" / "citadel_geometry.js").read_text()
    spec = (ROOT / "spec.json").read_text()
    overall = (ROOT / "overall_dimensions.json").read_text()
    svg = (ROOT / "schematic" / "citadel_schematic.svg").read_text()

    def fill(s: str) -> str:
        # str.replace, not format(): the payloads are full of braces
        return (s.replace("/*__THREE__*/", core)
                 .replace("/*__ORBIT__*/", orbit)
                 .replace("/*__GLTF__*/", gltf)
                 .replace("/*__OBJ__*/", obj)
                 .replace("/*__GEOMETRY__*/", geometry)
                 .replace("/*__SPEC__*/", spec)
                 .replace("/*__OVERALL__*/", overall)
                 .replace("<!--__SCHEMATIC__-->", svg)
                 .replace("__THREE_VERSION__", version))

    page = fill(tpl)
    standalone = "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n" \
                 + page.replace("<!--__BODY_SPLIT__-->", "</head>\n<body>") + "\n</body>\n</html>\n"
    artifact = page.replace("<!--__BODY_SPLIT__-->", "")
    (ROOT / "viewer.html").write_text(standalone)
    (ROOT / "viewer.artifact.html").write_text(artifact)
    for f in ("viewer.html", "viewer.artifact.html"):
        print(f"wrote {ROOT / f}  ({(ROOT / f).stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
