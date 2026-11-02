#!/usr/bin/env python3
"""
Generates the HackClock carrier PCB as a KiCad 8 file (hackclock.kicad_pcb).

All parts are through-hole so it is easy to hand-solder. Footprints are defined
inline, so the file opens in KiCad without any extra libraries. Traces are laid
out by a small 2-layer grid router (below) and checked for clearance at the end.
After opening in KiCad: press B to fill the GND zones, run DRC, then
File > Fabrication Outputs > Gerbers + Drill files and upload the zip to JLCPCB/PCBWay.
"""
import heapq, math, uuid, json, sys

BOARD_W, BOARD_H = 80.0, 60.0
OX, OY = 100.0, 100.0          # board offset on the KiCad sheet
GRID = 0.5
CLEAR = 0.25                   # copper-to-copper clearance (JLCPCB min is 0.127)
MARGIN = 0.12                  # extra safety for diagonal discretisation
SIG_W, PWR_W = 0.4, 0.6
VIA_D, VIA_DRILL = 0.8, 0.4
EDGE_CLEAR = 0.6

NETS = ["", "GND", "+5V", "+3V3", "BTN", "MODE_N", "UP_N", "DOWN_N", "TALK_N", "TFT_DC", "TFT_CS",
        "TFT_SCK", "TFT_MOSI", "TFT_BL", "TFT_RST", "MIC_SCK", "MIC_WS", "MIC_SD", "SDA", "SCL",
        "BUZ", "Q_B", "BZ_N", "+5V_IN"]
NET_ID = {n: i for i, n in enumerate(NETS)}
POWER = {"GND", "+5V", "+3V3", "+5V_IN"}

def uid():
    return str(uuid.uuid4())

# ----------------------------------------------------------------------- parts
# Each part: ref, value, footprint name, list of pads (num, x, y, net, shape, size, drill), silk box
parts = []

def add_part(ref, value, fpname, pads, desc=""):
    parts.append(dict(ref=ref, value=value, fp=fpname, pads=pads, desc=desc))

def header_1xN(ref, value, x0, y0, nets, vertical=False, labels=None):
    pads = []
    for i, n in enumerate(nets):
        x = x0 if vertical else x0 + i * 2.54
        y = y0 + i * 2.54 if vertical else y0
        pads.append((str(i + 1), x, y, n, "rect" if i == 0 else "circle", 1.7, 1.0))
    add_part(ref, value, f"PinHeader_1x{len(nets):02d}_P2.54mm", pads, labels or "")

def axial(ref, value, x1, y, net1, net2, pitch=10.16, fp="R_Axial_P10.16mm"):
    add_part(ref, value, fp, [("1", x1, y, net1, "circle", 1.6, 0.8),
                              ("2", x1 + pitch, y, net2, "circle", 1.6, 0.8)])

def radial_cp(ref, value, x1, y, netp, netn, pitch=3.5):
    """polarised electrolytic, pad 1 (square) = +"""
    add_part(ref, value, "CP_Radial_D8.0mm_P3.50mm", [("1", x1, y, netp, "rect", 1.6, 0.8),
                                                        ("2", x1 + pitch, y, netn, "circle", 1.6, 0.8)], "+")

def radial_cap(ref, value, x1, y, net1, net2, pitch=5.08):
    add_part(ref, value, "C_Disc_P5.08mm", [("1", x1, y, net1, "circle", 1.6, 0.8),
                                             ("2", x1 + pitch, y, net2, "circle", 1.6, 0.8)])

# U1 - Seeed XIAO ESP32-S3 on two 1x7 female headers (USB-C points to the board's top edge)
ux, uy = 40.0, 6.0
left  = ["BTN", "TFT_DC", "TFT_CS", "BUZ", "SDA", "SCL", "MIC_SCK"]       # D0..D6
right = ["+5V", "GND", "+3V3", "TFT_MOSI", "MIC_SD", "TFT_SCK", "MIC_WS"]  # 5V,GND,3V3,D10,D9,D8,D7
upads = []
for i, n in enumerate(left):
    upads.append((str(i + 1), ux - 7.62, uy + i * 2.54, n, "rect" if i == 0 else "circle", 1.7, 1.0))
