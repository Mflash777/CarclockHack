#!/usr/bin/env python3
"""Full-assembly previews of HackClock GT: every part placed where docs/WIRING.md says it goes.
Run case_gen.py first.  Writes docs/images/assembly_*.png (numpy + matplotlib only).
  1. assembled car, front-left and rear views
  2. top cover (hood + roof + windshield) lifted off: the inside
  3. top cover turned upside down beside the car: what hangs under it
Part sizes are real module sizes; positions follow the mounting table in docs/WIRING.md.
"""
import json, math, io, contextlib, importlib.util
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rast import render
from geom import extrude, rect, circle

spec = importlib.util.spec_from_file_location("cg", "case_gen.py"); cg = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()): spec.loader.exec_module(cg)
W, T, BZ = cg.W, cg.T, cg.BOTTOM_Z

# ------------------------------------------------------------------ primitives
def box(x0, x1, y0, y1, z0, z1):
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
    f = [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6), (0, 5, 1), (0, 4, 5), (1, 6, 2), (1, 5, 6), (2, 7, 3), (2, 6, 7), (3, 4, 0), (3, 7, 4)]
    return v[np.array(f)]

def cyl(p0, p1, r, n=20):
    p0 = np.array(p0, float); p1 = np.array(p1, float)
    d = p1 - p0; d /= np.linalg.norm(d)
    a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(d, a); u /= np.linalg.norm(u); w = np.cross(d, u)
    ang = [2 * math.pi * k / n for k in range(n + 1)]
    r0 = [p0 + r * (math.cos(t) * u + math.sin(t) * w) for t in ang]
    r1 = [p1 + r * (math.cos(t) * u + math.sin(t) * w) for t in ang]
    tris = []
    for k in range(n):
        tris += [[r0[k], r0[k + 1], r1[k + 1]], [r0[k], r1[k + 1], r1[k]], [p0, r0[k + 1], r0[k]], [p1, r1[k], r1[k + 1]]]
    return np.array(tris)

def tube(path, r, n=8):
    path = [np.array(p, float) for p in path]
    out = []
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        d = (b - a) / np.linalg.norm(b - a)
        out.append(cyl(a - d * (r * 0.9 if i else 0), b + d * (r * 0.9 if i < len(path) - 2 else 0), r, n))
    return np.concatenate(out)

def bundle(path, colours, r=0.55, gap=1.5):
    path = [np.array(p, float) for p in path]
    m = len(colours); res = []
    dirs = []
    for i in range(len(path)):
        a = path[max(i - 1, 0)]; b = path[min(i + 1, len(path) - 1)]
        d = b - a; d /= np.linalg.norm(d)
        dirs.append(d)
    for k, col in enumerate(colours):
        off = (k - (m - 1) / 2) * gap
        pts = []
        for p, d in zip(path, dirs):
            perp = np.cross(d, [0, 0, 1.0]) if abs(d[2]) < 0.9 else np.cross(d, [1.0, 0, 0])
            perp /= np.linalg.norm(perp)
            pts.append(p + off * perp)
        res.append((tube(pts, r), col, "solid"))
    return res

def mv(tris, dx=0, dy=0, dz=0): return tris + np.array([dx, dy, dz])

PEARL, DARK, SMOKE = (0.93, 0.93, 0.95), (0.13, 0.13, 0.15), (0.10, 0.10, 0.13)
GREEN, BLACK, SILVER, GOLD = (0.08, 0.40, 0.22), (0.07, 0.07, 0.08), (0.78, 0.79, 0.82), (0.85, 0.68, 0.25)
BLUE, RED, WHITE, GREY = (0.12, 0.30, 0.65), (0.78, 0.13, 0.15), (0.95, 0.95, 0.95), (0.45, 0.46, 0.5)
BEIGE, ORANGE = (0.82, 0.72, 0.5), (0.9, 0.55, 0.12)

# ------------------------------------------------------------------ parts that stay in the car (base)
base_parts = []          # (tris, colour, mode)
lid_parts = []

