#!/usr/bin/env python3
"""
HackClock GT - original hypercar-style enclosure generator (pure Python + numpy) -> STL files.

  * long, low sloping nose, forward cabin, swept fender flares, front splitter, rear wing that is also the SNOOZE / alarm-stop button
  * time (7-segment) behind a smoked windshield
  * 2.0" TFT in the LEFT door
  * Samsung Galaxy Watch charger puck flush in the middle of the ROOF
  * MODE + TALK buttons in the left door beside the info screen, mic behind the nose vent, USB-C power + one USB-A pass-through in the tail
  * 2" speaker fires down through the removable bottom plate (which also carries the PCB)

Coordinates (mm): x = length (nose x=0 -> tail), y = width (left side y=0), z = height (ground z=0).
Outputs in stl/: hackclock_body.stl, hackclock_bottom.stl, hackclock_wheel.stl (print 4),
hackclock_windshield.stl + hackclock_side_glass.stl (print 2) in translucent smoke PETG.
"""
import math, os, numpy as np
from geom import circle, rect, extrude, place, place_basis, write_stl, area

# ------------------------------------------------------------------ parameters
T = 2.0
W = 116.0                     # body width (fender flares add ~8 mm per side)
CY0, CY1 = 6.0, 110.0         # cabin spans y = 6..110
BOTTOM_Z = 6.0
LOWER = [(5, 6), (0, 11), (0, 19), (16, 31), (62, 50), (236, 56.5), (242, 53.5), (245, 50), (245, 11), (241, 6)]
L_NOSE, L_NOSETOP, L_HOOD, L_BELT, L_REAR = 1, 2, 3, 4, 7
CABIN = [(62, 50), (90, 72), (94, 74), (188, 74), (236, 56.5)]
C_SCREEN, C_ROOF, C_BACK = 0, 2, 3

WHEELS = [(50.0, 21.0), (200.0, 21.0)]
WHEEL_R, WHEEL_T = 21.0, 7.0
FLARE = (22.6, 31.0, 8.5)                   # inner r, outer r, how far the flare bulges out
SIDE_BUTTONS = [(98.0, 38.0, 12.2, "MODE"), (98.0, 20.0, 12.2, "TALK")]   # left door, beside the info screen: x, z, hole dia
WING_PIN = (239.0, 72.0, 2.1)               # wing hinge pin: axis (x, z) along y, hole dia (1.75-2 mm rod or filament)
SPOILER_SW = (225.0, 58.0, 5.0)             # SNOOZE switch under the wing's front edge: x, y, height of a 6x6 tactile switch
MIC_U = 10.0                                # mic hole on the nose top (u), centred in y
SCREEN_WIN = (17.8, 58.0, 26.5, 76.0)       # windshield opening: centre u, centre v, size u, size v
SEG7_POCKET = (25.4, 51.4)
SIDE_WIN = [[(78, 57), (94.4, 70), (144, 70), (144, 57)],
            [(150, 58.5), (150, 70), (190, 70), (222, 58.5)]]
SIDE_GLASS = [(75.6, 55.5), (92.6, 71.2), (189.3, 71.2), (226.5, 57.5)]
TFT_WIN = (140, 27.5, 42.0, 32.0)           # left door: centre x, z, w, h
TFT_POCKET = (59.6, 36.6)                   # TFT module PCB + 0.6 - MEASURE YOURS
PUCK = (47.0, 58.0, 38.6, 10.0)             # roof, middle: u along the roof (x = 94 + u = 141), v (y), puck dia, pocket depth - MEASURE YOUR PUCK
USB_SLOT = (30.0, 36.0, 9.6, 4.0)           # tail: USB-C power breakout (u down from top, v, w, h)
USB_A_SLOTS = [(30.0, 66.0)]                # tail: a pass-through a USB-A plug fits through (u, v)
USB_A_SIZE = (18.5, 9.5)                    # slot w (across the car) x h
SPEAKER = (205.0, 58.0, 52.4, 22.0)         # bottom plate: x, y, holder ID (2" speaker), grille r
PCB_ORIGIN = (85.0, 28.0)
PCB_HOLES = [(3.5, 3.5), (76.5, 3.5), (3.5, 56.5), (76.5, 56.5)]
BOSSES = [(18, T + 3.3), (18, W - T - 3.3), (232, T + 3.3), (232, W - T - 3.3)]
BOSS_TOP = 26.0
BUZZERS = [(55.0, 46.0), (55.0, 70.0)]

