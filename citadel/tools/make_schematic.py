#!/usr/bin/env python3
"""Generate the dimensioned schematic (SVG) of the Citadel of Ricks from spec.json (v2).

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

PP, MP, SP, B, L, AN = (SPEC["pod_profile"], SPEC["main_pod"], SPEC["satellite_pods"], SPEC["bridges"], SPEC["legs"], SPEC["antenna"])
R = MP["dome_radius"]
Rs = R * SP["scale"]

# ----------------------------------------------------------------------------
# Derived numbers
# ----------------------------------------------------------------------------
def pod_top(Rp):
    return PP["dome"]["base_y_frac"] * Rp + PP["dome"]["height_frac"] * Rp

def pod_bottom(Rp):
    return (PP["nub"]["top_y_frac"] - PP["nub"]["height_frac"]) * Rp

def collar_r(Rp):
    return PP["collar"]["radius_frac"] * Rp

def hull_r_at(Rp, y):
    f = y / Rp
    h = PP["hull"]
    for (r0, y0), (r1, y1) in zip(h, h[1:]):
        if y1 <= f <= y0:
            u = (y0 - f) / ((y0 - y1) or 1)
            return (r0 + (r1 - r0) * u) * Rp
    return h[0][0] * Rp

top = pod_top(R)
foot_bottom = L["foot"]["y"] - L["foot_pad"]["thickness"]
antenna_tip = AN["top_y"] - AN["length"] - AN["beacon_radius"]
bottom = min(foot_bottom, antenna_tip)
dx = L["foot"]["ring_radius"] - L["attach"]["ring_radius"]
dy = L["attach"]["y"] - L["foot"]["y"]
leg_len = math.hypot(dx, dy)
leg_rake = math.degrees(math.atan2(dx, dy))
bridge_span = (SP["center_distance"] - hull_r_at(Rs, B["attach_y_satellite"])) - hull_r_at(R, B["attach_y_main"])

def extent(axis):
    lo, hi = -collar_r(R), collar_r(R)
    circles = [(SP["center_distance"], a, collar_r(Rs)) for a in SP["azimuths_deg"]]
    circles += [(L["foot"]["ring_radius"], a, L["foot_pad"]["radius"]) for a in L["azimuths_deg"]]
    for dist, a, r in circles:
        c = math.cos(math.radians(a)) if axis == "x" else math.sin(math.radians(a))
        lo, hi = min(lo, dist * c - r), max(hi, dist * c + r)
    return hi - lo

overall_radius = max(SP["center_distance"] + collar_r(Rs), L["foot"]["ring_radius"] + L["foot_pad"]["radius"])
OVERALL = {
    "units": "meters",
    "height_total": top - bottom,
    "main_dome_top_y": top,
    "main_pod_bottom_y": pod_bottom(R),
    "depth_to_leg_feet": -foot_bottom,
    "depth_to_antenna_tip": -antenna_tip,
    "width_x_extent": extent("x"),
    "width_z_extent": extent("z"),
    "bounding_circle_diameter_plan": 2 * overall_radius,
    "main_dome_diameter": 2 * R,
    "main_dome_height": PP["dome"]["height_frac"] * R,
    "main_collar_diameter": 2 * collar_r(R),
    "main_pod_height": top - pod_bottom(R),
    "satellite_dome_diameter": 2 * Rs,
    "satellite_collar_diameter": 2 * collar_r(Rs),
    "satellite_center_distance": SP["center_distance"],
    "bridge_clear_span": round(bridge_span),
    "leg_length": round(leg_len),
    "leg_rake_deg": round(leg_rake, 1),
    "antenna_length": AN["length"],
    "council_tower_height": MP["council_tower"]["height"] + MP["council_tower"]["crown_height"],
}
(ROOT / "overall_dimensions.json").write_text(json.dumps(OVERALL, indent=2) + "\n")

# ----------------------------------------------------------------------------
# SVG helpers
# ----------------------------------------------------------------------------
INK, DIM, HID, GLASS, FILL, FILL2, CUT = "#1d2330", "#b3412a", "#8a94a6", "#3ea99a", "#e9edf3", "#cfd6e0", "#c9d1dc"
SANS = "'Inter','Helvetica Neue',Arial,sans-serif"
MONO = "'JetBrains Mono','Consolas',monospace"

def fmt(v):
    return f"{v:,.0f} m"


class Sheet:
    def __init__(self, x0, y0, w, h, scale, ox, oy, title, subtitle):
        self.x0, self.y0, self.w, self.h, self.s, self.ox, self.oy = x0, y0, w, h, scale, ox, oy
        self.out, self.title, self.subtitle = [], title, subtitle

    def X(self, x): return self.x0 + self.ox + x * self.s
    def Y(self, y): return self.y0 + self.oy - y * self.s
    def add(self, s): self.out.append(s)

    def circle(self, cx, cy, r, stroke=INK, fill="none", dash="", sw=1.6):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<circle cx="{self.X(cx):.1f}" cy="{self.Y(cy):.1f}" r="{r*self.s:.1f}" stroke="{stroke}" fill="{fill}" stroke-width="{sw}"{d}/>')

    def rect(self, x, y, w, h, stroke=INK, fill="none", dash="", sw=1.6):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{self.X(x):.1f}" y="{self.Y(y+h):.1f}" width="{w*self.s:.1f}" height="{h*self.s:.1f}" stroke="{stroke}" fill="{fill}" stroke-width="{sw}"{d}/>')

    def line(self, x1, y1, x2, y2, stroke=INK, sw=1.6, dash=""):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{self.X(x1):.1f}" y1="{self.Y(y1):.1f}" x2="{self.X(x2):.1f}" y2="{self.Y(y2):.1f}" stroke="{stroke}" stroke-width="{sw}"{d}/>')

    def poly(self, pts, stroke=INK, fill="none", sw=1.6, dash="", close=True):
        d = f' stroke-dasharray="{dash}"' if dash else ""
        p = " ".join(f"{self.X(x):.1f},{self.Y(y):.1f}" for x, y in pts)
        self.add(f'<{"polygon" if close else "polyline"} points="{p}" stroke="{stroke}" fill="{fill}" stroke-width="{sw}"{d}/>')

    def half_ellipse_up(self, cx, base_y, rx, ry, stroke=INK, fill="none", sw=1.6):
        x1, x2, y = self.X(cx - rx), self.X(cx + rx), self.Y(base_y)
        self.add(f'<path d="M{x1:.1f},{y:.1f} A{rx*self.s:.1f},{ry*self.s:.1f} 0 0 1 {x2:.1f},{y:.1f} Z" stroke="{stroke}" fill="{fill}" stroke-width="{sw}"/>')

    def text(self, x, y, s, size=13, anchor="start", color=INK, weight="normal", rotate=0, mono=False):
        rot = f' transform="rotate({rotate} {self.X(x):.1f} {self.Y(y):.1f})"' if rotate else ""
        self.add(f'<text x="{self.X(x):.1f}" y="{self.Y(y):.1f}" font-size="{size}" text-anchor="{anchor}" fill="{color}" font-weight="{weight}" font-family="{MONO if mono else SANS}"{rot}>{s}</text>')

    def ptext(self, px, py, s, size=13, anchor="start", color=INK, weight="normal", mono=False):
        self.add(f'<text x="{self.x0+px:.1f}" y="{self.y0+py:.1f}" font-size="{size}" text-anchor="{anchor}" fill="{color}" font-weight="{weight}" font-family="{MONO if mono else SANS}">{s}</text>')

    def dim_h(self, x1, x2, y, label, above=True, label_x=None):
        X1, X2, Y = self.X(x1), self.X(x2), self.Y(y)
        self.add(f'<line x1="{X1:.1f}" y1="{Y:.1f}" x2="{X2:.1f}" y2="{Y:.1f}" stroke="{DIM}" stroke-width="1.1" marker-start="url(#arrS)" marker-end="url(#arrE)"/>')
        ty = Y - 5 if above else Y + 15
        tx, anchor = ((X1 + X2) / 2, "middle") if label_x is None else (self.X(label_x), "start")
        self.add(f'<text x="{tx:.1f}" y="{ty:.1f}" font-size="12" text-anchor="{anchor}" fill="{DIM}" font-family="{SANS}">{label}</text>')

    def dim_v(self, y1, y2, x, label, side=1):
        X, Y1, Y2 = self.X(x), self.Y(y1), self.Y(y2)
        self.add(f'<line x1="{X:.1f}" y1="{Y1:.1f}" x2="{X:.1f}" y2="{Y2:.1f}" stroke="{DIM}" stroke-width="1.1" marker-start="url(#arrS)" marker-end="url(#arrE)"/>')
        self.add(f'<text x="{X + 6*side:.1f}" y="{(Y1+Y2)/2+4:.1f}" font-size="12" text-anchor="{"start" if side > 0 else "end"}" fill="{DIM}" font-family="{SANS}">{label}</text>')

    def ext(self, x1, y1, x2, y2): self.line(x1, y1, x2, y2, stroke=DIM, sw=0.7)

    def leader(self, x, y, px, py, label, anchor="start"):
        X, Y, LX, LY = self.X(x), self.Y(y), self.x0 + px, self.y0 + py
        self.add(f'<line x1="{X:.1f}" y1="{Y:.1f}" x2="{LX:.1f}" y2="{LY:.1f}" stroke="{INK}" stroke-width="0.8"/>')
        self.add(f'<circle cx="{X:.1f}" cy="{Y:.1f}" r="2.2" fill="{INK}"/>')
        self.add(f'<text x="{LX + (4 if anchor == "start" else -4):.1f}" y="{LY+4:.1f}" font-size="11.5" text-anchor="{anchor}" fill="{INK}" font-family="{SANS}">{label}</text>')

    def frame(self, n):
        self.add(f'<rect x="{self.x0}" y="{self.y0}" width="{self.w}" height="{self.h}" fill="#fbfcfe" stroke="{INK}" stroke-width="2"/>')
        self.ptext(18, 30, f"SHEET {n}  ·  {self.title}", 20, weight="700")
        self.ptext(18, 50, self.subtitle, 12.5, color="#4a5568")
        self.ptext(self.w - 18, 30, f"Scale: 1 px = {1/self.s:,.0f} m", 12, anchor="end", color="#4a5568", mono=True)

    def render(self):
        cid = f"clip{abs(hash((self.x0, self.y0)))}"
        return (f'<clipPath id="{cid}"><rect x="{self.x0}" y="{self.y0}" width="{self.w}" height="{self.h}"/></clipPath>'
                f'<g clip-path="url(#{cid})">' + "\n".join(self.out) + "</g>")


# pod silhouette helpers ------------------------------------------------------
def pod_silhouette(sh, cx, cy, Rp, fill_hull=FILL, fill_dark=FILL2, near=True, section=False):
    """Draw a pod's elevation/section at centre (cx, cy): collar, hull, plates, core, nub, dome."""
    C, hull, N, K = PP["collar"], PP["hull"], PP["nub"], PP["core"]
    cr, ch, ctop = C["radius_frac"] * Rp, C["height_frac"] * Rp, C["top_y_frac"] * Rp
    f_d = CUT if section else fill_dark
    f_h = CUT if section else fill_hull
    # hull (revolved profile mirrored)
    right = [(cx + r * Rp, cy + y * Rp) for r, y in hull]
    left = [(cx - r * Rp, cy + y * Rp) for r, y in reversed(hull)]
    sh.poly(right + left, fill=f_h)
    # plates
    for r, yt, t in PP["plates"]:
        sh.rect(cx - r * Rp, cy + (yt - t) * Rp, 2 * r * Rp, t * Rp, fill=f_d)
    # core + nub
    sh.rect(cx - K["radius_frac"] * Rp, cy + K["bottom_y_frac"] * Rp, 2 * K["radius_frac"] * Rp, (K["top_y_frac"] - K["bottom_y_frac"]) * Rp, fill=f_d)
    sh.poly([(cx - N["radius_top_frac"] * Rp, cy + N["top_y_frac"] * Rp), (cx + N["radius_top_frac"] * Rp, cy + N["top_y_frac"] * Rp),
             (cx + N["radius_bottom_frac"] * Rp, cy + (N["top_y_frac"] - N["height_frac"]) * Rp), (cx - N["radius_bottom_frac"] * Rp, cy + (N["top_y_frac"] - N["height_frac"]) * Rp)], fill=f_d)
    # collar
    sh.rect(cx - cr, cy + ctop - ch, 2 * cr, ch, fill=f_d)
    # dome
    sh.half_ellipse_up(cx, cy + PP["dome"]["base_y_frac"] * Rp, Rp, PP["dome"]["height_frac"] * Rp, stroke=GLASS, fill="none" if section else "#d9f3ee", sw=3 if section else 1.6)