OX, OY = cg.PCB_ORIGIN
PZ = BZ + T - 0.2 + 6.2                 # PCB underside (on the 6.2 mm standoffs)
TOP = PZ + 1.6                          # PCB top face
def P(x, y, z=None): return (OX + x, OY + y) if z is None else (OX + x, OY + y, z)
data = json.load(open("../hardware/pcb/pcb_data.json"))
swx, swy, swh = cg.SPOILER_SW; seat_z = cg.seat_z

base_parts.append((box(OX, OX + 80, OY, OY + 60, PZ, TOP), GREEN, "solid"))
for p in data["parts"]:
    pads = [(q[1], q[2]) for q in p["pads"]]
    ref = p["ref"]
    if ref == "U1":
        for (px, _) in {(q[0], 0) for q in pads}:
            base_parts.append((box(OX + px - 1.27, OX + px + 1.27, OY + 6.0 - 1.27, OY + 21.24 + 1.27, TOP, TOP + 8.5), BLACK, "solid"))
        cy = OY + 13.62; cx = OX + 40.0; zm = TOP + 8.5
        base_parts.append((box(cx - 8.9, cx + 8.9, cy - 10.5, cy + 10.5, zm, zm + 1.0), (0.05, 0.05, 0.07), "solid"))
        base_parts.append((box(cx - 5.5, cx + 5.5, cy + 0.0, cy + 10.0, zm + 1.0, zm + 3.2), SILVER, "solid"))
        base_parts.append((box(cx - 4.5, cx + 4.5, cy - 12.0, cy - 4.7, zm + 1.0, zm + 4.2), SILVER, "solid"))
    elif ref.startswith("J"):
        for (px, py) in pads:
            base_parts.append((box(OX + px - 1.27, OX + px + 1.27, OY + py - 1.27, OY + py + 1.27, TOP, TOP + 2.5), BLACK, "solid"))
            base_parts.append((box(OX + px - 0.32, OX + px + 0.32, OY + py - 0.32, OY + py + 0.32, TOP, TOP + 8.0), GOLD, "solid"))
    elif ref.startswith("R"):
        (x1, y), (x2, _) = pads[0], pads[1]
        base_parts.append((cyl((OX + (x1 + x2) / 2 - 3.1, OY + y, TOP + 1.4), (OX + (x1 + x2) / 2 + 3.1, OY + y, TOP + 1.4), 1.15, 12), BEIGE, "solid"))
        for px in (x1, x2):
            base_parts.append((cyl((OX + px, OY + y, TOP), (OX + px, OY + y, TOP + 1.4), 0.28, 6), SILVER, "solid"))
        base_parts.append((cyl((OX + x1, OY + y, TOP + 1.4), (OX + (x1 + x2) / 2 - 3.1, OY + y, TOP + 1.4), 0.28, 6), SILVER, "solid"))
        base_parts.append((cyl((OX + x2, OY + y, TOP + 1.4), (OX + (x1 + x2) / 2 + 3.1, OY + y, TOP + 1.4), 0.28, 6), SILVER, "solid"))
    elif ref == "C5":
        (x1, y), (x2, _) = pads
        base_parts.append((cyl((OX + (x1 + x2) / 2, OY + y, TOP), (OX + (x1 + x2) / 2, OY + y, TOP + 12.0), 4.0, 24), (0.08, 0.14, 0.35), "solid"))
    elif ref in ("C1", "C2", "C3", "C4"):
        (x1, y), (x2, _) = pads
        base_parts.append((box(OX + (x1 + x2) / 2 - 2.6, OX + (x1 + x2) / 2 + 2.6, OY + y - 1.2, OY + y + 1.2, TOP, TOP + 5.5), ORANGE, "solid"))
    elif ref == "Q1":
        xs = [q[0] for q in pads]; y = pads[0][1]
        base_parts.append((cyl((OX + sum(xs) / 3, OY + y, TOP), (OX + sum(xs) / 3, OY + y, TOP + 5.0), 2.4, 16), BLACK, "solid"))
    elif ref in ("D1", "D2"):
        (x1, y), (x2, _) = pads
        L = 3.8 if ref == "D1" else 5.0; r = 1.0 if ref == "D1" else 1.35
        mx = (x1 + x2) / 2
        base_parts.append((cyl((OX + mx - L / 2, OY + y, TOP + 1.4), (OX + mx + L / 2, OY + y, TOP + 1.4), r, 12), BLACK, "solid"))
        base_parts.append((cyl((OX + mx + L / 2 - 0.8, OY + y, TOP + 1.4), (OX + mx + L / 2, OY + y, TOP + 1.4), r + 0.05, 12), SILVER, "solid"))