body = []

# ------------------------------------------------------------------ mitered skin builder
def line_intersect(p1, d1, p2, d2):
    A = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]])
    t = np.linalg.solve(A, p2 - p1)
    return p1 + t[0] * d1

class Skin:
    """Panels following an open (x,z) polyline (clockwise round the solid), extruded across y0..y1."""
    def __init__(self, pts, y0, y1, end_line_start, end_line_end):
        self.P = [np.array(p, float) for p in pts]
        self.y0, self.y1 = y0, y1
        n = len(self.P) - 1
        self.d, self.n, self.L = [], [], []
        for i in range(n):
            v = self.P[i + 1] - self.P[i]; L = np.linalg.norm(v); v = v / L
            self.d.append(v); self.L.append(L); self.n.append(np.array([v[1], -v[0]]))
        self.inner = []
        for k in range(len(self.P)):
            if k == 0:
                q = self.P[0] + T * self.n[0]; self.inner.append(line_intersect(q, self.d[0], *end_line_start))
            elif k == n:
                q = self.P[-1] + T * self.n[-1]; self.inner.append(line_intersect(q, self.d[-1], *end_line_end))
            else:
                self.inner.append(line_intersect(self.P[k - 1] + T * self.n[k - 1], self.d[k - 1],
                                                 self.P[k] + T * self.n[k], self.d[k]))
        self.holes = {}

    def basis(self, i):
        d, nn = self.d[i], self.n[i]
        return np.array([self.P[i][0], 0.0, self.P[i][1]]), np.array([d[0], 0, d[1]]), np.array([0, 1.0, 0]), np.array([nn[0], 0, nn[1]])

    def on(self, i, tris, w_offset=0.0):
        o, eu, ev, ew = self.basis(i)
        return place_basis(tris, o + w_offset * ew, eu, ev, ew)

    def prism(self, poly):
        pts = [tuple(p) for p in poly]
        if abs(area(pts)) < 1e-6: return
        body.append(place(extrude(pts, [], self.y1 - self.y0), (0, 2, 1), (0, self.y0, 0)))

    def build(self):
        self.rng = {}
        for i in range(len(self.P) - 1):
            a = len(body)
            self._panel(i)
            self.rng[i] = (a, len(body))

    def _panel(self, i):
        if True:
            os_, oe, is_, ie = self.P[i], self.P[i + 1], self.inner[i], self.inner[i + 1]
            if i not in self.holes:
                self.prism([os_, oe, ie, is_]); return
            d, nn = self.d[i], self.n[i]
            s0 = max(0.0, float((is_ - os_) @ d)); s1 = min(self.L[i], float((ie - os_) @ d))
            self.prism([os_, os_ + s0 * d, os_ + s0 * d + T * nn, is_])
            self.prism([os_ + s1 * d, oe, ie, os_ + s1 * d + T * nn])
            outline = [(s0, self.y0), (s1, self.y0), (s1, self.y1), (s0, self.y1)]
            body.append(self.on(i, extrude(outline, self.holes[i], T)))

ground = (np.array([0, BOTTOM_Z]), np.array([1.0, 0]))
lower = Skin(LOWER, 0, W, ground, ground)
bl = np.array(CABIN[-1], float) - np.array(CABIN[0], float)
belt_line = (np.array(CABIN[0], float), bl / np.linalg.norm(bl))
cabin = Skin(CABIN, CY0, CY1, belt_line, belt_line)

# ---- holes
lower.holes[L_NOSETOP] = [circle(MIC_U, W / 2, 1.0, 12)] + \
    [circle(MIC_U + 3.0 * math.cos(math.radians(60 * k)), W / 2 + 3.0 * math.sin(math.radians(60 * k)), 1.0, 12) for k in range(6)]