# ----------------------------------------------------------------------------
# Sheet 1: PLAN
# ----------------------------------------------------------------------------
PW, PH = 1200, 1080
plan = Sheet(20, 20, PW, PH, 1200 / 60000, PW / 2, PH / 2 + 40, "PLAN VIEW (from above)",
             "+X to the right, +Z up the page. Azimuths counter-clockwise from +X. Legs and antenna shown hidden (dashed).")
plan.frame(1)
for a in L["azimuths_deg"]:
    r = math.radians(a)
    ax, az = L["attach"]["ring_radius"] * math.cos(r), L["attach"]["ring_radius"] * math.sin(r)
    fx, fz = L["foot"]["ring_radius"] * math.cos(r), L["foot"]["ring_radius"] * math.sin(r)
    plan.line(ax, az, fx, fz, stroke=HID, sw=3.4, dash="10,6")
    plan.circle(fx, fz, L["foot_pad"]["radius"], stroke=HID, dash="4,3", sw=1)
    plan.text(fx * 1.1, fz * 1.1, f"LEG {L['azimuths_deg'].index(a)+1} ({a}°)", 11, anchor="middle", color=HID)
for r_, yt, t in PP["plates"]:
    plan.circle(0, 0, r_ * R, stroke=HID, dash="5,4", sw=0.8)