# speaker (cone facing down through the bottom grille) + MAX98357A amp
sx, sy, sid, sr = cg.SPEAKER
base_parts.append((cyl((sx, sy, BZ + T), (sx, sy, BZ + T + 5.0), sid / 2 - 0.2, 64), (0.55, 0.56, 0.6), "solid"))
base_parts.append((cyl((sx, sy, BZ + T + 5.0), (sx, sy, BZ + T + 16.0), 14.0, 40), (0.10, 0.10, 0.11), "solid"))
AMP = (175.0, 95.0)
base_parts.append((box(AMP[0] - 9.5, AMP[0] + 9.5, AMP[1] - 8.9, AMP[1] + 8.9, BZ + T + 1.0, BZ + T + 2.6), (0.55, 0.12, 0.45), "solid"))
base_parts.append((box(AMP[0] - 1.5, AMP[0] + 1.5, AMP[1] - 1.5, AMP[1] + 1.5, BZ + T + 2.6, BZ + T + 3.5), BLACK, "solid"))
base_parts.append((box(AMP[0] + 3.0, AMP[0] + 9.5, AMP[1] + 1.0, AMP[1] + 8.0, BZ + T + 2.6, BZ + T + 8.6), BLUE, "solid"))
base_parts.append((box(AMP[0] - 9.5, AMP[0] - 7.0, AMP[1] - 8.9, AMP[1] + 8.9, BZ + T + 2.6, BZ + T + 5.1), BLACK, "solid"))
# buzzers
for (bx, by) in cg.BUZZERS:
    base_parts.append((cyl((bx, by, BZ + T - 0.2), (bx, by, BZ + T + 6.0), 6.0, 28), BLACK, "solid"))
    base_parts.append((cyl((bx, by, BZ + T + 6.0), (bx, by, BZ + T + 6.1), 1.2, 12), GREY, "solid"))

# TFT in the left door, behind its window
tx, tz = cg.TFT_WIN[0], cg.TFT_WIN[1]
base_parts.append((box(tx - 29.8, tx + 29.8, T + 1.4, T + 2.6, tz - 18.3, tz + 18.3), (0.10, 0.22, 0.45), "solid"))
base_parts.append((box(tx - 26.0, tx + 26.0, T - 0.1, T + 1.4, tz - 16.0, tz + 16.0), BLACK, "solid"))
base_parts.append((box(tx - 29.8, tx - 27.2, T + 2.6, T + 5.1, tz - 10.1, tz + 10.1), BLACK, "solid"))

# MODE + TALK buttons in the left door, beside the info screen: cap outside, body + nut inside
for (bx, bz, d, name) in cg.SIDE_BUTTONS:
    col = (0.2, 0.45, 0.8) if name == "TALK" else (0.25, 0.26, 0.3)
    base_parts.append((cyl((bx, 1.0, bz), (bx, -3.6, bz), (d - 1.2) / 2, 28), col, "solid"))
    base_parts.append((cyl((bx, 2.0, bz), (bx, 11.0, bz), 4.4, 18), BLACK, "solid"))
    base_parts.append((cyl((bx, 2.0, bz), (bx, 4.0, bz), 5.8, 6), SILVER, "solid"))