lower.holes[L_NOSE] = [rect(3.9, W / 2 - 24, 3.6, 30, 1.6), rect(4.0, W / 2 + 24, 3.6, 30, 1.6)]   # nose air intakes
belt_len = lower.L[L_BELT]
lower.holes[L_BELT] = [rect(belt_len / 2, (CY0 + CY1) / 2, belt_len - 3.0, CY1 - CY0 - 2 * T, 2)]
lower.holes[L_REAR] = [rect(USB_SLOT[0], USB_SLOT[1], USB_SLOT[3], USB_SLOT[2], 1.6),
                       ] + [rect(u, v, USB_A_SIZE[1], USB_A_SIZE[0], 2) for (u, v) in USB_A_SLOTS]
cabin.holes[C_SCREEN] = [rect(SCREEN_WIN[0], SCREEN_WIN[1], SCREEN_WIN[2], SCREEN_WIN[3], 3)]
cabin.holes[C_ROOF] = [circle(PUCK[0], PUCK[1], PUCK[2] / 2, 96)]
SW_U = (SPOILER_SW[0] - CABIN[C_BACK][0]) / float(cabin.d[C_BACK][0])      # position of the switch along the rear deck
cabin.holes[C_BACK] = [rect(SW_U, SPOILER_SW[1], 7.4, 10.0, 1.5)]            # wire slot under the spoiler switch
lower.build(); cabin.build()
LID = set()                      # the removable top cover: hood, nose top, whole greenhouse (+ what is glued to it)
for _i in (L_NOSETOP, L_HOOD): LID.update(range(*lower.rng[_i]))
for _i in range(len(CABIN) - 1): LID.update(range(*cabin.rng[_i]))

# ------------------------------------------------------------------ side walls
lower_closed = [tuple(p) for p in LOWER]
body.append(place(extrude(lower_closed, [rect(TFT_WIN[0], TFT_WIN[1], TFT_WIN[2], TFT_WIN[3], 1.5)] + [circle(bx, bz, d / 2, 48) for (bx, bz, d, _) in SIDE_BUTTONS], T), (0, 2, 1), (0, 0, 0)))
body.append(place(extrude(lower_closed, [rect(140 + s * 9, 30, 3, 20, 1.4) for s in (-1.5, -0.5, 0.5, 1.5)], T), (0, 2, 1), (0, W - T, 0)))   # right door vents
cab_closed = [tuple(p) for p in CABIN] + [(CABIN[-1][0], CABIN[-1][1] - 1.5), (CABIN[0][0], CABIN[0][1] - 1.5)]
side_win_holes = [list(map(tuple, w)) for w in SIDE_WIN]
body.append(place(extrude(cab_closed, side_win_holes, T), (0, 2, 1), (0, CY0, 0))); LID.add(len(body) - 1)
body.append(place(extrude(cab_closed, side_win_holes, T), (0, 2, 1), (0, CY1 - T, 0))); LID.add(len(body) - 1)

# ------------------------------------------------------------------ swept fender flares (closed solids)
def flare(wx, wz, side):
    r0, r1, dep = FLARE
    nphi, nth = 14, 48
    th0, th1 = math.radians(-8), math.radians(188)
    sec = []                                   # cross-section (r, y) - rounded bump + flat base inside the wall
    for k in range(nphi + 1):
        phi = math.pi * k / nphi
        sec.append((r0 + (r1 - r0) * (1 - math.cos(phi)) / 2, -dep * math.sin(phi) ** 0.8))
    sec.append((r1, 0.6)); sec.append((r0, 0.6))
    m = len(sec)
    rings = []
    for j in range(nth + 1):
        th = th0 + (th1 - th0) * j / nth
        ring = []
        for (r, y) in sec:
            yy = y if side == 0 else W - y
            ring.append((wx + r * math.cos(th), yy, wz + r * math.sin(th)))
        rings.append(np.array(ring))
    tris = []
    for j in range(nth):
        a, b = rings[j], rings[j + 1]
        for i in range(m):
            i2 = (i + 1) % m
            tris.append([a[i], b[i], b[i2]]); tris.append([a[i], b[i2], a[i2]])
    for ring, flip in ((rings[0], True), (rings[-1], False)):
        c = ring.mean(axis=0)
        for i in range(m):
            i2 = (i + 1) % m
            tris.append([c, ring[i], ring[i2]] if flip else [c, ring[i2], ring[i]])
    t = np.array(tris)
    vol = np.sum(np.einsum('ij,ij->i', t[:, 0], np.cross(t[:, 1], t[:, 2]))) / 6
    if vol < 0: t = t[:, [0, 2, 1], :]
    return t
