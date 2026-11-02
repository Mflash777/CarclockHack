#!/usr/bin/env python3
"""Preview renders of the HackClock GT case (z-buffer rasterizer). Run case_gen.py first."""
import numpy as np, matplotlib, math
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import importlib.util, io, contextlib
spec = importlib.util.spec_from_file_location("cg", "case_gen.py"); cg = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()): spec.loader.exec_module(cg)
from geom import extrude, rect, circle, place, place_basis

body = np.load("stl/_preview_body.npy")
wheels = np.load("stl/_preview_wheels.npy")
glass = np.load("stl/_preview_glass.npy")
wing = np.load("stl/_preview_wing.npy")
W = cg.W

def quad(p0, p1, p2, p3): return np.array([[p0, p1, p2], [p0, p2, p3]], float)

# props
tx, tz = cg.TFT_WIN[0], cg.TFT_WIN[1]
tft = quad([tx - 21, -0.05, tz - 16], [tx + 21, -0.05, tz - 16], [tx + 21, -0.05, tz + 16], [tx - 21, -0.05, tz + 16])
pu, pv, pd, _ = cg.PUCK
puck = cg.cabin.on(cg.C_ROOF, extrude(circle(pu, pv, pd / 2 - 0.3, 64), [], 0.6), -0.1)
watch = cg.cabin.on(cg.C_ROOF, extrude(circle(pu, pv, 23.5, 64), [], 11.0), -11.2)
bezel = cg.cabin.on(cg.C_ROOF, extrude(circle(pu, pv, 21.0, 64), [circle(pu, pv, 18.5, 64)], 1.0), -12.2)
band = cg.cabin.on(cg.C_ROOF, extrude(rect(pu, pv - 36, 20, 26, 3), [], 3.5), -4.0)     # strap runs side to side
band2 = cg.cabin.on(cg.C_ROOF, extrude(rect(pu, pv + 36, 20, 26, 3), [], 3.5), -4.0)
def render(objs, elev, azim, size=(1000, 720), scale=3.4, center=(122, 58, 40)):
    el, az = np.radians(elev), np.radians(azim)
    v = np.array([np.cos(el) * np.sin(az), -np.cos(el) * np.cos(az), np.sin(el)])
    right = np.cross([0, 0, 1], v); right /= np.linalg.norm(right)
    up = np.cross(v, right)
    Wp, Hp = size
    img = np.ones((Hp, Wp, 3)); zbuf = np.full((Hp, Wp), -1e9)
    c = np.array(center, float)
    light = np.array([-0.3, -0.6, 0.75]); light /= np.linalg.norm(light)
    for tris, base, flat in objs:
        for t in tris:
            n = np.cross(t[1] - t[0], t[2] - t[0]); ln = np.linalg.norm(n)
            if ln < 1e-12: continue
            n /= ln
            if not flat and n @ v <= 0: continue
            k = 1.0 if flat else 0.35 + 0.65 * max(0.0, n @ light) + 0.12 * max(0, n @ v)
            col = np.clip(np.array(base) * k, 0, 1)
            p = t - c
            sx = Wp / 2 + scale * (p @ right); sy = Hp / 2 - scale * (p @ up); sz = p @ v
            x0, x1 = int(max(0, np.floor(sx.min()))), int(min(Wp - 1, np.ceil(sx.max())))
            y0, y1 = int(max(0, np.floor(sy.min()))), int(min(Hp - 1, np.ceil(sy.max())))
            if x0 > x1 or y0 > y1: continue
            X, Y = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            d = (sy[1] - sy[2]) * (sx[0] - sx[2]) + (sx[2] - sx[1]) * (sy[0] - sy[2])
            if abs(d) < 1e-9: continue
            w0 = ((sy[1] - sy[2]) * (X - sx[2]) + (sx[2] - sx[1]) * (Y - sy[2])) / d
            w1 = ((sy[2] - sy[0]) * (X - sx[2]) + (sx[0] - sx[2]) * (Y - sy[2])) / d
            w2 = 1 - w0 - w1
            m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            z = w0 * sz[0] + w1 * sz[1] + w2 * sz[2] + (0.03 if flat else 0)
            zb = zbuf[y0:y1 + 1, x0:x1 + 1]
            m &= z > zb
            zb[m] = z[m]; img[y0:y1 + 1, x0:x1 + 1][m] = col
    def proj(P):
        p = np.array(P, float) - c
        return Wp / 2 + scale * (p @ right), Hp / 2 - scale * (p @ up)
    return img, proj

PEARL, DARK, SMOKE = (0.93, 0.93, 0.95), (0.13, 0.13, 0.15), (0.10, 0.10, 0.13)
fig, axs = plt.subplots(2, 1, figsize=(12, 15), dpi=120)

img, proj = render([(body, PEARL, False), (wing, PEARL, False), (wheels, DARK, False), (glass, SMOKE, False),
                    (tft, (0.05, 0.10, 0.22), True), (puck, (0.75, 0.75, 0.78), False), (watch, (0.12, 0.12, 0.13), False),
                    (bezel, (0.55, 0.55, 0.58), False), (band, (0.2, 0.2, 0.22), False), (band2, (0.2, 0.2, 0.22), False)], 22, -38)
axs[0].imshow(img); axs[0].axis("off")
# digits on the windshield and text on the door screen
o, eu, ev, ew = cg.cabin.basis(cg.C_SCREEN)
gcen = o + cg.SCREEN_WIN[0] * eu + cg.SCREEN_WIN[1] * ev - 0.5 * ew
x, y = proj(gcen); axs[0].text(x, y, "7:45", color="#ff4136", fontsize=22, ha="center", va="center", family="monospace", fontweight="bold", rotation=-8)
x, y = proj([tx, -1, tz]); axs[0].text(x, y, "AAPL +1.2%\n58°F Rain\nAlarm 6:30", color="#9fdcff", fontsize=8, ha="center", va="center", family="monospace")
axs[0].set_title("HackClock GT - front/left: time on the windshield, screen in the door, watch on its charger in the middle of the roof", fontsize=11)

img2, proj2 = render([(body, PEARL, False), (wing, PEARL, False), (wheels, DARK, False), (glass, SMOKE, False), (puck, (0.75, 0.75, 0.78), False),
                      (watch, (0.12, 0.12, 0.13), False), (bezel, (0.55, 0.55, 0.58), False), (band, (0.2, 0.2, 0.22), False),
                      (band2, (0.2, 0.2, 0.22), False)], 26, 125)
axs[1].imshow(img2); axs[1].axis("off")
axs[1].set_title("Rear: USB-C power + one USB-A pass-through in the tail, watch charger on the roof", fontsize=11)
plt.tight_layout()
plt.savefig("../docs/images/case_render.png", facecolor="white")
print("ok")