# audio board (ESP32 WROVER dev board) on the right wall, behind the door vents
YW = W - T                                   # inner face of the right wall
AX0, AX1, AZ0, AZ1 = 112.0, 167.0, 16.0, 44.0
base_parts.append((box(AX0, AX1, YW - 2.4, YW - 0.8, AZ0, AZ1), (0.06, 0.07, 0.10), "solid"))
base_parts.append((box(AX0 + 0.5, AX0 + 19.0, YW - 7.4, YW - 2.4, AZ0 + 2.0, AZ1 - 2.0), SILVER, "solid"))
base_parts.append((box(AX0 + 30.0, AX1 - 6.0, YW - 5.4, YW - 2.4, AZ0 + 0.4, AZ0 + 2.9), BLACK, "solid"))
base_parts.append((box(AX0 + 30.0, AX1 - 6.0, YW - 5.4, YW - 2.4, AZ1 - 2.9, AZ1 - 0.4), BLACK, "solid"))
base_parts.append((box(AX1 - 2.5, AX1 + 1.5, YW - 5.0, YW - 2.4, AZ0 + 10.0, AZ0 + 16.0), SILVER, "solid"))
# DS3231 RTC on the right wall further back
RX0, RX1, RZ0, RZ1 = 181.0, 219.0, 22.0, 44.0
base_parts.append((box(RX0, RX1, YW - 2.4, YW - 0.8, RZ0, RZ1), BLUE, "solid"))
base_parts.append((cyl((RX1 - 11.0, YW - 5.6, (RZ0 + RZ1) / 2), (RX1 - 11.0, YW - 2.4, (RZ0 + RZ1) / 2), 10.0, 36), SILVER, "solid"))
base_parts.append((box(RX0 + 6.0, RX0 + 14.0, YW - 3.8, YW - 2.4, RZ0 + 7.0, RZ0 + 13.0), BLACK, "solid"))
# USB-C power breakout in the tail
ux = 243.0; uz = 50.0 - cg.USB_SLOT[0]; uy = cg.USB_SLOT[1]
base_parts.append((box(ux - 5.0, ux - 3.2, uy - 6.0, uy + 6.0, uz - 5.0, uz + 5.0), GREEN, "solid"))
base_parts.append((box(ux - 3.2, ux + 2.0, uy - 4.5, uy + 4.5, uz - 1.6, uz + 1.6), SILVER, "solid"))

# watch charger puck cable: roof pocket -> inside the body -> tail slot -> USB-A plug outside
pu, pv, pd, pdepth = cg.PUCK
roof_o, roof_eu, _, roof_ew = cg.cabin.basis(cg.C_ROOF)
roof_pt = roof_o + pu * roof_eu
puck_x, puck_y, roof_z = float(roof_pt[0]), pv, float(roof_pt[2])
au, av = cg.USB_A_SLOTS[0]; az_slot = 50.0 - au
cable = [(puck_x, puck_y, roof_z - pdepth), (puck_x, puck_y, roof_z - pdepth - 8), (puck_x + 12, puck_y + 6, 46.0),
         (puck_x + 70, av, 40.0), (236.0, av, 34.0), (240.0, av, az_slot + 1.0), (247.0, av, az_slot)]
base_parts.append((tube(cable, 2.0, 10), WHITE, "solid"))
base_parts.append((box(246.0, 259.0, av - 6.1, av + 6.1, az_slot - 2.3, az_slot + 2.3), SILVER, "solid"))
base_parts.append((box(255.0, 262.0, av - 7.0, av + 7.0, az_slot - 4.5, az_slot + 4.5), BLACK, "solid"))