for (wx, wz) in WHEELS:
    body.append(flare(wx, wz, 0)); body.append(flare(wx, wz, 1))
# side skirts between the flares
skirt = rect((WHEELS[0][0] + WHEELS[1][0]) / 2, 9.5, WHEELS[1][0] - WHEELS[0][0] - 2 * FLARE[1] + 6, 4, 1.5)
body.append(place(extrude(skirt, [], 3.2), (0, 2, 1), (0, -3.0, 0)))
body.append(place(extrude(skirt, [], 3.2), (0, 2, 1), (0, W - 0.2, 0)))
# front splitter
body.append(place(extrude(rect(10.0, W / 2, 26.0, W - 10, 3), [], 1.6), (0, 1, 2), (-2.5, 0, BOTTOM_Z)))
# rear wing = the SNOOZE button.  Two fixed struts carry a hinge pin; the wing is a separate print that tilts on it
STRUT = [(229, 56), (237, 54.5), (243, 74.5), (235, 74.5)]
for v in (20.0, W - 20.0):
    body.append(place(extrude(STRUT, [circle(WING_PIN[0], WING_PIN[1], WING_PIN[2] / 2, 24)], 2.4), (0, 2, 1), (0, v - 1.2, 0))); LID.add(len(body) - 1)
# switch pedestal on the rear deck: hollow so the two switch wires drop through the deck slot into the body
swx, swy, swh = SPOILER_SW
foil = [(222, 77), (226, 79.1), (234, 79.9), (242, 79.3), (248, 78.1), (248, 76.9), (240, 76.3), (230, 76.1)]
foil_under = 77.0 - 0.9 * (swx - 222.0) / 8.0          # wing underside above the switch
seat_z = foil_under - swh                              # top of the pedestal plate
PED_BASE = 57.5
body.append(place(extrude(rect(swx, swy, 12.0, 16.0, 1.5), [rect(swx, swy, 8.0, 12.0, 1.0)], seat_z - 1.0 - PED_BASE), (0, 1, 2), (0, 0, PED_BASE))); LID.add(len(body) - 1)
body.append(place(extrude(rect(swx, swy, 12.0, 16.0, 1.5), [circle(swx, swy, 2.5, 24)], 1.0), (0, 1, 2), (0, 0, seat_z - 1.0))); LID.add(len(body) - 1)
body.append(place(extrude(rect(swx, swy, 7.8, 7.8, 0.6), [rect(swx, swy, 6.3, 6.3, 0.3)], 1.6), (0, 1, 2), (0, 0, seat_z))); LID.add(len(body) - 1)
# the wing (print upside down; assembled orientation here): airfoil, two end plates, two hinge lugs beside the struts
wing = [place(extrude(foil, [], W - 24), (0, 2, 1), (0, 12, 0))]
for v in (12.0, W - 12.0 - 1.6):
    wing.append(place(extrude([(224, 74), (247, 74), (247, 79.9), (226, 79.9)], [], 1.6), (0, 2, 1), (0, v, 0)))
LUG = rect(WING_PIN[0], 73.25, 8.0, 7.5, 1.0)
for y0 in (21.4, W - 21.4 - 2.4):
    wing.append(place(extrude(LUG, [circle(WING_PIN[0], WING_PIN[1], WING_PIN[2] / 2, 24)], 2.4), (0, 2, 1), (0, y0, 0)))

# ------------------------------------------------------------------ mounts inside
tx, tz = TFT_WIN[0], TFT_WIN[1]
pb = tz - TFT_POCKET[1] / 2
fr_out = [(tx - TFT_POCKET[0] / 2 - 1.6, BOTTOM_Z + T + 0.4), (tx + TFT_POCKET[0] / 2 + 1.6, BOTTOM_Z + T + 0.4),
          (tx + TFT_POCKET[0] / 2 + 1.6, tz + TFT_POCKET[1] / 2 + 1.6), (tx - TFT_POCKET[0] / 2 - 1.6, tz + TFT_POCKET[1] / 2 + 1.6)]