# bridges
for i, a in enumerate(SP["azimuths_deg"]):
    r = math.radians(a)
    x1, x2 = hull_r_at(R, B["attach_y_main"]) - 250, SP["center_distance"] - hull_r_at(Rs, B["attach_y_satellite"]) + 250
    hw = (B["tube_radius_main"] + B["tube_radius_satellite"]) / 2
    pts = [(u * math.cos(r) - v * math.sin(r), u * math.sin(r) + v * math.cos(r)) for (u, v) in [(x1, -hw), (x2, -hw), (x2, hw), (x1, hw)]]
    plan.poly(pts, fill="#d7ddd0")
# main pod
plan.circle(0, 0, collar_r(R), fill=FILL2)
plan.circle(0, 0, R, stroke=GLASS, fill="#d9f3ee", sw=2)
for i in range(PP["ribs"]["count_main"]):
    r = math.radians(i * 360 / PP["ribs"]["count_main"])
    plan.line(0, 0, R * math.cos(r), R * math.sin(r), stroke=GLASS, sw=0.5)
plan.circle(0, 0, MP["council_tower"]["radius_base"], fill="#ffffff")
for i in range(PP["hangar_bays"]["count"]):
    a = math.radians(i * 360 / PP["hangar_bays"]["count"] + PP["hangar_bays"]["phase_deg"])
    w, rr = PP["hangar_bays"]["width_frac"] * R, collar_r(R)
    tx, tz = -math.sin(a), math.cos(a)
    plan.line(rr * math.cos(a) - tx * w / 2, rr * math.sin(a) - tz * w / 2, rr * math.cos(a) + tx * w / 2, rr * math.sin(a) + tz * w / 2, stroke=DIM, sw=3)