# wiring between the carrier PCB and the modules (Dupont wires)
def hdr(x, y): return (OX + x, OY + y)
def wire(path, cols, **k): base_parts.extend(bundle(path, cols, **k))
TIP = TOP + 8.6
WC = [(0.85, 0.15, 0.15), (0.1, 0.1, 0.1), (0.95, 0.75, 0.1), (0.2, 0.55, 0.85), (0.2, 0.7, 0.3)]
WC_RED = WC[0]
j1 = hdr(18.9, 55.0); j2 = hdr(36.8, 55.0); j3 = hdr(49.8, 55.0); j4 = hdr(65.4, 55.0)
j5 = hdr(4.0, 23.25); j6 = hdr(76.0, 18.4); j7 = hdr(76.0, 34.1); j8 = hdr(4.0, 9.25)
wire([(j1[0], j1[1], TIP), (j1[0], j1[1], 36), (j1[0], 12.0, 36), (111.0, 8.5, 36), (111.0, 8.5, 14.0)], WC[:4])        # TFT
wire([(j3[0], j3[1], TIP), (j3[0], j3[1], 40), (172, 96, 40), (181.5, 108, 38), (181.5, 110, 34)], WC[:4])                # RTC
wire([(j7[0], j7[1], TIP), (j7[0], j7[1], 32), (j7[0], 95, 32), (158, 104, 40), (158, 109, 45.5)], WC[:5])               # audio board
wire([(150, YW - 4.0, AZ0 + 1.4), (150, 100, 12.5), (172, 90, 12.0), (172, 88.0, 10.5)], WC[1:4], r=0.5, gap=1.3)          # I2S to amp
wire([(AMP[0] + 9.5, AMP[1] + 4.5, 12.0), (200, 89, 11.0), (226, 76, 12.0), (230.0, 62.0, 12.0)], WC[:2], r=0.65, gap=1.6)  # amp to speaker
wire([(j5[0], j5[1], TIP), (j5[0], j5[1], 28), (62, 52, 28), (55, 50, 16.0)], WC[:2])                                      # buzzers
wire([(j5[0], j5[1] + 0.8, TIP), (j5[0], j5[1] + 0.8, 29), (62, 66, 29), (55, 70, 16.0)], WC[:2])
wire([(j8[0], j8[1], TIP), (j8[0], j8[1], 24), (j8[0], 24.0, 24), (j8[0], 24.0, 12), (236, 24.0, 12), (236, uy - 2, 18), (ux - 4.0, uy, uz)], WC[:2], r=0.8, gap=1.8)   # 5 V in
# loose ends that go up into the top cover (7-seg, buttons, mic)
wire([(j2[0], j2[1], TIP), (j2[0], j2[1], 46), (112, 76, 60)], WC[:4])
wire([(j4[0] + 1.3, j4[1], TIP), (j4[0] + 1.3, j4[1], 50), (222, 70, 52), (swx - 0.5, swy, 56.0), (swx - 0.5, swy, seat_z - 3.0)], WC[:2], r=0.5, gap=1.2)   # spoiler switch
for (bx, bz, d, name), dz in zip(cg.SIDE_BUTTONS, (0.0, 1.2)):
    wire([(j4[0] - dz, j4[1], TIP), (j4[0] - dz, j4[1], 31 + dz), (100.5 + dz, 83, 31 + dz), (100.5 + dz, 12, 31 + dz), (bx + 0.5, 12, bz + 3)], WC[:2], r=0.5, gap=1.2)   # MODE, TALK
wire([(j6[0], j6[1], TIP), (j6[0], j6[1], 44), (150, 46, 54)], WC[:5])

# ------------------------------------------------------------------ parts that ride on the top cover (lid)
# spoiler = SNOOZE switch: tactile switch on the stand, hinged wing on a pin through the struts
swx, swy, swh = cg.SPOILER_SW; seat_z = cg.seat_z
lid_parts.append((box(swx - 3, swx + 3, swy - 3, swy + 3, seat_z + 0.2, seat_z + 3.6), BLACK, "solid"))
lid_parts.append((cyl((swx, swy, seat_z + 3.6), (swx, swy, seat_z + swh), 1.7, 16), SILVER, "solid"))
lid_parts.append((tube([(swx - 1.5, swy, seat_z + 0.2), (swx - 1.5, swy, seat_z - 3.0)], 0.5, 6), WC_RED, "solid"))
lid_parts.append((tube([(swx + 1.5, swy, seat_z + 0.2), (swx + 1.5, swy, seat_z - 3.0)], 0.5, 6), (0.1, 0.1, 0.1), "solid"))
lid_parts.append((np.load("stl/_preview_wing.npy"), PEARL, "solid"))
lid_parts.append((cyl((cg.WING_PIN[0], 18.0, cg.WING_PIN[1]), (cg.WING_PIN[0], W - 18.0, cg.WING_PIN[1]), 0.85, 12), SILVER, "solid"))
# mic module under the nose-top vent
mic = cg.lower.on(cg.L_NOSETOP, extrude(rect(cg.MIC_U, W / 2, 13.0, 13.0), [], 1.4), T + 1.0)
mic_can = cg.lower.on(cg.L_NOSETOP, extrude(circle(cg.MIC_U, W / 2, 2.0, 16), [], 1.6), T - 0.6)
lid_parts += [(mic, (0.1, 0.1, 0.5), "solid"), (mic_can, SILVER, "solid")]
# 7-segment module behind the windshield glass
gu, gv = cg.SCREEN_WIN[0], cg.SCREEN_WIN[1]
lid_parts.append((cg.cabin.on(cg.C_SCREEN, extrude(rect(gu, gv, 19.5, 46.0), [], 4.6), T + 1.2), (0.06, 0.06, 0.07), "solid"))
lid_parts.append((cg.cabin.on(cg.C_SCREEN, extrude(rect(gu, gv, 25.0, 51.0), [], 1.5), T + 5.8), (0.1, 0.1, 0.12), "solid"))
# watch charger puck in the roof pocket (its back sits in the pocket, face flush with the roof)
lid_parts.append((cg.cabin.on(cg.C_ROOF, extrude(circle(pu, pv, pd / 2 - 0.3, 64), [], pdepth - 1.0), 0.2), SILVER, "solid"))
lid_parts.append((cg.cabin.on(cg.C_ROOF, extrude(circle(pu, pv, 11.0, 32), [], 3.0), pdepth - 2.0), BLACK, "solid"))