for i, n in enumerate(right):
    upads.append((str(8 + i), ux + 7.62, uy + i * 2.54, n, "circle", 1.7, 1.0))
add_part("U1", "XIAO_ESP32S3", "Seeed_XIAO_Socket", upads)

header_1xN("J1", "TFT", 10.0, 55.0, ["GND", "+3V3", "TFT_SCK", "TFT_MOSI", "TFT_RST", "TFT_DC", "TFT_CS", "TFT_BL"],
           labels="GND VCC SCL SDA RES DC CS BLK")
header_1xN("J2", "7SEG_I2C", 33.0, 55.0, ["GND", "+3V3", "SDA", "SCL"], labels="GND VCC SDA SCL")
header_1xN("J3", "RTC", 46.0, 55.0, ["GND", "+3V3", "SDA", "SCL"], labels="GND VCC SDA SCL")
header_1xN("J4", "BUTTONS", 59.0, 55.0, ["GND", "BTN", "MODE_N", "UP_N", "DOWN_N", "TALK_N"], labels="GND SNZ MOD UP DN TLK")
header_1xN("J6", "MIC", 76.0, 12.0, ["+3V3", "GND", "GND", "MIC_WS", "MIC_SCK", "MIC_SD"], vertical=True, labels="3V3 GND LR WS SCK SD")
header_1xN("J7", "AUDIO", 76.0, 29.0, ["+5V", "GND", "SDA", "SCL", "TFT_BL"], vertical=True, labels="5V GND SDA SCL BL")
header_1xN("J8", "5V_IN", 4.0, 8.0, ["+5V_IN", "GND"], vertical=True, labels="5V GND")
header_1xN("J5", "BUZZERS", 4.0, 22.0, ["+5V", "BZ_N"], vertical=True, labels="+5V BZ-")

# Q1 2N3904 TO-92, flat side facing you: E B C
add_part("Q1", "2N3904", "TO-92_Inline", [("1", 8.0, 33.0, "GND", "rect", 1.5, 0.8),
                                          ("2", 10.54, 33.0, "Q_B", "circle", 1.5, 0.8),
                                          ("3", 13.08, 33.0, "BZ_N", "circle", 1.5, 0.8)])
axial("R1", "1k", 6.0, 40.0, "BUZ", "Q_B")
axial("R2", "10k", 6.0, 46.0, "Q_B", "GND")
axial("D1", "1N4148", 6.0, 17.0, "+5V", "BZ_N", pitch=7.62, fp="D_DO-35_P7.62mm")  # pad1 = cathode (band)
axial("D2", "1N5819", 9.0, 4.5, "+5V", "+5V_IN", pitch=10.16, fp="D_DO-41_P10.16mm")  # reverse-polarity / backfeed protection
radial_cp("C5", "470uF", 22.0, 10.0, "+5V", "GND")                                   # amp current peaks

axial("R3", "10k", 56.0, 20.0, "+3V3", "BTN")
axial("R4", "2k2", 56.0, 26.0, "BTN", "MODE_N")
axial("R5", "4k7", 56.0, 32.0, "BTN", "UP_N")
axial("R6", "10k", 56.0, 38.0, "BTN", "DOWN_N")
radial_cap("C1", "100nF", 56.0, 44.0, "BTN", "GND")
axial("R8", "15k", 56.0, 50.0, "BTN", "TALK_N")

radial_cap("C2", "1uF", 22.0, 42.0, "TFT_RST", "GND")
axial("R7", "10k", 22.0, 48.0, "TFT_RST", "+3V3")

radial_cap("C3", "10uF", 54.0, 11.0, "+3V3", "GND")
radial_cap("C4", "10uF", 54.0, 6.0, "+5V", "GND")

MOUNT = [(3.5, 3.5), (BOARD_W - 3.5, 3.5), (3.5, BOARD_H - 3.5), (BOARD_W - 3.5, BOARD_H - 3.5)]

# ----------------------------------------------------------------------- router
NX, NY = int(BOARD_W / GRID) + 1, int(BOARD_H / GRID) + 1
FREE, MULTI = 0, -1
owner = [[[FREE] * NY for _ in range(NX)] for _ in range(2)]   # owner[layer][ix][iy]

def cell_xy(ix, iy):
    return ix * GRID, iy * GRID

