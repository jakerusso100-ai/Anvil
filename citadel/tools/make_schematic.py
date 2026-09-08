#!/usr/bin/env python3
"""Generate the dimensioned schematic (SVG) of the Citadel of Ricks from spec.json.

Every number drawn here is read from citadel/spec.json, the same file the 3D
viewer builds its geometry from, so the drawing and the model cannot drift
apart.  Output:

    citadel/schematic/citadel_schematic.svg   four-sheet drawing
    citadel/overall_dimensions.json           computed envelope / summary

Run:  python3 citadel/tools/make_schematic.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "spec.json").read_text())

# ----------------------------------------------------------------------------
# Derived numbers (the "overall" block)
# ----------------------------------------------------------------------------
H, P, B, U, L = SPEC["hub"], SPEC["pods"], SPEC["bridges"], SPEC["understructure"], SPEC["legs"]

antenna_top = H["antenna"]["base_y"] + H["antenna"]["height"]
foot_bottom = L["foot"]["y"] - L["foot_pad"]["thickness"]
keel_bottom = U["keel_emitter"]["y"] - U["keel_emitter"]["radius"]
pod_outer = P["center_distance"] + P["deck_rim_band"]["radius"]
leg_outer = L["foot"]["ring_radius"] + L["foot_pad"]["radius"]
overall_radius = max(pod_outer, leg_outer, H["deck_lip"]["radius"])
dx = L["foot"]["ring_radius"] - L["attach"]["ring_radius"]
dy = L["attach"]["y"] - L["foot"]["y"]
leg_len = math.hypot(dx, dy)
leg_rake = math.degrees(math.atan2(dx, dy))
bridge_len = (P["center_distance"] - P["deck"]["radius"]) - H["deck"]["radius"]

# Widest extent in X and Z separately (pods/legs are not symmetric about both axes,
# so take the true min..max of every outermost circle rather than doubling one side).
def extent(axis: str) -> float:
    lo, hi = -H["deck_lip"]["radius"], H["deck_lip"]["radius"]
    circles = [(P["center_distance"], a, P["deck_rim_band"]["radius"]) for a in P["azimuths_deg"]]
    circles += [(L["foot"]["ring_radius"], a, L["foot_pad"]["radius"]) for a in L["azimuths_deg"]]
    for dist, a, r in circles:
        c = math.cos(math.radians(a)) if axis == "x" else math.sin(math.radians(a))
        lo, hi = min(lo, dist * c - r), max(hi, dist * c + r)
    return hi - lo

OVERALL = {
    "units": "meters",
    "height_total": antenna_top - foot_bottom,
    "height_deck_to_antenna_tip": antenna_top,
    "height_above_deck_incl_antenna": antenna_top,
    "depth_below_deck_to_keel_emitter": -keel_bottom,
    "depth_below_deck_to_leg_feet": -foot_bottom,
    "width_x_extent": extent("x"),
    "width_z_extent": extent("z"),
    "bounding_circle_diameter_plan": 2 * overall_radius,
    "hub_deck_diameter": 2 * H["deck"]["radius"],
    "hub_dome_diameter": 2 * H["dome"]["base_radius"],
    "hub_dome_height": H["dome"]["height"],
    "pod_deck_diameter": 2 * P["deck"]["radius"],
    "pod_center_distance": P["center_distance"],
    "bridge_clear_span": bridge_len,
    "leg_length": round(leg_len),
    "leg_rake_deg": round(leg_rake, 1),
    "antenna_height": H["antenna"]["height"],
    "council_tower_height": H["council_tower"]["height"] + H["council_tower"]["crown_height"],
}
(ROOT / "overall_dimensions.json").write_text(json.dumps(OVERALL, indent=2) + "\n")

# ----------------------------------------------------------------------------
# SVG helpers
# ----------------------------------------------------------------------------
INK = "#1d2330"
DIM = "#b3412a"
HID = "#8a94a6"
GLASS = "#3ea99a"
FILL = "#e9edf3"
FILL2 = "#cfd6e0"


def fmt(v: float) -> str:
    return f"{v:,.0f} m"


class Sheet:
    """One sheet of the drawing: world metres -> page px via (scale, origin)."""

    def __init__(self, x0, y0, w, h, scale, ox, oy, title, subtitle, flip_y=True):
        self.x0, self.y0, self.w, self.h = x0, y0, w, h
        self.s, self.ox, self.oy = scale, ox, oy
        self.flip = -1 if flip_y else 1
        self.out = []
        self.title, self.subtitle = title, subtitle

    def X(self, x):
        return self.x0 + self.ox + x * self.s

    def Y(self, y):
        return self.y0 + self.oy + self.flip * y * self.s

    def add(self, s):
        self.out.append(s)

    # primitives -------------------------------------------------------------
    def circle(self, cx, cy, r, stroke=INK, fill="none", dash="", sw=1.6):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<circle cx="{self.X(cx):.1f}" cy="{self.Y(cy):.1f}" r="{r*self.s:.1f}" stroke="{stroke}" fill="{fill}" stroke-width="{sw}"{d}/>')

    def rect(self, x, y, w, h, stroke=INK, fill="none", dash="", sw=1.6):
        """x,y = lower-left in world coords, w,h positive."""
        d = f' stroke-dasharray="{dash}"' if dash else ""
        px, py = self.X(x), self.Y(y + h) if self.flip == -1 else self.Y(y)
        self.add(f'<rect x="{px:.1f}" y="{py:.1f}" width="{w*self.s:.1f}" height="{h*self.s:.1f}" stroke="{stroke}" fill="{fill}" stroke-width="{sw}"{d}/>')

    def line(self, x1, y1, x2, y2, stroke=INK, sw=1.6, dash=""):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{self.X(x1):.1f}" y1="{self.Y(y1):.1f}" x2="{self.X(x2):.1f}" y2="{self.Y(y2):.1f}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def poly(self, pts, stroke=INK, fill="none", sw=1.6, dash="", close=True):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        p = " ".join(f"{self.X(x):.1f},{self.Y(y):.1f}" for x, y in pts)
        tag = "polygon" if close else "polyline"
        self.add(f'<{tag} points="{p}" stroke="{stroke}" fill="{fill}" stroke-width="{sw}"{d}/>')

    def half_ellipse_up(self, cx, base_y, rx, ry, stroke=INK, fill="none", sw=1.6):
        x1, x2 = self.X(cx - rx), self.X(cx + rx)
        y = self.Y(base_y)
        self.add(f'<path d="M{x1:.1f},{y:.1f} A{rx*self.s:.1f},{ry*self.s:.1f} 0 0 1 {x2:.1f},{y:.1f} Z" stroke="{stroke}" fill="{fill}" stroke-width="{sw}"/>')

    def text(self, x, y, s, size=13, anchor="start", color=INK, weight="normal", rotate=0, mono=False):
        fam = "'JetBrains Mono','Consolas',monospace" if mono else "'Inter','Helvetica Neue',Arial,sans-serif"
        rot = f' transform="rotate({rotate} {self.X(x):.1f} {self.Y(y):.1f})"' if rotate else ""
        self.add(f'<text x="{self.X(x):.1f}" y="{self.Y(y):.1f}" font-size="{size}" text-anchor="{anchor}" fill="{color}" font-weight="{weight}" font-family="{fam}"{rot}>{s}</text>')

    def ptext(self, px, py, s, size=13, anchor="start", color=INK, weight="normal", mono=False):
        """text at page pixels (relative to sheet origin)."""
        fam = "'JetBrains Mono','Consolas',monospace" if mono else "'Inter','Helvetica Neue',Arial,sans-serif"
        self.add(f'<text x="{self.x0+px:.1f}" y="{self.y0+py:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{color}" font-weight="{weight}" font-family="{fam}">{s}</text>')

    # dimension lines --------------------------------------------------------
    def dim_h(self, x1, x2, y, label, off=0, above=True, label_x=None):
        """horizontal dimension between x1..x2 drawn at world y, label centred (or at label_x)."""
        X1, X2, Y = self.X(x1), self.X(x2), self.Y(y)
        if label_x is not None:
            self.add(f'<line x1="{X1:.1f}" y1="{Y:.1f}" x2="{X2:.1f}" y2="{Y:.1f}" stroke="{DIM}" stroke-width="1.1" marker-start="url(#arrS)" marker-end="url(#arrE)"/>')
            ty = Y - 5 if above else Y + 15
            self.add(f'<text x="{self.X(label_x):.1f}" y="{ty:.1f}" font-size="12" text-anchor="start" fill="{DIM}" font-family="Inter,Arial,sans-serif">{label}</text>')
            return
        self.add(f'<line x1="{X1:.1f}" y1="{Y:.1f}" x2="{X2:.1f}" y2="{Y:.1f}" stroke="{DIM}" stroke-width="1.1" marker-start="url(#arrS)" marker-end="url(#arrE)"/>')
        ty = Y - 5 if above else Y + 15
        self.add(f'<text x="{(X1+X2)/2:.1f}" y="{ty:.1f}" font-size="12" text-anchor="middle" fill="{DIM}" font-family="Inter,Arial,sans-serif">{label}</text>')

    def dim_v(self, y1, y2, x, label, side=1):
        X, Y1, Y2 = self.X(x), self.Y(y1), self.Y(y2)
        self.add(f'<line x1="{X:.1f}" y1="{Y1:.1f}" x2="{X:.1f}" y2="{Y2:.1f}" stroke="{DIM}" stroke-width="1.1" marker-start="url(#arrS)" marker-end="url(#arrE)"/>')
        tx = X + 6 * side
        anchor = "start" if side > 0 else "end"
        self.add(f'<text x="{tx:.1f}" y="{(Y1+Y2)/2+4:.1f}" font-size="12" text-anchor="{anchor}" fill="{DIM}" font-family="Inter,Arial,sans-serif">{label}</text>')

    def ext(self, x1, y1, x2, y2):
        self.line(x1, y1, x2, y2, stroke=DIM, sw=0.7)

    def leader(self, x, y, px, py, label, anchor="start"):
        """leader from world point to page-relative label position."""
        X, Y = self.X(x), self.Y(y)
        LX, LY = self.x0 + px, self.y0 + py
        self.add(f'<line x1="{X:.1f}" y1="{Y:.1f}" x2="{LX:.1f}" y2="{LY:.1f}" stroke="{INK}" stroke-width="0.8"/>')
        self.add(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="2.2" fill="{INK}"/>')
        dx = 4 if anchor == "start" else -4
        self.add(f'<text x="{LX+dx:.1f}" y="{LY+4:.1f}" font-size="11.5" text-anchor="{anchor}" fill="{INK}" font-family="Inter,Arial,sans-serif">{label}</text>')

    def frame(self, n):
        self.add(f'<rect x="{self.x0}" y="{self.y0}" width="{self.w}" height="{self.h}" fill="#fbfcfe" stroke="{INK}" stroke-width="2"/>')
        self.ptext(18, 30, f"SHEET {n}  ·  {self.title}", 20, weight="700")
        self.ptext(18, 50, self.subtitle, 12.5, color="#4a5568")
        self.ptext(self.w - 18, 30, f"Scale: 1 px = {1/self.s:,.0f} m", 12, anchor="end", color="#4a5568", mono=True)

    def render(self):
        cid = f"clip{abs(hash((self.x0, self.y0)))}"
        return (f'<clipPath id="{cid}"><rect x="{self.x0}" y="{self.y0}" width="{self.w}" height="{self.h}"/></clipPath>'
                f'<g clip-path="url(#{cid})">' + "\n".join(self.out) + "</g>")


# ----------------------------------------------------------------------------
# Sheet 1: PLAN
# ----------------------------------------------------------------------------
PW, PH = 1200, 1080
plan = Sheet(20, 20, PW, PH, 1200 / 48000, PW / 2, PH / 2 + 40,
             "PLAN VIEW (from above)", "+X to the right, +Z up the page. Azimuths counter-clockwise from +X. Legs and understructure shown hidden (dashed).")
plan.frame(1)

# hidden understructure (below deck)
for pl in U["plates"]:
    plan.circle(0, 0, pl["radius"], stroke=HID, dash="6,5", sw=0.9)
plan.circle(0, 0, U["core"]["radius"], stroke=HID, dash="6,5", sw=0.9)
plan.circle(0, 0, U["keel"]["radius"], stroke=HID, dash="3,4", sw=0.9)
for a in L["azimuths_deg"]:
    r = math.radians(a)
    ax, az = L["attach"]["ring_radius"] * math.cos(r), L["attach"]["ring_radius"] * math.sin(r)
    fx, fz = L["foot"]["ring_radius"] * math.cos(r), L["foot"]["ring_radius"] * math.sin(r)
    plan.line(ax, az, fx, fz, stroke=HID, sw=3.2, dash="10,6")
    plan.circle(fx, fz, L["foot_pad"]["radius"], stroke=HID, dash="4,3", sw=1)
    plan.circle(ax, az, L["knee_radius"], stroke=HID, dash="4,3", sw=1)
    plan.text(fx * 1.09, fz * 1.09, f"LEG {L['azimuths_deg'].index(a)+1}  ({a}°)", 11, anchor="middle", color=HID)

# hub
plan.circle(0, 0, H["deck_lip"]["radius"], fill=FILL2)
plan.circle(0, 0, H["deck"]["radius"], fill=FILL)
plan.circle(0, 0, H["dome"]["base_radius"], stroke=GLASS, fill="#d9f3ee", sw=2)
plan.circle(0, 0, H["dome_collar"]["ring_radius"], stroke=GLASS, sw=0.8)
for i in range(H["dome_ribs"]["count"]):
    r = math.radians(i * 360 / H["dome_ribs"]["count"])
    plan.line(0, 0, H["dome"]["base_radius"] * math.cos(r), H["dome"]["base_radius"] * math.sin(r), stroke=GLASS, sw=0.5)
plan.circle(0, 0, H["council_tower"]["radius_base"], fill="#ffffff")
plan.circle(0, 0, H["city"]["max_radius"], stroke=HID, dash="2,3", sw=0.7)
# hangar bays
for i in range(H["hangar_bays"]["count"]):
    a = math.radians(i * 360 / H["hangar_bays"]["count"] + 22.5)
    rr = H["deck_rim_band"]["radius"]
    w = H["hangar_bays"]["width"]
    tx, tz = -math.sin(a), math.cos(a)
    cx, cz = rr * math.cos(a), rr * math.sin(a)
    plan.line(cx - tx * w / 2, cz - tz * w / 2, cx + tx * w / 2, cz + tz * w / 2, stroke=DIM, sw=3)

# pods + bridges
for i, a in enumerate(P["azimuths_deg"]):
    r = math.radians(a)
    cx, cz = P["center_distance"] * math.cos(r), P["center_distance"] * math.sin(r)
    # bridge
    x1 = H["deck"]["radius"]; x2 = P["center_distance"] - P["deck"]["radius"]
    hw = B["causeway"]["width"] / 2
    pts = []
    for (u, v) in [(x1, -hw), (x2, -hw), (x2, hw), (x1, hw)]:
        pts.append((u * math.cos(r) - v * math.sin(r), u * math.sin(r) + v * math.cos(r)))
    plan.poly(pts, fill=FILL2)
    plan.circle(cx, cz, P["deck_rim_band"]["radius"], fill=FILL2)
    plan.circle(cx, cz, P["deck"]["radius"], fill=FILL)
    plan.circle(cx, cz, P["dome"]["base_radius"], stroke=GLASS, fill="#d9f3ee", sw=2)
    plan.circle(cx, cz, P["understructure"]["core_radius"], stroke=HID, dash="4,3", sw=0.8)
    plan.text(cx, cz + P["deck_rim_band"]["radius"] + 900, f"POD {i+1}  ({a}°)", 12, anchor="middle", weight="700")

# axes
plan.line(-21000, 0, 21000, 0, stroke=HID, sw=0.6, dash="12,6")
plan.line(0, -21000, 0, 21000, stroke=HID, sw=0.6, dash="12,6")
plan.text(22000, 400, "+X", 12, color=HID)
plan.text(400, 18300, "+Z", 12, color=HID)

# dimensions
plan.dim_h(-H["deck"]["radius"], H["deck"]["radius"], -9600, f"HUB DECK Ø {fmt(2*H['deck']['radius'])}", above=False)
plan.dim_h(-H["dome"]["base_radius"], H["dome"]["base_radius"], 8700, f"DOME Ø {fmt(2*H['dome']['base_radius'])}", label_x=1100)
px, pz = P["center_distance"] * math.cos(math.radians(330)), P["center_distance"] * math.sin(math.radians(330))
plan.dim_h(px - P["deck"]["radius"], px + P["deck"]["radius"], pz - P["deck_rim_band"]["radius"] - 700, f"POD DECK Ø {fmt(2*P['deck']['radius'])}", above=False)
plan.line(0, 0, px, pz, stroke=DIM, sw=1.1)
plan.text(px * 0.30 - 2600, pz * 0.30 + 1500, f"CENTRE DISTANCE {fmt(P['center_distance'])}", 12, color=DIM, rotate=30)
plan.dim_h(-overall_radius, overall_radius, 19400, f"BOUNDING CIRCLE Ø {fmt(2*overall_radius)}  (widest extent, leg feet / pod rims)")
plan.ext(-overall_radius, 19400, -overall_radius, 0)
plan.ext(overall_radius, 19400, overall_radius, 0)
plan.circle(0, 0, overall_radius, stroke=DIM, dash="2,6", sw=0.8)
# bridge span
bx1, bx2 = H["deck"]["radius"], P["center_distance"] - P["deck"]["radius"]
r330 = math.radians(330)
plan.text((bx1 + bx2) / 2 * math.cos(r330) + 2300, (bx1 + bx2) / 2 * math.sin(r330) + 300, f"BRIDGE SPAN {fmt(bridge_len)}", 11, color=DIM, rotate=30)
# legend
plan.ptext(18, PH - 62, "Solid = above deck plane.  Dashed grey = understructure / legs below the deck.  Orange ticks on the rim = hangar bays.", 11.5, color="#4a5568")
plan.ptext(18, PH - 44, f"Pods every 120° at {P['azimuths_deg']}°; legs every 120° at {L['azimuths_deg']}° (offset 60°, between the pods).", 11.5, color="#4a5568")
plan.ptext(18, PH - 26, f"Plan envelope: {fmt(OVERALL['width_x_extent'])} (X) × {fmt(OVERALL['width_z_extent'])} (Z).", 11.5, color="#4a5568")
plan.add(f'<rect x="{plan.x0+PW-440}" y="{plan.y0+PH-100}" width="424" height="84" fill="#ffffff" stroke="{INK}" stroke-width="1.4"/>')
plan.ptext(PW - 428, PH - 78, SPEC["name"].upper() + "  —  GENERAL ARRANGEMENT", 14, weight="700")
plan.ptext(PW - 428, PH - 58, "Units: metres · Scale 1:1 · Up = +Y · Origin: deck centre", 11, mono=True)
plan.ptext(PW - 428, PH - 42, f"Spec v{SPEC['version']} · tools/make_schematic.py · 4 sheets", 11, mono=True)
plan.ptext(PW - 428, PH - 26, "Fan-made reconstruction of the show's exterior establishing shot; not official.", 10.5, color="#4a5568")

# ----------------------------------------------------------------------------
# Sheet 2: FRONT ELEVATION  (camera at +Z looking toward -Z; X right, Y up)
# ----------------------------------------------------------------------------
EW, EH = 1200, 1080
elev = Sheet(20 + PW + 20, 20, EW, EH, 1200 / 48000, EW / 2, 352,
             "FRONT ELEVATION", "Viewed from +Z (pod 1 nearest the viewer). X to the right, Y up. Deck top surface is y = 0.")
elev.frame(2)

def pod_xz(a):
    r = math.radians(a)
    return P["center_distance"] * math.cos(r), P["center_distance"] * math.sin(r)

# far legs first (behind), then near
for a in sorted(L["azimuths_deg"], key=lambda a: math.sin(math.radians(a))):
    r = math.radians(a)
    ax = L["attach"]["ring_radius"] * math.cos(r)
    fx = L["foot"]["ring_radius"] * math.cos(r)
    near = math.sin(r) > 0
    ra, rf = L["radius_attach"], L["radius_foot"]
    elev.poly([(ax - ra, L["attach"]["y"]), (ax + ra, L["attach"]["y"]), (fx + rf, L["foot"]["y"]), (fx - rf, L["foot"]["y"])],
              fill=FILL2 if near else "#dfe4ec")
    elev.circle(ax, L["attach"]["y"], L["knee_radius"], fill=FILL2)
    elev.rect(fx - L["foot_pad"]["radius"], L["foot"]["y"] - L["foot_pad"]["thickness"], 2 * L["foot_pad"]["radius"], L["foot_pad"]["thickness"], fill=FILL2)
    # brace
    bx = ax + (fx - ax) * L["brace"]["leg_frac"]
    by = L["attach"]["y"] + (L["foot"]["y"] - L["attach"]["y"]) * L["brace"]["leg_frac"]
    elev.line(bx, by, 0, L["brace"]["keel_y"], sw=2.2, stroke=HID if not near else INK)

# far pods (behind hub) drawn before hub
def draw_pod(cx, near):
    f = FILL if near else "#e2e7ef"
    d = P["deck"]
    elev.rect(cx - P["deck_rim_band"]["radius"], P["deck_rim_band"]["top_y"] - P["deck_rim_band"]["height"], 2 * P["deck_rim_band"]["radius"], P["deck_rim_band"]["height"], fill=FILL2)
    elev.rect(cx - d["radius"], -d["thickness"], 2 * d["radius"], d["thickness"], fill=f)
    us = P["understructure"]
    elev.rect(cx - us["core_radius"], -d["thickness"] - us["core_height"], 2 * us["core_radius"], us["core_height"], fill=FILL2)
    for pl in us["plates"]:
        elev.rect(cx - pl["radius"], pl["top_y"] - pl["thickness"], 2 * pl["radius"], pl["thickness"], fill=FILL2)
    sp = us["spike"]
    elev.poly([(cx - sp["radius"], sp["top_y"]), (cx + sp["radius"], sp["top_y"]), (cx, sp["top_y"] - sp["height"])], fill=FILL2)
    elev.half_ellipse_up(cx, 0, P["dome"]["base_radius"], P["dome"]["height"], stroke=GLASS, fill="#d9f3ee")

for a in P["azimuths_deg"]:
    cx, cz = pod_xz(a)
    if cz <= 0:
        draw_pod(cx, False)
        # bridge (seen obliquely; draw as bar from hub edge to pod edge)
        sx = H["deck"]["radius"] * math.copysign(1, cx)
        ex = cx - P["deck"]["radius"] * math.copysign(1, cx)
        elev.rect(min(sx, ex), -B["causeway"]["thickness"], abs(ex - sx), B["causeway"]["thickness"], fill=FILL2)
        elev.rect(min(sx, ex), B["tube"]["y"] - B["tube"]["radius_hub"], abs(ex - sx), 2 * B["tube"]["radius_hub"], fill="#d2d9c9")

# understructure (hub)
uc = U["core"]
elev.rect(-uc["radius"], uc["top_y"] - uc["height"], 2 * uc["radius"], uc["height"], fill=FILL2)
for pl in U["plates"]:
    elev.rect(-pl["radius"], pl["top_y"] - pl["thickness"], 2 * pl["radius"], pl["thickness"], fill=FILL2)
mb = U["machinery_blocks"]
for i in range(mb["count"]):
    a = math.radians(i * 360 / mb["count"] + 30)
    cx = mb["ring_radius"] * math.cos(a)
    elev.rect(cx - mb["width"] / 2, mb["top_y"] - mb["height"], mb["width"], mb["height"], fill="#dfe4ec", sw=0.8)
k = U["keel"]
elev.rect(-k["radius"], k["top_y"] - k["height"], 2 * k["radius"], k["height"], fill=FILL2)
kc = U["keel_cone"]
elev.poly([(-kc["radius_top"], kc["top_y"]), (kc["radius_top"], kc["top_y"]), (kc["radius_bottom"], kc["top_y"] - kc["height"]), (-kc["radius_bottom"], kc["top_y"] - kc["height"])], fill=FILL2)
elev.circle(0, U["keel_emitter"]["y"], U["keel_emitter"]["radius"], fill="#dff6ff")

# hub deck, rim, dome
elev.rect(-H["deck_rim_band"]["radius"], H["deck_rim_band"]["top_y"] - H["deck_rim_band"]["height"], 2 * H["deck_rim_band"]["radius"], H["deck_rim_band"]["height"], fill=FILL2)
elev.rect(-H["deck_lip"]["radius"], H["deck_lip"]["top_y"] - H["deck_lip"]["height"], 2 * H["deck_lip"]["radius"], H["deck_lip"]["height"], fill=FILL2)
elev.rect(-H["deck"]["radius"], -H["deck"]["thickness"], 2 * H["deck"]["radius"], H["deck"]["thickness"], fill=FILL)
elev.half_ellipse_up(0, 0, H["dome"]["base_radius"], H["dome"]["height"], stroke=GLASS, fill="#d9f3ee")
# skyline hint (deterministic sample of towers) and council tower
ct = H["council_tower"]
elev.poly([(-ct["radius_base"], 0), (ct["radius_base"], 0), (ct["radius_top"], ct["height"]), (-ct["radius_top"], ct["height"])], fill="#ffffff")
elev.poly([(-ct["radius_top"], ct["height"]), (ct["radius_top"], ct["height"]), (0, ct["height"] + ct["crown_height"])], fill="#ffffff")
for i in range(-9, 10):
    if i == 0:
        continue
    x = i * 700
    hmax = H["dome"]["height"] * math.sqrt(max(0.0, 1 - (x / H["dome"]["base_radius"]) ** 2)) - 400
    hgt = min(hmax, H["city"]["height_min"] + (H["city"]["height_max"] - H["city"]["height_min"]) * (1 - abs(i) / 10))
    elev.rect(x - 180, 0, 360, max(hgt, 200), fill="#ffffff", sw=0.8)
# antenna
an = H["antenna"]
elev.poly([(-an["radius_base"], an["base_y"]), (an["radius_base"], an["base_y"]), (an["radius_top"], antenna_top), (-an["radius_top"], antenna_top)], fill=INK)
for rg in an["rings"]:
    y = an["base_y"] + an["height"] * rg["y_frac"]
    elev.line(-rg["radius"], y, rg["radius"], y, sw=2)
dsh = an["dish"]
y = an["base_y"] + an["height"] * dsh["y_frac"]
elev.poly([(-dsh["radius"], y + dsh["depth"]), (0, y), (dsh["radius"], y + dsh["depth"])], fill="none", sw=1.4, close=False)
elev.circle(0, antenna_top, an["beacon_radius"] * 2, fill="#dff6ff")

# near pod (in front of hub)
for a in P["azimuths_deg"]:
    cx, cz = pod_xz(a)
    if cz > 0:
        draw_pod(cx, True)
        elev.text(cx, -P["deck"]["thickness"] - P["understructure"]["core_height"] - 5200, f"POD {P['azimuths_deg'].index(a)+1} (nearest)", 11, anchor="middle")

# ground line / datum
elev.line(-21000, 0, 21000, 0, stroke=DIM, sw=0.7, dash="8,5")
elev.text(-20800, 250, "DATUM y = 0 (hub deck surface)", 11, color=DIM)

# dimensions (vertical, right side)
xr = 16800
elev.dim_v(0, antenna_top, xr, f"{fmt(antenna_top)} deck→antenna")
elev.ext(0, antenna_top, xr, antenna_top)
elev.dim_v(0, H["dome"]["height"], -9300, f"DOME {fmt(H['dome']['height'])}", side=-1)
elev.ext(-H["dome"]["base_radius"] * 0.2, H["dome"]["height"], -9300, H["dome"]["height"])
elev.dim_v(-H["deck"]["thickness"], 0, 9600, f"DECK {fmt(H['deck']['thickness'])}", side=1)
ps_top, ps_bot = -H["deck"]["thickness"], U["plates"][-1]["top_y"] - U["plates"][-1]["thickness"]
elev.dim_v(ps_bot, ps_top, 9600, f"PLATES {fmt(ps_top - ps_bot)}", side=1)
elev.ext(U["plates"][-1]["radius"], ps_bot, 9600, ps_bot)
elev.dim_v(keel_bottom, 0, xr - 2600, f"{fmt(-keel_bottom)} deck→keel", side=1)
elev.ext(0, keel_bottom, xr - 2600, keel_bottom)
elev.dim_v(foot_bottom, 0, -xr - 2400, f"{fmt(-foot_bottom)} deck→feet", side=-1)
elev.ext(-L["foot"]["ring_radius"] * math.cos(math.radians(30)), foot_bottom, -xr - 2400, foot_bottom)
elev.dim_v(foot_bottom, antenna_top, -xr + 800, f"{fmt(OVERALL['height_total'])} OVERALL", side=-1)
elev.dim_h(-H["deck"]["radius"], H["deck"]["radius"], antenna_top + 700, f"HUB DECK Ø {fmt(2*H['deck']['radius'])}", label_x=-H["deck"]["radius"] + 600)
elev.ext(-H["deck"]["radius"], 0, -H["deck"]["radius"], antenna_top + 700)
elev.ext(H["deck"]["radius"], 0, H["deck"]["radius"], antenna_top + 700)
elev.dim_h(-OVERALL["width_x_extent"] / 2, OVERALL["width_x_extent"] / 2, foot_bottom - 1400, f"X EXTENT {fmt(OVERALL['width_x_extent'])}", above=False)
elev.leader(0, an["base_y"] + an["height"] * 0.5, EW / 2 + 120, 75, f"Antenna: {fmt(an['height'])} tall, Ø {2*an['radius_base']} → {2*an['radius_top']} m")
elev.leader(ct["radius_top"], ct["height"], EW / 2 + 150, 140, f"Council spire {fmt(OVERALL['council_tower_height'])}")
fxn = L["foot"]["ring_radius"] * math.cos(math.radians(30))
elev.leader(fxn * 0.55 + 2000, L["attach"]["y"] + (L["foot"]["y"] - L["attach"]["y"]) * 0.5, EW - 470, EH - 120, f"Leg: {fmt(leg_len)} long, rake {leg_rake:.0f}°, Ø {2*L['radius_attach']} → {2*L['radius_foot']} m", anchor="start")
elev.ptext(18, EH - 26, "Pods 2 and 3 sit behind the hub in this view; their bridges are foreshortened. Leg 3 (270°) is directly behind the keel.", 11.5, color="#4a5568")

# ----------------------------------------------------------------------------
# Sheet 3: HUB SECTION + LEG DETAIL  (section on the X–Y plane through the centre)
# ----------------------------------------------------------------------------
SW_, SH_ = 1200, 1000
sec = Sheet(20, 20 + PH + 20, SW_, SH_, 1200 / 34000, 560, 330,
            "HUB SECTION A–A and LEG DETAIL", "Vertical section through the hub on the X–Y plane. Solid = cut material. Dome shell, rim band, plate stack, pipes, keel and emitter dimensioned.")
sec.frame(3)
# section fill
sec.rect(-H["deck"]["radius"], -H["deck"]["thickness"], 2 * H["deck"]["radius"], H["deck"]["thickness"], fill="#c9d1dc")
sec.rect(-H["deck_rim_band"]["radius"], H["deck_rim_band"]["top_y"] - H["deck_rim_band"]["height"], 2 * H["deck_rim_band"]["radius"], H["deck_rim_band"]["height"], fill="#b9c2cf")
# hangar mouth cut on right rim
hb = H["hangar_bays"]
sec.rect(H["deck_rim_band"]["radius"] - hb["depth"], hb["y"] - hb["height"] / 2, hb["depth"], hb["height"], fill="#f7c59f", stroke=DIM)
sec.rect(-uc["radius"], uc["top_y"] - uc["height"], 2 * uc["radius"], uc["height"], fill="#c9d1dc")
for pl in U["plates"]:
    sec.rect(-pl["radius"], pl["top_y"] - pl["thickness"], 2 * pl["radius"], pl["thickness"], fill="#b9c2cf")
pp = U["pipes"]
for sgn in (-1, 1):
    sec.rect(sgn * pp["ring_radius"] - pp["radius"], pp["bottom_y"], 2 * pp["radius"], pp["top_y"] - pp["bottom_y"], fill="#98a3b3")
sec.rect(-k["radius"], k["top_y"] - k["height"], 2 * k["radius"], k["height"], fill="#c9d1dc")
sec.poly([(-kc["radius_top"], kc["top_y"]), (kc["radius_top"], kc["top_y"]), (kc["radius_bottom"], kc["top_y"] - kc["height"]), (-kc["radius_bottom"], kc["top_y"] - kc["height"])], fill="#c9d1dc")
sec.circle(0, U["keel_emitter"]["y"], U["keel_emitter"]["radius"], fill="#dff6ff")
# dome shell as an arc (thin)
sec.half_ellipse_up(0, 0, H["dome"]["base_radius"], H["dome"]["height"], stroke=GLASS, fill="none", sw=3)
sec.circle(-H["dome_collar"]["ring_radius"], H["dome_collar"]["y"], H["dome_collar"]["tube_radius"], fill="#b9c2cf")
sec.circle(H["dome_collar"]["ring_radius"], H["dome_collar"]["y"], H["dome_collar"]["tube_radius"], fill="#b9c2cf")
sec.poly([(-ct["radius_base"], 0), (ct["radius_base"], 0), (ct["radius_top"], ct["height"]), (-ct["radius_top"], ct["height"])], fill="#ffffff")
sec.line(-9000, 0, 9500, 0, stroke=DIM, sw=0.7, dash="8,5")

# plate labels
for i, pl in enumerate(U["plates"]):
    sec.leader(pl["radius"], pl["top_y"] - pl["thickness"] / 2, 930, 300 + i * 26,
               f"Plate {i+1}: R {pl['radius']:,} m, t {pl['thickness']} m, top y {pl['top_y']:,}")
sec.leader(uc["radius"], uc["top_y"] - uc["height"] * 0.55, 930, 300 + 5 * 26, f"Core: R {uc['radius']:,} m, {uc['height']:,} m tall")
sec.leader(pp["ring_radius"], (pp["top_y"] + pp["bottom_y"]) / 2, 930, 300 + 6 * 26, f"Pipes ×{pp['count']}: Ø {2*pp['radius']} m on R {pp['ring_radius']:,} m")
sec.leader(k["radius"], k["top_y"] - k["height"] / 2, 930, 300 + 7 * 26, f"Keel: R {k['radius']:,} m, {k['height']:,} m tall")
sec.leader(kc["radius_bottom"], kc["top_y"] - kc["height"], 930, 300 + 8 * 26, f"Keel cone: R {kc['radius_top']:,} → {kc['radius_bottom']} m over {kc['height']:,} m")
sec.leader(U["keel_emitter"]["radius"], U["keel_emitter"]["y"], 930, 300 + 9 * 26, f"Emitter sphere: R {U['keel_emitter']['radius']} m at y {U['keel_emitter']['y']:,}")
sec.leader(H["deck_rim_band"]["radius"], hb["y"], 930, 300 + 10 * 26, f"Hangar bays ×{hb['count']}: {hb['width']:,} × {hb['height']} m, {hb['depth']} m deep")
sec.leader(H["dome"]["base_radius"] * 0.7, H["dome"]["height"] * 0.72, 930, 300 + 11 * 26, f"Dome: ellipsoid R {H['dome']['base_radius']:,} m, h {H['dome']['height']:,} m, {H['dome_ribs']['count']} ribs")
sec.leader(H["dome_collar"]["ring_radius"], H["dome_collar"]["y"], 930, 300 + 12 * 26, f"Dome collar: torus R {H['dome_collar']['ring_radius']:,} m, tube Ø {2*H['dome_collar']['tube_radius']} m")
sec.leader(H["deck_rim_band"]["radius"], H["deck_rim_band"]["top_y"] - H["deck_rim_band"]["height"] / 2 - 200, 930, 300 + 13 * 26, f"Rim band: R {H['deck_rim_band']['radius']:,} m, h {H['deck_rim_band']['height']} m (orange light band)")

sec.dim_v(0, H["dome"]["height"], -10200, f"{fmt(H['dome']['height'])}", side=-1)
sec.dim_v(-H["deck"]["thickness"], 0, -10200, f"{fmt(H['deck']['thickness'])}", side=-1)
sec.dim_v(keel_bottom, -H["deck"]["thickness"], -9200, f"{fmt(-H['deck']['thickness'] - keel_bottom)} below deck", side=-1)
sec.dim_h(-H["deck"]["radius"], H["deck"]["radius"], H["dome"]["height"] + 600, f"HUB DECK Ø {fmt(2*H['deck']['radius'])}")

# leg detail inset (page-relative at lower-left)
leg = Sheet(sec.x0 + 715, sec.y0 + 660, 470, 330, 470 / 40000, 30, 22, "", "")
leg.add(f'<rect x="{leg.x0}" y="{leg.y0}" width="{leg.w}" height="{leg.h}" fill="#f2f5f9" stroke="{INK}" stroke-width="1"/>')
leg.ptext(10, 20, "DETAIL B — LEG (one of three, in its own vertical plane)", 12, weight="700")
ax0, fx0 = L["attach"]["ring_radius"], L["foot"]["ring_radius"]
leg.poly([(ax0 - L["radius_attach"], L["attach"]["y"]), (ax0 + L["radius_attach"], L["attach"]["y"]), (fx0 + L["radius_foot"], L["foot"]["y"]), (fx0 - L["radius_foot"], L["foot"]["y"])], fill=FILL2)
leg.circle(ax0, L["attach"]["y"], L["knee_radius"], fill=FILL2)
leg.rect(fx0 - L["foot_pad"]["radius"], L["foot"]["y"] - L["foot_pad"]["thickness"], 2 * L["foot_pad"]["radius"], L["foot_pad"]["thickness"], fill=FILL2)
bx = ax0 + (fx0 - ax0) * L["brace"]["leg_frac"]
by = L["attach"]["y"] + (L["foot"]["y"] - L["attach"]["y"]) * L["brace"]["leg_frac"]
leg.line(bx, by, k["radius"], L["brace"]["keel_y"], sw=2)
leg.rect(0, k["top_y"] - k["height"], k["radius"], k["height"], fill="#c9d1dc")
leg.line(0, 0, 0, L["foot"]["y"] - 1500, stroke=HID, sw=0.7, dash="6,4")
leg.line(-500, L["attach"]["y"], 13000, L["attach"]["y"], stroke=DIM, sw=0.6, dash="4,3")
leg.dim_h(ax0, fx0, L["foot"]["y"] - 1100, f"ΔR {fmt(fx0-ax0)}", above=False)
leg.dim_v(L["foot"]["y"], L["attach"]["y"], fx0 + 2200, f"ΔY {fmt(L['attach']['y']-L['foot']['y'])}")
leg.leader(ax0, L["attach"]["y"], 250, 60, f"Knee R {L['knee_radius']} m at R {ax0:,}, y {L['attach']['y']:,}")
leg.leader(fx0, L["foot"]["y"], 250, 80, f"Foot pad R {L['foot_pad']['radius']} m at R {fx0:,}, y {L['foot']['y']:,}")
leg.leader(bx, by, 250, 100, f"Brace Ø {2*L['brace']['radius']} m to keel at y {L['brace']['keel_y']:,}")
leg.ptext(10, 320, f"Leg length {fmt(leg_len)}   rake {leg_rake:.1f}° from vertical   Ø {2*L['radius_attach']} → {2*L['radius_foot']} m", 11.5, mono=True)

# ----------------------------------------------------------------------------
# Sheet 4: PARTS TABLE + TITLE BLOCK
# ----------------------------------------------------------------------------
TW, TH = 1200, 1000
tab = Sheet(20 + PW + 20, 20 + PH + 20, TW, TH, 1, 0, 0, "PARTS LIST, ENVELOPE AND SCALE BASIS", "IDs match the layer names in the 3D viewer (spec.json is the single source of truth).")
tab.frame(4)

parts = [
    ("H-01", "Hub deck", 1, f"Ø {2*H['deck']['radius']:,} × {H['deck']['thickness']:,} thick", "hull_light / hull", "0 to −1,400"),
    ("H-02", "Deck rim band + lip", 1, f"Ø {2*H['deck_rim_band']['radius']:,} × {H['deck_rim_band']['height']} ; lip Ø {2*H['deck_lip']['radius']:,}", "hull / rim_light", "−200 to −950"),
    ("H-03", "Hangar bays", H["hangar_bays"]["count"], f"{H['hangar_bays']['width']:,} × {H['hangar_bays']['height']} × {H['hangar_bays']['depth']} deep", "trim / rim_light", str(H["hangar_bays"]["y"])),
    ("H-04", "Main dome (glass)", 1, f"ellipsoid Ø {2*H['dome']['base_radius']:,} × h {H['dome']['height']:,}", "glass", f"0 to {H['dome']['height']:,}"),
    ("H-05", "Dome collar + ribs", 1, f"torus R {H['dome_collar']['ring_radius']:,}; {H['dome_ribs']['count']} ribs Ø {2*H['dome_ribs']['tube_radius']}", "hull_light", "≈0"),
    ("H-06", "Council spire", 1, f"Ø {2*ct['radius_base']:,} → {2*ct['radius_top']} , h {OVERALL['council_tower_height']:,}", "city / city_glow", f"0 to {OVERALL['council_tower_height']:,}"),
    ("H-07", "Hub city towers", H["city"]["tower_count"], f"{H['city']['footprint_min']}–{H['city']['footprint_max']} footprint, {H['city']['height_min']}–{H['city']['height_max']:,} tall (seed {H['city']['seed']})", "city / city_glow", f"0 to ≤{H['city']['height_max']:,}"),
    ("H-08", "Hub low-rise blocks", H["city"]["lowrise_count"], f"{H['city']['lowrise_height_min']}–{H['city']['lowrise_height_max']} tall", "city", "0 to 360"),
    ("H-09", "Antenna mast", 1, f"h {an['height']:,}, Ø {2*an['radius_base']} → {2*an['radius_top']}; 3 rings, 1 dish, beacon R {an['beacon_radius']}", "hull_dark / beacon", f"{an['base_y']:,} to {antenna_top:,}"),
    ("P-01", "Pod deck", 3, f"Ø {2*P['deck']['radius']:,} × {P['deck']['thickness']} thick; rim Ø {2*P['deck_rim_band']['radius']:,}", "hull_light / hull", f"0 to −{P['deck']['thickness']}"),
    ("P-02", "Pod dome (glass)", 3, f"ellipsoid Ø {2*P['dome']['base_radius']:,} × h {P['dome']['height']:,}", "glass", f"0 to {P['dome']['height']:,}"),
    ("P-03", "Pod city", 3, f"{P['city']['tower_count']} towers + {P['city']['lowrise_count']} low-rise per pod", "city / city_glow", f"0 to ≤{P['city']['height_max']:,}"),
    ("P-04", "Pod understructure", 3, f"core R {P['understructure']['core_radius']:,}; 2 plates; spike h {P['understructure']['spike']['height']:,}", "hull_dark", f"−{P['deck']['thickness']} to {P['understructure']['spike']['top_y']-P['understructure']['spike']['height']:,}"),
    ("B-01", "Bridge tube (transit)", 3, f"Ø {2*B['tube']['radius_hub']} → {2*B['tube']['radius_pod']}, span {bridge_len:,}, {B['tube']['rib_count']} ribs", "bridge_tube", str(B["tube"]["y"])),
    ("B-02", "Bridge causeway + rails", 3, f"{B['causeway']['width']:,} wide × {B['causeway']['thickness']} thick", "hull_light / trim", "0"),
    ("B-03", "Bridge struts", 3 * B["struts"]["count"], f"Ø {2*B['struts']['radius']}, spread {B['struts']['spread']}", "hull_dark", "below tube"),
    ("U-01", "Understructure core", 1, f"Ø {2*uc['radius']:,} × {uc['height']:,}", "hull_dark", f"{uc['top_y']:,} to {uc['top_y']-uc['height']:,}"),
    ("U-02", "Metallic plates", len(U["plates"]), "Ø " + " / ".join(f"{2*p['radius']:,}" for p in U["plates"]), "hull_dark", f"{U['plates'][0]['top_y']:,} to {U['plates'][-1]['top_y']-U['plates'][-1]['thickness']:,}"),
    ("U-03", "Service pipes", pp["count"], f"Ø {2*pp['radius']} on R {pp['ring_radius']:,}", "trim", f"{pp['top_y']:,} to {pp['bottom_y']:,}"),
    ("U-04", "Machinery blocks", mb["count"], f"{mb['width']:,} × {mb['height']} × {mb['depth']:,} on R {mb['ring_radius']:,}", "hull", f"{mb['top_y']:,} to {mb['top_y']-mb['height']:,}"),
    ("U-05", "Keel + cone", 1, f"Ø {2*k['radius']:,} × {k['height']:,}; cone to Ø {2*kc['radius_bottom']:,}", "hull_dark", f"{k['top_y']:,} to {kc['top_y']-kc['height']:,}"),
    ("U-06", "Keel emitter", 1, f"sphere R {U['keel_emitter']['radius']}", "beacon", f"{U['keel_emitter']['y']:,}"),
    ("L-01", "Legs", 3, f"{leg_len:,.0f} long, rake {leg_rake:.1f}°, Ø {2*L['radius_attach']} → {2*L['radius_foot']}", "hull_dark", f"{L['attach']['y']:,} to {L['foot']['y']:,}"),
    ("L-02", "Knee joints", 3, f"sphere R {L['knee_radius']}", "hull", str(L["attach"]["y"])),
    ("L-03", "Foot pads", 3, f"Ø {2*L['foot_pad']['radius']:,} × {L['foot_pad']['thickness']}", "hull", f"{L['foot']['y']:,}"),
    ("L-04", "Leg braces", 3, f"Ø {2*L['brace']['radius']} from 42 % down the leg to keel at y {L['brace']['keel_y']:,}", "hull_dark", "—"),
]
cols = [(18, "ID"), (70, "Part"), (250, "Qty"), (290, "Key dimensions (m)"), (760, "Material"), (930, "Y range (m)")]
y = 78
for x, name in cols:
    tab.ptext(x, y, name, 12, weight="700")
tab.add(f'<line x1="{tab.x0+14}" y1="{tab.y0+y+6}" x2="{tab.x0+TW-14}" y2="{tab.y0+y+6}" stroke="{INK}" stroke-width="1"/>')
y += 24
for row in parts:
    for (x, _), val in zip(cols, row):
        tab.ptext(x, y, str(val), 11.5, mono=(x in (18, 250, 290, 930)))
    y += 21
y += 10
tab.add(f'<line x1="{tab.x0+14}" y1="{tab.y0+y-14}" x2="{tab.x0+TW-14}" y2="{tab.y0+y-14}" stroke="{INK}" stroke-width="1"/>')
tab.ptext(18, y + 6, "OVERALL ENVELOPE (computed)", 13, weight="700")
env_rows = [
    f"Overall height, leg feet → antenna tip: {fmt(OVERALL['height_total'])}",
    f"Deck → antenna tip: {fmt(antenna_top)}     Deck → keel emitter: {fmt(-keel_bottom)}     Deck → leg feet: {fmt(-foot_bottom)}",
    f"Plan envelope: {fmt(OVERALL['width_x_extent'])} (X) × {fmt(OVERALL['width_z_extent'])} (Z);  bounding circle Ø {fmt(2*overall_radius)}",
    f"Hub deck Ø {fmt(2*H['deck']['radius'])};  main dome Ø {fmt(2*H['dome']['base_radius'])} × {fmt(H['dome']['height'])} high;  pod decks Ø {fmt(2*P['deck']['radius'])} at {fmt(P['center_distance'])} from centre",
]
for i, r in enumerate(env_rows):
    tab.ptext(18, y + 28 + i * 18, r, 11.5, mono=True)
y += 28 + len(env_rows) * 18 + 12
tab.ptext(18, y, "SCALE BASIS (why these numbers)", 13, weight="700")
basis = SPEC["scale_basis"]["summary"]
# naive wrap
words, lines, cur = basis.split(), [], ""
for w in words:
    if len(cur) + len(w) + 1 > 160:
        lines.append(cur); cur = w
    else:
        cur = (cur + " " + w).strip()
lines.append(cur)
for i, ln in enumerate(lines):
    tab.ptext(18, y + 20 + i * 16, ln, 11.5, color="#2d3748")
y += 20 + len(lines) * 16 + 8
tab.ptext(18, y, "Confidence: " + SPEC["scale_basis"]["confidence"], 11, color="#4a5568")
y += 24
tab.ptext(18, y, "REFERENCES (episodes with the exterior establishing shot)", 13, weight="700")
for i, r in enumerate(SPEC["canonical_references"]):
    tab.ptext(18, y + 20 + i * 16, f"{r['id']}  {r['title']} — {r['note']}", 11, color="#2d3748")

# ----------------------------------------------------------------------------
# Assemble
# ----------------------------------------------------------------------------
W = 20 + PW + 20 + EW + 20
Hh = 20 + PH + 20 + max(SH_, TH) + 20
svg = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{Hh}" viewBox="0 0 {W} {Hh}" font-family="Inter, Helvetica Neue, Arial, sans-serif">',
    "<defs>",
    f'<marker id="arrS" markerWidth="8" markerHeight="8" refX="1" refY="4" orient="auto-start-reverse"><path d="M8,0 L0,4 L8,8 z" fill="{DIM}"/></marker>',
    f'<marker id="arrE" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="{DIM}"/></marker>',
    "</defs>",
    f'<rect width="{W}" height="{Hh}" fill="#e3e7ee"/>',
    plan.render(), elev.render(), sec.render(), leg.render(), tab.render(),
    "</svg>",
]
out = ROOT / "schematic" / "citadel_schematic.svg"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(svg))
print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB) and overall_dimensions.json")
print(json.dumps(OVERALL, indent=2))