plan.circle(0, 0, AN["rings"][0]["radius"], stroke=HID, dash="3,3", sw=0.8)
# satellites
for i, a in enumerate(SP["azimuths_deg"]):
    r = math.radians(a)
    cx, cz = SP["center_distance"] * math.cos(r), SP["center_distance"] * math.sin(r)
    plan.circle(cx, cz, collar_r(Rs), fill=FILL2)
    plan.circle(cx, cz, Rs, stroke=GLASS, fill="#d9f3ee", sw=2)
    for k in range(PP["ribs"]["count_satellite"]):
        rr = math.radians(k * 360 / PP["ribs"]["count_satellite"])
        plan.line(cx, cz, cx + Rs * math.cos(rr), cz + Rs * math.sin(rr), stroke=GLASS, sw=0.5)
    plan.text(cx, cz + collar_r(Rs) + 1000, f"POD {i+1} ({a}°)", 12, anchor="middle", weight="700")
plan.line(-26000, 0, 26000, 0, stroke=HID, sw=0.6, dash="12,6")
plan.line(0, -26000, 0, 24000, stroke=HID, sw=0.6, dash="12,6")
plan.text(25500, 500, "+X", 12, color=HID)
plan.text(500, 23000, "+Z", 12, color=HID)
plan.dim_h(-collar_r(R), collar_r(R), -collar_r(R) - 1100, f"MAIN COLLAR Ø {fmt(2*collar_r(R))}", above=False)
plan.dim_h(-R, R, R + 1500, f"MAIN DOME Ø {fmt(2*R)}", label_x=1200)
px, pz = SP["center_distance"] * math.cos(math.radians(330)), SP["center_distance"] * math.sin(math.radians(330))
plan.dim_h(px - Rs, px + Rs, pz - collar_r(Rs) - 900, f"SATELLITE DOME Ø {fmt(2*Rs)}", above=False)
plan.line(0, 0, px, pz, stroke=DIM, sw=1.1)
plan.text(px * 0.32 - 2800, pz * 0.32 + 1800, f"CENTRE DISTANCE {fmt(SP['center_distance'])}", 12, color=DIM, rotate=30)
plan.dim_h(-overall_radius, overall_radius, 23800, f"BOUNDING CIRCLE Ø {fmt(2*overall_radius)}")
plan.ext(-overall_radius, 23800, -overall_radius, 0); plan.ext(overall_radius, 23800, overall_radius, 0)
plan.circle(0, 0, overall_radius, stroke=DIM, dash="2,6", sw=0.8)
plan.text(px * 0.62 + 1500, pz * 0.62 + 2200, f"BRIDGE SPAN {fmt(bridge_span)}", 11, color=DIM, rotate=30)
plan.ptext(18, PH - 62, "Solid = above the plate stack. Dashed grey = plates, legs and antenna below. Orange ticks = hangar bays in the collar.", 11.5, color="#4a5568")
plan.ptext(18, PH - 44, f"Satellite pods every 120° at {SP['azimuths_deg']}°, {int(SP['scale']*100)} % scale; legs every 120° at {L['azimuths_deg']}° (between the pods).", 11.5, color="#4a5568")
plan.ptext(18, PH - 26, f"Plan envelope: {fmt(OVERALL['width_x_extent'])} (X) × {fmt(OVERALL['width_z_extent'])} (Z).", 11.5, color="#4a5568")
plan.add(f'<rect x="{plan.x0+PW-440}" y="{plan.y0+PH-100}" width="424" height="84" fill="#ffffff" stroke="{INK}" stroke-width="1.4"/>')
plan.ptext(PW - 428, PH - 78, SPEC["name"].upper() + "  —  GENERAL ARRANGEMENT", 14, weight="700")
plan.ptext(PW - 428, PH - 58, "Units: metres · Scale 1:1 · Up = +Y · Origin: main pod, dome base", 11, mono=True)
plan.ptext(PW - 428, PH - 42, f"Spec v{SPEC['version']} · tools/make_schematic.py · 4 sheets", 11, mono=True)
plan.ptext(PW - 428, PH - 26, "Fan reconstruction from written descriptions of the establishing shot; not official.", 10.5, color="#4a5568")

# ----------------------------------------------------------------------------
# Sheet 2: FRONT ELEVATION (camera at +Z; pod 1 nearest)
# ----------------------------------------------------------------------------
EW, EH = 1200, 1080
elev = Sheet(20 + PW + 20, 20, EW, EH, 1200 / 62000, EW / 2, 300, "FRONT ELEVATION",
             "Viewed from +Z (pod 1 nearest the viewer). X to the right, Y up. Main dome base plane is y = 0.")
elev.frame(2)
def sat_xz(a):
    r = math.radians(a); return SP["center_distance"] * math.cos(r), SP["center_distance"] * math.sin(r)