# ------------------------------------------------------------------ the watch on the roof (shown on the assembled views)
watch = [(cg.cabin.on(cg.C_ROOF, extrude(circle(pu, pv, 23.5, 64), [], 11.0), -11.2), (0.12, 0.12, 0.13), "solid"),
         (cg.cabin.on(cg.C_ROOF, extrude(circle(pu, pv, 21.0, 64), [circle(pu, pv, 18.5, 64)], 1.0), -12.2), (0.55, 0.55, 0.58), "solid"),
         (cg.cabin.on(cg.C_ROOF, extrude(circle(pu, pv, 18.5, 64), [], 0.3), -11.8), (0.02, 0.03, 0.08), "solid"),
         (cg.cabin.on(cg.C_ROOF, extrude(rect(pu, pv - 36, 20, 26, 3), [], 3.5), -4.0), (0.2, 0.2, 0.22), "solid"),
         (cg.cabin.on(cg.C_ROOF, extrude(rect(pu, pv + 36, 20, 26, 3), [], 3.5), -4.0), (0.2, 0.2, 0.22), "solid")]

# ------------------------------------------------------------------ the shells
body_base = np.load("stl/_preview_base.npy"); body_lid = np.load("stl/_preview_lid.npy")
plate = np.load("stl/_preview_back.npy"); wheels = np.load("stl/_preview_wheels.npy"); glass = np.load("stl/_preview_glass.npy")
tft_quad = np.array([[[tx - 21, -0.05, tz - 16], [tx + 21, -0.05, tz - 16], [tx + 21, -0.05, tz + 16]],
                     [[tx - 21, -0.05, tz - 16], [tx + 21, -0.05, tz + 16], [tx - 21, -0.05, tz + 16]]], float)

def cat(parts): return np.concatenate([p[0] for p in parts]) if parts else np.zeros((0, 3, 3))
def fused(parts):                                       # keep colours: one render object per part
    return list(parts)

def lid_flip(tris, dy=150.0):
    t = np.array(tris, float).copy()
    t[..., 1] = W - t[..., 1] + dy
    t[..., 2] = 96.0 - t[..., 2]
    return t

def scene(show_lid=True, flip_lid=False, watch_on=True):
    objs = [(body_base, PEARL, "solid"), (plate, (0.30, 0.31, 0.34), "solid"), (wheels, DARK, "solid"), (tft_quad, (0.05, 0.10, 0.22), "flat")]
    objs += base_parts
    lidobjs = [(body_lid, PEARL, "solid"), (glass, SMOKE, "solid")] + lid_parts
    if watch_on and show_lid and not flip_lid: lidobjs += watch
    if show_lid:
        if flip_lid: lidobjs = [(lid_flip(t), c, m) for (t, c, m) in lidobjs]
        objs += lidobjs
    return objs

