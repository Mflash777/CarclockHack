"""Tiny z-buffer rasterizer used by the preview renders (numpy only).

objs: list of (triangles[n,3,3], base_colour, mode)
  mode "solid": two-sided, lit using the normal that faces the camera (works for open / unoriented meshes)
  mode "flat" : unlit colour (screens, text panels)
"""
import numpy as np


def render(objs, elev, azim, size=(1000, 720), scale=3.4, center=(122, 58, 40)):
    el, az = np.radians(elev), np.radians(azim)
    v = np.array([np.cos(el) * np.sin(az), -np.cos(el) * np.cos(az), np.sin(el)])
    right = np.cross([0, 0, 1], v); right /= np.linalg.norm(right)
    up = np.cross(v, right)
    Wp, Hp = size
    img = np.ones((Hp, Wp, 3)); zbuf = np.full((Hp, Wp), -1e9)
    c = np.array(center, float)
    light = np.array([-0.3, -0.6, 0.75]); light /= np.linalg.norm(light)
    for tris, base, mode in objs:
        tris = np.asarray(tris, float)
        if len(tris) == 0:
            continue
        nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        ln = np.linalg.norm(nrm, axis=1)
        P = tris - c
        SX = Wp / 2 + scale * (P @ right); SY = Hp / 2 - scale * (P @ up); SZ = P @ v
        for k in range(len(tris)):
            if ln[k] < 1e-12:
                continue
            sx, sy, sz = SX[k], SY[k], SZ[k]
            x0, x1 = int(max(0, np.floor(sx.min()))), int(min(Wp - 1, np.ceil(sx.max())))
            y0, y1 = int(max(0, np.floor(sy.min()))), int(min(Hp - 1, np.ceil(sy.max())))
            if x0 > x1 or y0 > y1:
                continue
            if mode == "flat":
                col = np.array(base)
            else:
                n = nrm[k] / ln[k]
                if n @ v < 0:
                    n = -n
                shade = 0.35 + 0.65 * max(0.0, n @ light) + 0.12 * max(0.0, n @ v)
                col = np.clip(np.array(base) * shade, 0, 1)
            d = (sy[1] - sy[2]) * (sx[0] - sx[2]) + (sx[2] - sx[1]) * (sy[0] - sy[2])
            if abs(d) < 1e-9:
                continue
            X, Y = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            w0 = ((sy[1] - sy[2]) * (X - sx[2]) + (sx[2] - sx[1]) * (Y - sy[2])) / d
            w1 = ((sy[2] - sy[0]) * (X - sx[2]) + (sx[0] - sx[2]) * (Y - sy[2])) / d
            w2 = 1 - w0 - w1
            m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
            z = w0 * sz[0] + w1 * sz[1] + w2 * sz[2] + (0.03 if mode == "flat" else 0)
            zb = zbuf[y0:y1 + 1, x0:x1 + 1]
            m &= z > zb
            zb[m] = z[m]; img[y0:y1 + 1, x0:x1 + 1][m] = col

    def proj(Pt):
        p = np.array(Pt, float) - c
        return Wp / 2 + scale * (p @ right), Hp / 2 - scale * (p @ up)
    return img, proj