# far legs, far pods, main, near pod
for a in sorted(L["azimuths_deg"], key=lambda a: math.sin(math.radians(a))):
    r = math.radians(a)
    ax, fx = L["attach"]["ring_radius"] * math.cos(r), L["foot"]["ring_radius"] * math.cos(r)
    near = math.sin(r) > 0
    elev.poly([(ax - L["radius_attach"], L["attach"]["y"]), (ax + L["radius_attach"], L["attach"]["y"]), (fx + L["radius_foot"], L["foot"]["y"]), (fx - L["radius_foot"], L["foot"]["y"])], fill=FILL2 if near else "#dfe4ec")
    elev.circle(ax, L["attach"]["y"], L["knee_radius"], fill=FILL2)
    elev.rect(fx - L["foot_pad"]["radius"], L["foot"]["y"] - L["foot_pad"]["thickness"], 2 * L["foot_pad"]["radius"], L["foot_pad"]["thickness"], fill=FILL2)
    bx = ax + (fx - ax) * L["brace"]["leg_frac"]; by = L["attach"]["y"] + (L["foot"]["y"] - L["attach"]["y"]) * L["brace"]["leg_frac"]
    elev.line(bx, by, math.cos(r) * PP["core"]["radius_frac"] * R, L["brace"]["core_y"], sw=2, stroke=INK if near else HID)
for a in SP["azimuths_deg"]:
    cx, cz = sat_xz(a)
    if cz <= 0:
        pod_silhouette(elev, cx, SP["y_offset"], Rs, fill_hull="#e2e7ef", fill_dark="#d3d9e3")
        sx = math.copysign(hull_r_at(R, B["attach_y_main"]), cx); ex = cx - math.copysign(hull_r_at(Rs, B["attach_y_satellite"]), cx)
        elev.rect(min(sx, ex), B["attach_y_main"] - B["tube_radius_main"] - B["sag"] / 2, abs(ex - sx), 2 * B["tube_radius_main"], fill="#d7ddd0")
# antenna (behind main pod's nub, in front of far things)
aTop, aBot = AN["top_y"], AN["top_y"] - AN["length"]
elev.poly([(-AN["radius_top"], aTop), (AN["radius_top"], aTop), (AN["radius_tip"], aBot), (-AN["radius_tip"], aBot)], fill=INK)
for rg in AN["rings"]:
    y = aTop - AN["length"] * rg["y_frac"]; elev.line(-rg["radius"], y, rg["radius"], y, sw=2)
y = aTop - AN["length"] * AN["dish"]["y_frac"]
elev.poly([(-AN["dish"]["radius"], y - AN["dish"]["depth"]), (0, y), (AN["dish"]["radius"], y - AN["dish"]["depth"])], fill="none", sw=1.4, close=False)
elev.circle(0, aBot, AN["beacon_radius"] * 2, fill="#dff6ff")
pod_silhouette(elev, 0, 0, R)
# council spire
ct = MP["council_tower"]; cy0 = PP["dome"]["base_y_frac"] * R
elev.poly([(-ct["radius_base"], cy0), (ct["radius_base"], cy0), (ct["radius_top"], cy0 + ct["height"]), (-ct["radius_top"], cy0 + ct["height"])], fill="#ffffff")
elev.poly([(-ct["radius_top"], cy0 + ct["height"]), (ct["radius_top"], cy0 + ct["height"]), (0, cy0 + ct["height"] + ct["crown_height"])], fill="#ffffff")
for i in range(-9, 10):
    if i == 0: continue
    x = i * 700
    hmax = PP["dome"]["height_frac"] * R * math.sqrt(max(0.0, 1 - (x / R) ** 2)) - 400
    hgt = min(hmax, MP["city"]["height_min"] + (MP["city"]["height_max"] - MP["city"]["height_min"]) * (1 - abs(i) / 10))
    elev.rect(x - 180, cy0, 360, max(hgt, 200), fill="#ffffff", sw=0.8)
for a in SP["azimuths_deg"]:
    cx, cz = sat_xz(a)
    if cz > 0:
        pod_silhouette(elev, cx, SP["y_offset"], Rs)
        elev.text(cx, pod_bottom(Rs) - 1400, "POD 1 (nearest)", 11, anchor="middle")