fr_in = rect(tx, tz, TFT_POCKET[0], TFT_POCKET[1])
body.append(place(extrude(fr_out, [fr_in], 5.2), (0, 2, 1), (0, T - 0.2, 0)))
pu, pv, pd, pdepth = PUCK
body.append(cabin.on(C_ROOF, extrude(circle(pu, pv, pd / 2 + 1.4, 96), [circle(pu, pv, pd / 2, 96)], pdepth - T + 0.2), T - 0.2)); LID.add(len(body) - 1)
body.append(cabin.on(C_ROOF, extrude(circle(pu, pv, pd / 2 + 1.4, 96), [circle(pu, pv, 12.0, 48)], 1.6), pdepth)); LID.add(len(body) - 1)
# windshield glass lip
gu, gv = SCREEN_WIN[0], SCREEN_WIN[1]
lip = extrude(rect(gu, gv, SCREEN_WIN[2] + 8.8, SCREEN_WIN[3] + 8.8, 3), [rect(gu, gv, SCREEN_WIN[2] + 6.4, SCREEN_WIN[3] + 6.4, 3)], 2.2)
body.append(cabin.on(C_SCREEN, lip, T - 0.2)); LID.add(len(body) - 1)
# mic pocket under the nose top
body.append(lower.on(L_NOSETOP, extrude(rect(MIC_U, W / 2, 17.0, 17.0), [rect(MIC_U, W / 2, 14.6, 14.6)], 3.2), T - 0.2)); LID.add(len(body) - 1)
# lights: slim headlights on the nose top, four round tail lights
for v in (18.0, W - 18.0):
    body.append(lower.on(L_NOSETOP, extrude(rect(10.0, v, 7.0, 18.0, 3.0), [rect(10.0, v, 4.0, 15.0, 1.5)], 1.6), -1.4)); LID.add(len(body) - 1)
for v in (13.0, 27.0, W - 27.0, W - 13.0):
    body.append(lower.on(L_REAR, extrude(circle(9.0, v, 5.0, 40), [circle(9.0, v, 3.4, 40)], 1.8), -1.6))
# bosses
for (bx, by) in BOSSES:
    body.append(place(extrude(circle(bx, by, 3.5, 32), [circle(bx, by, 1.25, 20)], BOSS_TOP - BOTTOM_Z - T), (0, 1, 2), (0, 0, BOTTOM_Z + T)))

# ------------------------------------------------------------------ bottom plate
x0b, x1b = lower.inner[0][0] + 0.4, lower.inner[-1][0] - 0.4
bh = [circle(bx, by, 1.7, 24) for (bx, by) in BOSSES]
bh += [rect(PCB_ORIGIN[0] + 18 + i * 9, PCB_ORIGIN[1] + 30, 3, 26, 1.4) for i in range(5)]
for (bx, by) in BUZZERS:
    bh.append(circle(bx, by, 1.5, 14))
    bh += [circle(bx + 4 * math.cos(math.radians(60 * k)), by + 4 * math.sin(math.radians(60 * k)), 1.5, 14) for k in range(6)]
sx, sy, sid, sr = SPEAKER
for row in range(-6, 7):
    for col in range(-6, 7):
        gx = sx + row * 4.4 * 0.866; gy = sy + col * 4.4 + (2.2 if row % 2 else 0)
        if (gx - sx) ** 2 + (gy - sy) ** 2 <= sr ** 2: bh.append(circle(gx, gy, 1.5, 12))
back = [place(extrude(rect((x0b + x1b) / 2, W / 2, x1b - x0b, W - 2 * T - 0.6, 2), bh, T), (0, 1, 2), (0, 0, BOTTOM_Z))]
for (hx, hy) in PCB_HOLES:
    cx, cy = PCB_ORIGIN[0] + hx, PCB_ORIGIN[1] + hy
    back.append(place(extrude(circle(cx, cy, 3.0, 32), [circle(cx, cy, 1.3, 20)], 6.2), (0, 1, 2), (0, 0, BOTTOM_Z + T - 0.2)))