def mark_disc(layer, x, y, radius, net):
    r = radius
    for ix in range(max(0, int((x - r) / GRID) - 1), min(NX, int((x + r) / GRID) + 2)):
        for iy in range(max(0, int((y - r) / GRID) - 1), min(NY, int((y + r) / GRID) + 2)):
            cx, cy = cell_xy(ix, iy)
            if (cx - x) ** 2 + (cy - y) ** 2 < r * r:
                o = owner[layer][ix][iy]
                if o == FREE: owner[layer][ix][iy] = net
                elif o != net: owner[layer][ix][iy] = MULTI

def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

def mark_seg(layer, a, b, half, net):
    r = half + CLEAR + PWR_W / 2 + MARGIN
    (ax, ay), (bx, by) = a, b
    for ix in range(max(0, int((min(ax, bx) - r) / GRID) - 1), min(NX, int((max(ax, bx) + r) / GRID) + 2)):
        for iy in range(max(0, int((min(ay, by) - r) / GRID) - 1), min(NY, int((max(ay, by) + r) / GRID) + 2)):
            cx, cy = cell_xy(ix, iy)
            if seg_dist(cx, cy, ax, ay, bx, by) < r:
                o = owner[layer][ix][iy]
                if o == FREE: owner[layer][ix][iy] = net
                elif o != net: owner[layer][ix][iy] = MULTI

# edges + mounting holes block everything
for L in range(2):
    for ix in range(NX):
        for iy in range(NY):
            x, y = cell_xy(ix, iy)
            if x < EDGE_CLEAR + PWR_W / 2 or y < EDGE_CLEAR + PWR_W / 2 or \
               x > BOARD_W - EDGE_CLEAR - PWR_W / 2 or y > BOARD_H - EDGE_CLEAR - PWR_W / 2:
                owner[L][ix][iy] = MULTI
    for (mx, my) in MOUNT:
        mark_disc(L, mx, my, 3.2 + CLEAR + PWR_W / 2, MULTI)   # covers the M3 screw head too

pad_list = []
for p in parts:
    for (num, x, y, net, shape, size, drill) in p["pads"]:
        pad_list.append((x, y, net, shape, size))
        eff = size / 2 * (1.42 if shape == "rect" else 1.0)
        for L in range(2):
            mark_disc(L, x, y, eff + CLEAR + PWR_W / 2 + MARGIN, NET_ID[net])

tracks, vias = [], []          # tracks: (layer, (x1,y1), (x2,y2), width, net)
net_cells = {}                 # net -> set of (layer, ix, iy) already connected

def snap(x, y):
    return int(round(x / GRID)), int(round(y / GRID))

def route(net, src, targets):
    """Dijkstra from src cells to any cell in targets, 2 layers, 8-way + vias."""
    nid = NET_ID[net]
    INF = float("inf")
    dist = {}
    prev = {}
    pq = []
    for s in src:
        dist[s] = 0; heapq.heappush(pq, (0, s))
    dirs = [(1, 0, 1), (-1, 0, 1), (0, 1, 1), (0, -1, 1),
            (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414)]
    def ok(L, ix, iy):
        if not (0 <= ix < NX and 0 <= iy < NY): return False
        o = owner[L][ix][iy]
        return o == FREE or o == nid
    def via_ok(ix, iy):
        rr = int(math.ceil((VIA_D / 2 + CLEAR + PWR_W / 2 - 0.55) / GRID))
        for L in range(2):
            for dx in range(-rr, rr + 1):
                for dy in range(-rr, rr + 1):
                    if not ok(L, ix + dx, iy + dy): return False
        return True
    found = None
    while pq:
        d, cur = heapq.heappop(pq)
        if d > dist.get(cur, INF): continue
        if cur in targets: found = cur; break
        L, ix, iy = cur
        for dx, dy, c in dirs:
            nx, ny = ix + dx, iy + dy
            if not ok(L, nx, ny): continue
            if dx and dy and not (ok(L, ix + dx, iy) or ok(L, ix, iy + dy)): continue
            cost = c * (1.0 if L == 0 else 1.15)
            # prefer horizontal on top, vertical on bottom (classic 2-layer style)
            if L == 0 and dy and not dx: cost *= 1.3
            if L == 1 and dx and not dy: cost *= 1.3
            nxt = (L, nx, ny); nd = d + cost
            if nd < dist.get(nxt, INF):
                dist[nxt] = nd; prev[nxt] = cur; heapq.heappush(pq, (nd, nxt))
        other = (1 - L, ix, iy)
        if via_ok(ix, iy):
            nd = d + 12
            if nd < dist.get(other, INF):
                dist[other] = nd; prev[other] = cur; heapq.heappush(pq, (nd, other))
    if not found: return None
    path = [found]
    while path[-1] in prev: path.append(prev[path[-1]])
    return path[::-1]