elev.line(-28000, 0, 28000, 0, stroke=DIM, sw=0.7, dash="8,5")
elev.text(-27800, 350, "DATUM y = 0 (main dome base)", 11, color=DIM)
xr = 21500
elev.dim_v(0, top, xr, f"{fmt(top)} dome top", side=1); elev.ext(0, top, xr, top)
elev.dim_v(pod_bottom(R), 0, xr, f"{fmt(-pod_bottom(R))} main pod below datum", side=1); elev.ext(PP["nub"]["radius_bottom_frac"] * R, pod_bottom(R), xr, pod_bottom(R))
elev.dim_v(antenna_tip, 0, xr + 3200, f"{fmt(-antenna_tip)} antenna tip", side=1); elev.ext(0, antenna_tip, xr + 3200, antenna_tip)
elev.dim_v(foot_bottom, 0, -xr - 3200, f"{fmt(-foot_bottom)} leg feet", side=-1); elev.ext(-L["foot"]["ring_radius"] * math.cos(math.radians(30)), foot_bottom, -xr - 3200, foot_bottom)
elev.dim_v(bottom, top, -xr + 400, f"{fmt(OVERALL['height_total'])} OVERALL", side=-1)
elev.dim_v(0, PP["dome"]["height_frac"] * R, -collar_r(R) - 1600, f"DOME {fmt(PP['dome']['height_frac']*R)}", side=-1)
elev.dim_h(-collar_r(R), collar_r(R), top + 1200, f"MAIN COLLAR Ø {fmt(2*collar_r(R))}", label_x=-collar_r(R) + 600)
elev.ext(-collar_r(R), PP["collar"]["top_y_frac"] * R, -collar_r(R), top + 1200); elev.ext(collar_r(R), PP["collar"]["top_y_frac"] * R, collar_r(R), top + 1200)
elev.dim_h(-OVERALL["width_x_extent"] / 2, OVERALL["width_x_extent"] / 2, foot_bottom - 1600, f"X EXTENT {fmt(OVERALL['width_x_extent'])}", above=False)
elev.leader(0, aTop - AN["length"] * 0.6, EW / 2 + 180, EH - 200, f"Antenna: {fmt(AN['length'])} down the centre, Ø {2*AN['radius_top']} → {2*AN['radius_tip']} m, shorter than the legs")
elev.leader(ct["radius_top"], cy0 + ct["height"], EW / 2 + 150, 90, f"Council spire {fmt(OVERALL['council_tower_height'])}")
fxn = L["foot"]["ring_radius"] * math.cos(math.radians(30))
elev.leader(fxn * 0.5 + 1600, L["attach"]["y"] + (L["foot"]["y"] - L["attach"]["y"]) * 0.5, EW - 470, EH - 110, f"Leg: {fmt(leg_len)}, rake {leg_rake:.0f}°, Ø {2*L['radius_attach']} → {2*L['radius_foot']} m")
elev.leader(collar_r(R), PP["collar"]["top_y_frac"] * R - PP["collar"]["height_frac"] * R / 2, EW - 300, 150, f"Raised collar {fmt(PP['collar']['height_frac']*R)} tall")
elev.leader(PP["plates"][2][0] * R, PP["plates"][2][1] * R, EW - 300, 190, f"{len(PP['plates'])} metallic plates")
elev.ptext(18, EH - 26, "Pods 2 and 3 sit behind the main pod in this view; their bridges are foreshortened. Leg 3 (270°) is directly behind the antenna.", 11.5, color="#4a5568")

# ----------------------------------------------------------------------------
# Sheet 3: MAIN POD SECTION + PROFILE TABLE
# ----------------------------------------------------------------------------
SW_, SH_ = 1200, 1000
sec = Sheet(20, 20 + PH + 20, SW_, SH_, 1200 / 36000, 520, 330, "MAIN POD SECTION A–A and PROFILE",
            "Vertical section through the main pod on the X–Y plane. Solid = cut material. The same profile at 60 % is each satellite pod.")
sec.frame(3)
pod_silhouette(sec, 0, 0, R, section=True)
sec.poly([(-ct["radius_base"], cy0), (ct["radius_base"], cy0), (ct["radius_top"], cy0 + ct["height"]), (-ct["radius_top"], cy0 + ct["height"])], fill="#ffffff")
sec.rect(collar_r(R) - PP["hangar_bays"]["depth_frac"] * R, PP["hangar_bays"]["y_frac"] * R - PP["hangar_bays"]["height_frac"] * R / 2, PP["hangar_bays"]["depth_frac"] * R, PP["hangar_bays"]["height_frac"] * R, fill="#f7c59f", stroke=DIM)
sec.line(-12000, 0, 12000, 0, stroke=DIM, sw=0.7, dash="8,5")
# antenna stub
sec.poly([(-AN["radius_top"], aTop), (AN["radius_top"], aTop), (AN["radius_top"] * 0.9, aTop - 1500), (-AN["radius_top"] * 0.9, aTop - 1500)], fill=INK)
rows = [
    (f"Dome: ellipsoid R {R:,} m, h {PP['dome']['height_frac']*R:,.0f} m, {PP['ribs']['count_main']} ribs", R * 0.7, PP['dome']['height_frac'] * R * 0.72),
    (f"Collar: R {collar_r(R):,.0f} m, h {PP['collar']['height_frac']*R:,.0f} m, light band + {PP['hangar_bays']['count']} hangar bays", collar_r(R), (PP['collar']['top_y_frac'] - PP['collar']['height_frac'] / 2) * R),
]
for k, (r, y) in enumerate(PP["hull"][1:6], 1):
    rows.append((f"Hull point {k}: R {r*R:,.0f} m at y {y*R:,.0f} m", r * R, y * R))
for k, (r, yt, t) in enumerate(PP["plates"], 1):
    rows.append((f"Plate {k}: R {r*R:,.0f} m, t {t*R:,.0f} m, top y {yt*R:,.0f} m", r * R, (yt - t / 2) * R))
rows.append((f"Core: R {PP['core']['radius_frac']*R:,.0f} m, y {PP['core']['top_y_frac']*R:,.0f} to {PP['core']['bottom_y_frac']*R:,.0f} m", PP['core']['radius_frac'] * R, (PP['core']['top_y_frac'] + PP['core']['bottom_y_frac']) / 2 * R))
rows.append((f"Nub: R {PP['nub']['radius_top_frac']*R:,.0f} → {PP['nub']['radius_bottom_frac']*R:,.0f} m, bottom y {pod_bottom(R):,.0f} m", PP['nub']['radius_bottom_frac'] * R, pod_bottom(R)))
rows.append((f"Antenna root at y {AN['top_y']:,} m (runs {AN['length']:,} m down)", AN["radius_top"], aTop - 800))
for i, (label, x, y) in enumerate(rows):
    sec.leader(x, y, 880, 90 + i * 24, label)