def finish(ax, img, title):
    ax.imshow(img); ax.axis("off"); ax.set_title(title, fontsize=12)

def label(ax, proj, items, fs=8.5, colour="#0b3d91"):
    for (txt, pt, dx, dy) in items:
        x, y = proj(pt)
        ax.annotate(txt, (x, y), (x + dx, y + dy), fontsize=fs, color=colour, ha="center", va="center",
                    arrowprops=dict(arrowstyle="-", color=colour, lw=0.9), bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=colour, lw=0.8, alpha=0.93))

# ------------------------------------------------------------------ 1. assembled
fig, axs = plt.subplots(2, 1, figsize=(12, 15), dpi=110)
img, proj = render(scene(), 22, -38, size=(1000, 720), scale=3.4)
finish(axs[0], img, "HackClock GT, assembled (front-left): time on the windshield, info screen in the door, watch on its charger on the roof")
o, eu, ev, ew = cg.cabin.basis(cg.C_SCREEN)
gcen = o + gu * eu + gv * ev - 0.5 * ew
x, y = proj(gcen); axs[0].text(x, y, "7:45", color="#ff4136", fontsize=22, ha="center", va="center", family="monospace", fontweight="bold", rotation=-8)
x, y = proj([puck_x, puck_y, roof_z + 12.2]); axs[0].text(x, y, "7:45", color="#e8f1ff", fontsize=9, ha="center", va="center", family="monospace", fontweight="bold", rotation=-8)
x, y = proj([tx, -1, tz]); axs[0].text(x, y, "AAPL +1.2%\n58°F Rain\nAlarm 6:30", color="#9fdcff", fontsize=8, ha="center", va="center", family="monospace")
img2, proj2 = render(scene(), 26, 125, size=(1000, 720), scale=3.4)
label(axs[0], proj, [("MODE + TALK buttons", (98, -3.0, 29), 40, 125)], fs=8.5)
finish(axs[1], img2, "Rear: the wing is the alarm-stop button; USB-C power in, the watch charger's USB-A plug through its slot")
label(axs[1], proj2, [("Spoiler = SNOOZE / alarm stop\n(tilts on a pin, presses a switch)", (236, 58, 80), -60, -150)], fs=8.5)
plt.tight_layout(); plt.savefig("../docs/images/assembly_assembled.png", facecolor="white"); plt.close()
print("1 ok")

# ------------------------------------------------------------------ 2. top cover off (two sides)
def labels_abs(ax, proj, items, fs=9, colour="#0b3d91"):
    for (txt, pt, lx, ly) in items:
        x, y = proj(pt)
        ax.annotate(txt, (x, y), (lx, ly), fontsize=fs, color=colour, ha="center", va="center",
                    arrowprops=dict(arrowstyle="-", color=colour, lw=0.9), bbox=dict(boxstyle="round,pad=0.25", fc="white", ec=colour, lw=0.8, alpha=0.95))

SZ = (1600, 1150)
fig, ax = plt.subplots(1, 1, figsize=(16, 11.5), dpi=110)
img, proj = render(scene(show_lid=False), 52, -28, size=SZ, scale=4.9, center=(122, 58, 14))
finish(ax, img, "Top cover lifted off, seen from the left: the inside")
labels_abs(ax, proj, [
    ("Loose wires go up to the 7-segment,\nmic and spoiler switch in the top cover", (j2[0], j2[1], 46), 330, 215),
    ("Audio board: ESP32 WROVER\n(Bluetooth speaker + voice replies)", (140, YW - 6, 40), 420, 120),
    ("DS3231 RTC", (200, YW - 4, 40), 700, 50),
    ("MAX98357A amp", (AMP[0], AMP[1], 11), 1010, 40),
    ("Watch charger cable, out through\nthe tail slot to its USB-A plug", (236, av, 34), 1370, 60),
    ("USB-C power input", (ux, uy, uz), 1470, 560),
    ("2\" speaker (cone fires\ndown at the desk)", (sx, sy, BZ + T + 15), 1370, 800),
    ("Info screen: the TFT sits behind\nthis window in the left door", (tx, T + 4.5, tz), 1180, 930),
    ("Carrier PCB + XIAO ESP32-S3\n(clock board)", (OX + 40, OY + 14, TOP + 12), 880, 960),
    ("Bottom plate (carries PCB + speaker)", (40, 58, BZ + T), 560, 1040),
    ("Buzzers x2\n(backup alarm)", (55, 46, 14), 300, 830),
    ("MODE + TALK buttons\n(left door, beside the screen)", (98, -3.0, 29), 740, 1062),
], fs=9)
plt.tight_layout(); plt.savefig("../docs/images/assembly_open_left.png", facecolor="white"); plt.close()