for (bx, by) in BUZZERS:
    back.append(place(extrude(circle(bx, by, 7.7, 40), [circle(bx, by, 6.2, 40)], 8.2), (0, 1, 2), (0, 0, BOTTOM_Z + T - 0.2)))
back.append(place(extrude(circle(sx, sy, sid / 2 + 1.8, 96), [circle(sx, sy, sid / 2, 96)], 5.2), (0, 1, 2), (0, 0, BOTTOM_Z + T - 0.2)))

# ------------------------------------------------------------------ wheel (print 4): 7 round windows
wheel = [extrude(circle(0, 0, WHEEL_R, 96), [circle(11.5 * math.cos(math.radians(90 + 360 / 7 * k)), 11.5 * math.sin(math.radians(90 + 360 / 7 * k)), 3.4, 32) for k in range(7)], WHEEL_T),
         extrude(circle(0, 0, WHEEL_R, 96), [circle(0, 0, WHEEL_R - 2.6, 96)], WHEEL_T + 0.8),
         extrude(circle(0, 0, 4.2, 32), [], WHEEL_T + 1.2)]
wheels_placed = []
for (wx, wz) in WHEELS:
    for side in (0, 1):
        for w in wheel:
            if side == 0:
                t2 = np.stack([w[:, :, 0] + wx, -w[:, :, 2] - 0.0, w[:, :, 1] + wz], axis=-1)
            else:
                t2 = np.stack([w[:, :, 0] + wx, W + w[:, :, 2], w[:, :, 1] + wz], axis=-1)[:, [0, 2, 1], :]
            wheels_placed.append(t2)

# ------------------------------------------------------------------ glass parts
glass = [extrude(rect(0, 0, SCREEN_WIN[2] + 6.0, SCREEN_WIN[3] + 6.0, 3), [], 1.2),
         extrude(rect(0, 0, SEG7_POCKET[0] + 3.2, SEG7_POCKET[1] + 3.2), [rect(0, 0, SEG7_POCKET[0], SEG7_POCKET[1])], 5.2)]
side_glass = [extrude(SIDE_GLASS, [], 1.2)]
glass_placed = [cabin.on(C_SCREEN, g + np.array([gu, gv, 0]), T) for g in glass]
for yy in (CY0 + T, CY1 - T - 1.2):
    glass_placed.append(place(side_glass[0], (0, 2, 1), (0, yy, 0)))

# ------------------------------------------------------------------ write
os.makedirs("stl", exist_ok=True)
tb = write_stl("stl/hackclock_body.stl", body, "HackClock GT body")
bp = write_stl("stl/hackclock_bottom.stl", back, "HackClock GT bottom plate")
wl = write_stl("stl/hackclock_wheel.stl", wheel, "HackClock GT wheel")
gl = write_stl("stl/hackclock_windshield.stl", glass, "HackClock GT windshield")
sg = write_stl("stl/hackclock_side_glass.stl", side_glass, "HackClock GT side glass")
def _flip(t):
    t = np.array(t, float).copy(); t[..., 1] = W - t[..., 1]; t[..., 2] = 79.9 - t[..., 2]; return t     # print upside down (rotated 180 deg about x)
wg = write_stl("stl/hackclock_wing.stl", [_flip(p) for p in wing], "HackClock GT wing")
np.save("stl/_preview_wing.npy", np.concatenate(wing))
np.save("stl/_preview_body.npy", tb); np.save("stl/_preview_back.npy", bp)
np.save("stl/_preview_lid.npy", np.concatenate([body[i] for i in sorted(LID)]))
np.save("stl/_preview_base.npy", np.concatenate([body[i] for i in range(len(body)) if i not in LID]))
np.save("stl/_preview_wheels.npy", np.concatenate(wheels_placed)); np.save("stl/_preview_glass.npy", np.concatenate(glass_placed))
if __name__ == "__main__":
    print("body", len(tb), "bottom", len(bp), "wheel", len(wl), "windshield", len(gl), "side glass", len(sg))