sec.dim_v(0, PP["dome"]["height_frac"] * R, -10500, f"{fmt(PP['dome']['height_frac']*R)}", side=-1)
sec.dim_v(pod_bottom(R), 0, -10500, f"{fmt(-pod_bottom(R))} hull + plates", side=-1)
sec.dim_h(-collar_r(R), collar_r(R), PP["dome"]["height_frac"] * R + 900, f"COLLAR Ø {fmt(2*collar_r(R))}")
sec.dim_h(-R, R, -pod_bottom(R) * 0 + PP["dome"]["height_frac"] * R + 300, f"DOME Ø {fmt(2*R)}")
# satellite mini-silhouette for scale comparison
sec.ptext(30, SH_ - 340, "SATELLITE POD (60 %) at the same scale, for comparison:", 11.5, weight="700")
mini = Sheet(sec.x0, sec.y0, SW_, SH_, sec.s, 190, SH_ - 215, "", "")
pod_silhouette(mini, 0, 0, Rs)
mini.dim_h(-collar_r(Rs), collar_r(Rs), pod_bottom(Rs) - 900, f"Ø {fmt(2*collar_r(Rs))}", above=False)
mini.dim_v(pod_bottom(Rs), pod_top(Rs), collar_r(Rs) + 900, f"{fmt(pod_top(Rs)-pod_bottom(Rs))}")

# ----------------------------------------------------------------------------
# Sheet 4: PARTS, ENVELOPE, BASIS, REFERENCES, DIALOGUE
# ----------------------------------------------------------------------------
TW, TH = 1200, 1000
tab = Sheet(20 + PW + 20, 20 + PH + 20, TW, TH, 1, 0, 0, "PARTS LIST, ENVELOPE AND SOURCES", "IDs match the layer names in the 3D viewer (spec.json is the single source of truth).")
tab.frame(4)
parts = [
    ("M-01", "Main dome (glass) + deck", 1, f"ellipsoid Ø {2*R:,} × h {PP['dome']['height_frac']*R:,.0f}", "glass / hull_light"),
    ("M-02", "Main collar, ribs, hangar bays", 1, f"Ø {2*collar_r(R):,.0f} × {PP['collar']['height_frac']*R:,.0f}; {PP['ribs']['count_main']} ribs; {PP['hangar_bays']['count']} bays", "hull / rim_light"),
    ("M-03", "Main hull (revolved)", 1, f"Ø {2*1.09*R:,.0f} → {2*0.68*R:,.0f} over {0.56*R:,.0f}", "hull"),
    ("M-04", "Main metallic plates", len(PP["plates"]), "Ø " + " / ".join(f"{2*p[0]*R:,.0f}" for p in PP["plates"]), "hull_dark / rim_light"),
    ("M-05", "Main core + nub", 1, f"Ø {2*PP['core']['radius_frac']*R:,.0f}; bottom y {pod_bottom(R):,.0f}", "hull_dark"),
    ("M-06", "Main city", MP["city"]["tower_count"], f"{MP['city']['height_min']}–{MP['city']['height_max']:,} tall + {MP['city']['lowrise_count']} low-rise", "city / city_glow"),
    ("M-07", "Council spire", 1, f"Ø {2*ct['radius_base']:,} → {2*ct['radius_top']}, h {OVERALL['council_tower_height']:,}", "city / city_glow"),
    ("S-01", "Satellite domes + decks", SP["count"], f"ellipsoid Ø {2*Rs:,.0f} × h {PP['dome']['height_frac']*Rs:,.0f}", "glass / hull_light"),
    ("S-02", "Satellite collars, ribs, bays", SP["count"], f"Ø {2*collar_r(Rs):,.0f}; {PP['ribs']['count_satellite']} ribs", "hull / rim_light"),
    ("S-03", "Satellite hulls", SP["count"], f"{int(SP['scale']*100)} % of main profile", "hull"),
    ("S-04", "Satellite plates", SP["count"] * len(PP["plates"]), "Ø " + " / ".join(f"{2*p[0]*Rs:,.0f}" for p in PP["plates"]), "hull_dark"),
    ("S-05", "Satellite cores + nubs", SP["count"], f"Ø {2*PP['core']['radius_frac']*Rs:,.0f}; bottom y {pod_bottom(Rs):,.0f}", "hull_dark"),
    ("S-06", "Satellite cities", SP["count"], f"{SP['city']['tower_count']} towers + {SP['city']['lowrise_count']} low-rise each", "city / city_glow"),
    ("B-01", "Bridge tubes (organic)", B["count"], f"Ø {2*B['tube_radius_main']:,} → {2*B['tube_radius_satellite']:,}, span {bridge_span:,.0f}, sag {B['sag']}, {B['rib_count']} ribs", "bridge_tube"),
    ("B-02", "Bridge trusses (technical)", B["count"], f"{B['truss']['width']} × {B['truss']['height']} rail, y {B['truss']['y']}", "hull_light / trim"),
    ("L-01", "Legs", L["count"], f"{leg_len:,.0f} long, rake {leg_rake:.1f}°, Ø {2*L['radius_attach']} → {2*L['radius_foot']}", "hull_dark"),
    ("L-02", "Knee joints + braces", L["count"], f"sphere R {L['knee_radius']}; brace Ø {2*L['brace']['radius']} to core at y {L['brace']['core_y']:,}", "hull"),
    ("L-03", "Foot pads", L["count"], f"Ø {2*L['foot_pad']['radius']:,} × {L['foot_pad']['thickness']}; y {L['foot']['y']:,}", "hull"),
    ("A-01", "Central antenna (downward)", 1, f"{AN['length']:,} long from y {AN['top_y']:,}; Ø {2*AN['radius_top']} → {2*AN['radius_tip']}; 3 rings, 1 dish, beacon", "hull_dark / beacon"),
]
cols = [(18, "ID"), (70, "Part"), (300, "Qty"), (340, "Key dimensions (m)"), (940, "Material")]
y = 78
for x, name in cols: tab.ptext(x, y, name, 12, weight="700")
tab.add(f'<line x1="{tab.x0+14}" y1="{tab.y0+y+6}" x2="{tab.x0+TW-14}" y2="{tab.y0+y+6}" stroke="{INK}" stroke-width="1"/>')
y += 24
for row in parts:
    for (x, _), val in zip(cols, row): tab.ptext(x, y, str(val), 11.5, mono=(x in (18, 300, 340)))
    y += 20