fig, ax = plt.subplots(1, 1, figsize=(16, 11.5), dpi=110)
img, proj = render(scene(show_lid=False), 50, 152, size=SZ, scale=4.9, center=(122, 58, 14))
finish(ax, img, "Top cover lifted off, seen from the right: the info-screen module on the left wall")
labels_abs(ax, proj, [
    ("TFT module (2.0\" ST7789),\nglued behind its door window", (tx, T + 4.5, tz), 480, 80),
    ("MODE + TALK buttons: body and nut\ninside the left door", (98, 8.0, 29), 250, 200),
    ("Wires J1 to the TFT\n(rise over the PCB, run to the screen)", (111.0, 8.5, 20), 930, 70),
    ("Bottom plate", (45, 40, BZ + T), 1180, 190),
    ("Buzzers x2", (55, 46, 14), 1300, 330),
    ("Carrier PCB + XIAO ESP32-S3", (OX + 40, OY + 14, TOP + 12), 1230, 560),
    ("2\" speaker", (sx, sy, BZ + T + 15), 160, 330),
    ("USB-C power input", (ux, uy, uz), 150, 900),
    ("Watch charger USB-A plug\n(cable runs in through the slot)", (252, av, az_slot), 520, 960),
], fs=9)
plt.tight_layout(); plt.savefig("../docs/images/assembly_open_right.png", facecolor="white"); plt.close()
print("2 ok")

# ------------------------------------------------------------------ 3. cover upside down beside the car
fig, ax = plt.subplots(1, 1, figsize=(17, 12), dpi=110)
img, proj = render(scene(show_lid=True, flip_lid=True, watch_on=False), 47, -22, size=(1750, 1250), scale=4.5, center=(122, 128, 30))
finish(ax, img, "Below: the car without its top cover.  Above: the top cover turned upside down, showing what is mounted under it")
def fl(p): return (p[0], W - p[1] + 150.0, 96.0 - p[2])
o_n, eu_n, ev_n, ew_n = cg.lower.basis(cg.L_NOSETOP)
mic_pt = o_n + cg.MIC_U * eu_n + (W / 2) * ev_n + (T + 1.7) * ew_n
sd = o + gu * eu + gv * ev + (T + 6.5) * ew
pk = roof_o + pu * roof_eu + pv * np.array([0, 1.0, 0]) + (pdepth - 1.0) * roof_ew
labels_abs(ax, proj, [
    ("Spoiler switch stand: the wires drop\nthrough the deck slot into the body", fl((swx, swy, seat_z + 2.0)), 330, 640),
    ("Wing: hinged on a pin,\nlugs inside the struts", fl((cg.WING_PIN[0], 60.0, 78.0)), 1120, 120),
    ("INMP441 microphone\n(under the nose vent)", fl(mic_pt), 140, 500),
    ("7-segment display (HT16K33),\nglued behind the windshield glass", fl(sd), 650, 635),
    ("Watch charger puck\nin its roof pocket", fl(pk), 1250, 330),
        ("Carrier PCB + XIAO", (OX + 40, OY + 14, TOP + 12), 860, 1073),
    ("Audio board", (140, YW - 6, 40), 1500, 560),
    ("Speaker", (sx, sy, BZ + T + 15), 1595, 838),
], fs=9)
plt.tight_layout(); plt.savefig("../docs/images/assembly_lid_underside.png", facecolor="white"); plt.close()
print("3 ok")