def commit(net, path, width):
    nid = NET_ID[net]
    # split into runs per layer, merge collinear steps
    runs = []
    cur = [path[0]]
    for a in path[1:]:
        if a[0] != cur[-1][0]:
            runs.append(cur)
            x, y = cell_xy(a[1], a[2]); vias.append((x, y, net))
            for L in range(2): mark_disc(L, x, y, VIA_D / 2 + CLEAR + PWR_W / 2 + MARGIN, nid)
            cur = [a]
        else:
            cur.append(a)
    runs.append(cur)
    for run in runs:
        L = run[0][0]
        pts = [cell_xy(c[1], c[2]) for c in run]
        simp = [pts[0]]
        for i in range(1, len(pts) - 1):
            d1 = (pts[i][0] - simp[-1][0], pts[i][1] - simp[-1][1])
            d2 = (pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
            if abs(d1[0] * d2[1] - d1[1] * d2[0]) > 1e-9: simp.append(pts[i])
        if len(pts) > 1: simp.append(pts[-1])
        for a, b in zip(simp, simp[1:]):
            tracks.append((L, a, b, width, net))
            mark_seg(L, a, b, width / 2, nid)
    for c in path: net_cells.setdefault(net, set()).add(c)

net_pads = {}
for p in parts:
    for (num, x, y, net, *_ ) in p["pads"]:
        net_pads.setdefault(net, []).append((x, y))

order = ["BUZ", "Q_B", "BZ_N", "MIC_SCK", "MIC_WS", "MIC_SD", "TFT_DC", "TFT_CS", "TFT_SCK", "TFT_MOSI", "TFT_RST",
         "TFT_BL", "SDA", "SCL", "MODE_N", "UP_N", "DOWN_N", "TALK_N", "BTN", "+5V_IN", "+5V", "+3V3", "GND"]
import os
if os.environ.get("HC_ORDER"): order = os.environ["HC_ORDER"].split(",")
unrouted = []
for net in order:
    pads = net_pads[net][:]
    width = PWR_W if net in POWER else SIG_W
    # start from the pad closest to the board centre, grow a tree pad by pad (nearest first)
    start = pads.pop(0)
    sx, sy = snap(*start)
    tree = {(0, sx, sy), (1, sx, sy)}
    while pads:
        pads.sort(key=lambda p: min(math.hypot(p[0] - c[1] * GRID, p[1] - c[2] * GRID) for c in tree))
        p = pads.pop(0)
        ix, iy = snap(*p)
        path = route(net, [(0, ix, iy), (1, ix, iy)], tree)
        if not path:
            unrouted.append((net, p)); continue
        commit(net, path, width)
        tree |= set(path)
        tree |= {(0, ix, iy), (1, ix, iy)}

# ----------------------------------------------------------------------- DRC
def min_clearance():
    items = []   # (kind, layer(s), geom, half, net)
    for (x, y, net, shape, size) in pad_list:
        items.append(("pad", (0, 1), ((x, y), (x, y)), size / 2 * (1.42 if shape == "rect" else 1), net))
    for (x, y, net) in vias:
        items.append(("via", (0, 1), ((x, y), (x, y)), VIA_D / 2, net))
    for (L, a, b, w, net) in tracks:
        items.append(("trk", (L,), (a, b), w / 2, net))
    worst = (9e9, None)
    def sdist(s1, s2):
        (a, b), (c, d) = s1, s2
        return min(seg_dist(*a, *c, *d), seg_dist(*b, *c, *d), seg_dist(*c, *a, *b), seg_dist(*d, *a, *b))
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            A, B = items[i], items[j]
            if A[4] == B[4] or not set(A[1]) & set(B[1]): continue
            g = sdist(A[2], B[2]) - A[3] - B[3]
            if g < worst[0]: worst = (g, (A[0], A[4], B[0], B[4], A[2][0]))
    return worst

# ----------------------------------------------------------------------- KiCad writer
def fmt(v): return f"{v:.4f}".rstrip("0").rstrip(".")

def footprint(p):
    xs = [pd[1] for pd in p["pads"]]; ys = [pd[2] for pd in p["pads"]]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    out = [f'  (footprint "HackClock:{p["fp"]}" (layer "F.Cu") (uuid "{uid()}") (at {fmt(OX + cx)} {fmt(OY + cy)})']
    ref_y = min(ys) - cy - 2.0 if p["ref"] not in ("J1", "J2", "J3", "J4") else max(ys) - cy - 3.0
    if p["ref"] == "U1": ref_y = 0
    out.append(f'    (property "Reference" "{p["ref"]}" (at 0 {fmt(ref_y)} 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 1 1) (thickness 0.15))))')
    out.append(f'    (property "Value" "{p["value"]}" (at 0 {fmt(max(ys) - cy + 2)} 0) (layer "F.Fab") (uuid "{uid()}") (effects (font (size 1 1) (thickness 0.15))))')
    out.append(f'    (property "Footprint" "HackClock:{p["fp"]}" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{uid()}") (effects (font (size 1 1))))')
    # silk outline
    if p["ref"] == "U1":
        w, h = 17.8, 21.0; ox, oy = 0, -0.3
    else:
        w = max(xs) - min(xs) + 2.6; h = max(ys) - min(ys) + 2.6; ox = oy = 0
    x1, y1, x2, y2 = ox - w / 2, oy - h / 2, ox + w / 2, oy + h / 2
    for (a, b, c, d) in [(x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)]:
        out.append(f'    (fp_line (start {fmt(a)} {fmt(b)}) (end {fmt(c)} {fmt(d)}) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{uid()}"))')
    if p["ref"] == "U1":
        out.append(f'    (fp_text user "USB-C" (at 0 -8.5 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 0.8 0.8) (thickness 0.12))))')
    if p["desc"]:
        lab_y = (y1 - 1.0) if p["ref"] in ("J1", "J2", "J3", "J4") else (y2 + 1.0)
        if p["ref"] in ("J5", "J8"):
            out.append(f'    (fp_text user "{p["desc"]}" (at 2.6 0 90) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 0.7 0.7) (thickness 0.1))))')
        elif p["ref"] in ("J6", "J7"):
            out.append(f'    (fp_text user "{p["desc"]}" (at -2.6 0 90) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 0.7 0.7) (thickness 0.1))))')
        elif p["fp"].startswith("CP_"):
            out.append(f'    (fp_circle (center 0 0) (end 4 0) (stroke (width 0.12) (type solid)) (fill none) (layer "F.SilkS") (uuid "{uid()}"))')
            out.append(f'    (fp_text user "+" (at -3.2 -2.2 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 1 1) (thickness 0.15))))')
        else:
            out.append(f'    (fp_text user "{p["desc"]}" (at 0 {fmt(lab_y)} 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 0.7 0.7) (thickness 0.1))))')
    if p["fp"].startswith("D_"):   # cathode band
        out.append(f'    (fp_line (start {fmt(x1 + 1.8)} {fmt(y1)}) (end {fmt(x1 + 1.8)} {fmt(y2)}) (stroke (width 0.3) (type solid)) (layer "F.SilkS") (uuid "{uid()}"))')
    for (num, x, y, net, shape, size, drill) in p["pads"]:
        out.append(f'    (pad "{num}" thru_hole {shape} (at {fmt(x - cx)} {fmt(y - cy)}) (size {fmt(size)} {fmt(size)}) (drill {fmt(drill)}) '
                   f'(layers "*.Cu" "*.Mask") (net {NET_ID[net]} "{net}") (uuid "{uid()}"))')
    out.append("  )")
    return "\n".join(out)

def board():
    L = []
    L.append('(kicad_pcb (version 20240108) (generator "hackclock_gen") (generator_version "8.0")')
    L.append('  (general (thickness 1.6) (legacy_teardrops no))')
    L.append('  (paper "A4")')
    L.append('  (title_block (title "HackClock carrier board") (rev "2.0") (company "Hack Club Half Life"))')
    L.append('''  (layers
    (0 "F.Cu" signal) (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive") (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user) (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user) (39 "F.Mask" user)
    (40 "Dwgs.User" user "User.Drawings") (41 "Cmts.User" user "User.Comments")
    (42 "Eco1.User" user "User.Eco1") (43 "Eco2.User" user "User.Eco2")
    (44 "Edge.Cuts" user) (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard") (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user) (49 "F.Fab" user)
  )''')
    L.append('''  (setup
    (pad_to_mask_clearance 0)
    (allow_soldermask_bridges_in_footprints no)
    (pcbplotparams (layerselection 0x00010fc_ffffffff) (plot_on_all_layers_selection 0x0000000_00000000)
      (disableapertmacros no) (usegerberextensions no) (usegerberattributes yes) (usegerberadvancedattributes yes)
      (creategerberjobfile yes) (dashed_line_dash_ratio 12.000000) (dashed_line_gap_ratio 3.000000)
      (svgprecision 4) (plotframeref no) (viasonmask no) (mode 1) (useauxorigin no) (hpglpennumber 1)
      (hpglpenspeed 20) (hpglpendiameter 15.000000) (pdf_front_fp_property_popups yes) (pdf_back_fp_property_popups yes)
      (dxfpolygonmode yes) (dxfimperialunits yes) (dxfusepcbnewfont yes) (psnegative no) (psa4output no)
      (plotreference yes) (plotvalue yes) (plotfptext yes) (plotinvisibletext no) (sketchpadsonfab no)
      (subtractmaskfromsilk no) (outputformat 1) (mirror no) (drillshape 0) (scaleselection 1)
      (outputdirectory "gerbers/"))
  )''')
    for i, n in enumerate(NETS):
        L.append(f'  (net {i} "{n}")')
    for p in parts:
        L.append(footprint(p))
    # mounting holes (NPTH M3)
    for i, (x, y) in enumerate(MOUNT):
        L.append(f'  (footprint "HackClock:MountingHole_3.2mm_M3" (layer "F.Cu") (uuid "{uid()}") (at {fmt(OX + x)} {fmt(OY + y)})')
        L.append(f'    (property "Reference" "H{i + 1}" (at 0 -3.2 0) (layer "F.Fab") (uuid "{uid()}") (effects (font (size 1 1) (thickness 0.15))))')
        L.append(f'    (property "Value" "M3" (at 0 3.2 0) (layer "F.Fab") (uuid "{uid()}") (effects (font (size 1 1) (thickness 0.15))))')
        L.append(f'    (attr exclude_from_pos_files exclude_from_bom)')
        L.append(f'    (fp_circle (center 0 0) (end 3.2 0) (stroke (width 0.12) (type solid)) (fill none) (layer "F.SilkS") (uuid "{uid()}"))')
        L.append(f'    (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu" "*.Mask") (uuid "{uid()}"))')
        L.append('  )')
    # board outline with rounded corners
    r = 2.0
    x0, y0, x1, y1 = OX, OY, OX + BOARD_W, OY + BOARD_H
    for (a, b) in [((x0 + r, y0), (x1 - r, y0)), ((x1, y0 + r), (x1, y1 - r)),
                   ((x1 - r, y1), (x0 + r, y1)), ((x0, y1 - r), (x0, y0 + r))]:
        L.append(f'  (gr_line (start {fmt(a[0])} {fmt(a[1])}) (end {fmt(b[0])} {fmt(b[1])}) (stroke (width 0.1) (type default)) (layer "Edge.Cuts") (uuid "{uid()}"))')
    s = r * (1 - math.sqrt(0.5))
    for (sx, sy, mx, my, ex, ey) in [(x0, y0 + r, x0 + s, y0 + s, x0 + r, y0), (x1 - r, y0, x1 - s, y0 + s, x1, y0 + r),
                                     (x1, y1 - r, x1 - s, y1 - s, x1 - r, y1), (x0 + r, y1, x0 + s, y1 - s, x0, y1 - r)]:
        L.append(f'  (gr_arc (start {fmt(sx)} {fmt(sy)}) (mid {fmt(mx)} {fmt(my)}) (end {fmt(ex)} {fmt(ey)}) (stroke (width 0.1) (type default)) (layer "Edge.Cuts") (uuid "{uid()}"))')
    # silkscreen titles
    L.append(f'  (gr_text "HackClock v2.0" (at {fmt(OX + 22)} {fmt(OY + 26)} 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 1.5 1.5) (thickness 0.25))))')
    L.append(f'  (gr_text "Hack Club Half Life" (at {fmt(OX + 22)} {fmt(OY + 28.5)} 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 0.9 0.9) (thickness 0.15))))')
    L.append(f'  (gr_text "BACK OF CASE  ^" (at {fmt(OX + 22)} {fmt(OY + 2.2)} 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 0.8 0.8) (thickness 0.12))))')
    L.append(f'  (gr_text "FRONT OF CASE (displays)" (at {fmt(OX + 40)} {fmt(OY + 58.6)} 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 0.8 0.8) (thickness 0.12))))')
    # tracks / vias
    layer_name = {0: "F.Cu", 1: "B.Cu"}
    for (Ly, a, b, w, net) in tracks:
        L.append(f'  (segment (start {fmt(OX + a[0])} {fmt(OY + a[1])}) (end {fmt(OX + b[0])} {fmt(OY + b[1])}) (width {fmt(w)}) (layer "{layer_name[Ly]}") (net {NET_ID[net]}) (uuid "{uid()}"))')
    for (x, y, net) in vias:
        L.append(f'  (via (at {fmt(OX + x)} {fmt(OY + y)}) (size {VIA_D}) (drill {VIA_DRILL}) (layers "F.Cu" "B.Cu") (net {NET_ID[net]}) (uuid "{uid()}"))')
    # GND pour on both layers (press B in KiCad to fill)
    for layer in ("F.Cu", "B.Cu"):
        L.append(f'''  (zone (net {NET_ID["GND"]}) (net_name "GND") (layer "{layer}") (uuid "{uid()}") (hatch edge 0.5)
    (connect_pads (clearance 0.3)) (min_thickness 0.25) (filled_areas_thickness no)
    (fill (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon (pts (xy {fmt(OX + 0.5)} {fmt(OY + 0.5)}) (xy {fmt(OX + BOARD_W - 0.5)} {fmt(OY + 0.5)}) (xy {fmt(OX + BOARD_W - 0.5)} {fmt(OY + BOARD_H - 0.5)}) (xy {fmt(OX + 0.5)} {fmt(OY + BOARD_H - 0.5)})))
  )''')
    L.append(")")
    return "\n".join(L)

with open("hackclock.kicad_pcb", "w") as f:
    f.write(board())

# minimal project file so KiCad opens it as a project
with open("hackclock.kicad_pro", "w") as f:
    json.dump({"board": {"design_settings": {"rules": {"min_clearance": 0.2, "min_track_width": 0.2,
               "min_via_diameter": 0.6, "min_through_hole_diameter": 0.3}}},
               "meta": {"filename": "hackclock.kicad_pro", "version": 1}}, f, indent=2)

# netlist / data for the preview + schematic scripts
with open("pcb_data.json", "w") as f:
    json.dump({"parts": parts, "tracks": tracks, "vias": vias, "mount": MOUNT,
               "board": [BOARD_W, BOARD_H]}, f)

if unrouted and int(os.environ.get("HC_TRY", "0")) < 12:
    # retry with the nets that failed routed first
    failed = []
    for n, _ in unrouted:
        if n not in failed: failed.append(n)
    new_order = failed + [n for n in order if n not in failed]
    env = dict(os.environ, HC_ORDER=",".join(new_order), HC_TRY=str(int(os.environ.get("HC_TRY", "0")) + 1))
    print(f"retry {env['HC_TRY']}: unrouted {failed}")
    os.execve(sys.executable, [sys.executable, __file__], env)

worst = min_clearance()
print(f"parts={len(parts)} tracks={len(tracks)} vias={len(vias)} unrouted={unrouted}")
print(f"min copper clearance = {worst[0]:.3f} mm  ({worst[1]})")
sys.exit(1 if unrouted else 0)