y += 8
tab.add(f'<line x1="{tab.x0+14}" y1="{tab.y0+y-12}" x2="{tab.x0+TW-14}" y2="{tab.y0+y-12}" stroke="{INK}" stroke-width="1"/>')
tab.ptext(18, y + 6, "OVERALL ENVELOPE (computed)", 13, weight="700")
env_rows = [
    f"Overall height (leg feet → main dome top): {fmt(OVERALL['height_total'])}     Main pod alone: {fmt(OVERALL['main_pod_height'])} tall",
    f"Datum → leg feet: {fmt(-foot_bottom)}     Datum → antenna tip: {fmt(-antenna_tip)}     Datum → dome top: {fmt(top)}",
    f"Plan envelope: {fmt(OVERALL['width_x_extent'])} (X) × {fmt(OVERALL['width_z_extent'])} (Z);  bounding circle Ø {fmt(2*overall_radius)}",
    f"Main dome Ø {fmt(2*R)}; collar Ø {fmt(2*collar_r(R))}; satellites Ø {fmt(2*Rs)} domes at {fmt(SP['center_distance'])} from centre",
]
for i, r in enumerate(env_rows): tab.ptext(18, y + 28 + i * 18, r, 11.5, mono=True)
y += 28 + len(env_rows) * 18 + 10
def wrap(s, n=150):
    out, cur = [], ""
    for w in s.split():
        if len(cur) + len(w) + 1 > n: out.append(cur); cur = w
        else: cur = (cur + " " + w).strip()
    return out + [cur]
tab.ptext(18, y, "SCALE BASIS", 13, weight="700")
lines = wrap(SPEC["scale_basis"]["summary"])
for i, ln in enumerate(lines): tab.ptext(18, y + 20 + i * 16, ln, 11.5, color="#2d3748")
y += 20 + len(lines) * 16 + 6
tab.ptext(18, y, "CONFIDENCE", 13, weight="700")
lines = wrap(SPEC["scale_basis"]["confidence"])
for i, ln in enumerate(lines): tab.ptext(18, y + 20 + i * 16, ln, 11, color="#4a5568")
y += 20 + len(lines) * 16 + 6
tab.ptext(18, y, "WRITTEN SOURCES (see research.md for full text)", 13, weight="700")
src = [
    "Wiki: 'a massive space station with a central glass dome, with three separate, smaller domed districts protruding from it. Several metallic plates extend from the bottom'.",
    "Build log: 'profile sketch of the main pod ... revolved'; 'raised piece that rests on the outside of the pod'; smaller pods 'scaled down to 60%'; bridge 'sculpted';",
    "  'three legs extruding downward'; 'the middle antenna that runs right down the middle of the center pod ... shorter than the surrounding feet'.",
    "Print model: 'always the same shot at the same angle, so ... the lower part' is speculative; centre disc ~ Brooklyn.",
]
for i, ln in enumerate(src): tab.ptext(18, y + 20 + i * 15, ln, 10.5, color="#2d3748")
y += 20 + len(src) * 15 + 6
tab.ptext(18, y, "IN THE SHOW", 13, weight="700")
quotes = [
    "S1E10 Rick: 'The citadel of Ricks. It's the secret headquarters for the council of Ricks.'   Morty (S3E1): 'All the different Ricks from all the different realities got together to hide here.'",
    "S3E1 Worker Rick: 'This area's for teleporting the entire Citadel to somewhere else using only buttons and dials.'   Summer: 'A city of Grandpas?'",
]
for i, ln in enumerate(quotes): tab.ptext(18, y + 20 + i * 15, ln, 10.5, color="#2d3748")

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
    plan.render(), elev.render(), sec.render(), mini.render(), tab.render(),
    "</svg>",
]
out = ROOT / "schematic" / "citadel_schematic.svg"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("\n".join(svg))
print(f"wrote {out} ({out.stat().st_size/1024:.0f} KB) and overall_dimensions.json")
print(json.dumps(OVERALL, indent=2))
