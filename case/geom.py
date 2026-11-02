"""Small geometry kit: 2D shapes, polygon-with-holes extrusion (ear clipping), placement, STL writer."""
import math, struct, numpy as np

# ------------------------------------------------------------------ 2D helpers
def circle(cx, cy, r, n=None):
    n = n or max(16, int(r * 6))
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]

def rect(cx, cy, w, h, r=0.0):
    if r <= 0:
        return [(cx - w / 2, cy - h / 2), (cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy + h / 2)]
    pts = []
    for (qx, qy, a0) in [(cx + w / 2 - r, cy - h / 2 + r, -90), (cx + w / 2 - r, cy + h / 2 - r, 0),
                         (cx - w / 2 + r, cy + h / 2 - r, 90), (cx - w / 2 + r, cy - h / 2 + r, 180)]:
        for k in range(7):
            a = math.radians(a0 + k * 15)
            p = (round(qx + r * math.cos(a), 6), round(qy + r * math.sin(a), 6))
            if not pts or math.dist(p, pts[-1]) > 1e-6: pts.append(p)
    if math.dist(pts[0], pts[-1]) < 1e-6: pts.pop()
    return pts

def area(p):
    return 0.5 * sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))

def orient(p, ccw=True):
    return p if (area(p) > 0) == ccw else p[::-1]

def cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

def seg_intersect(p1, p2, p3, p4):
    d1, d2 = cross(p3, p4, p1), cross(p3, p4, p2)
    d3, d4 = cross(p1, p2, p3), cross(p1, p2, p4)
    return ((d1 > 1e-9 and d2 < -1e-9) or (d1 < -1e-9 and d2 > 1e-9)) and \
           ((d3 > 1e-9 and d4 < -1e-9) or (d3 < -1e-9 and d4 > 1e-9))

def bridge_holes(outer, holes):
    """Merge holes into the outer ring with zero-width bridges (classic ear-clipping prep)."""
    poly = orient(outer, True)[:]
    holes = [orient(h, False) for h in holes]
    holes.sort(key=lambda h: -max(p[0] for p in h))
    remaining = holes[:]
    while remaining:
        hole = remaining.pop(0)
        mi = max(range(len(hole)), key=lambda i: hole[i][0])
        M = hole[mi]
        edges = [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]
        for h in remaining + [hole]:
            edges += [(h[i], h[(i + 1) % len(h)]) for i in range(len(h))]
        best = None
        for j in sorted(range(len(poly)), key=lambda j: (poly[j][0] - M[0]) ** 2 + (poly[j][1] - M[1]) ** 2):
            V = poly[j]
            if all(not seg_intersect(M, V, a, b) for a, b in edges):
                best = j; break
        ring = hole[mi:] + hole[:mi + 1]
        poly = poly[:best + 1] + ring + [poly[best]] + poly[best + 1:]
    return poly

def earclip(poly):
    idx = list(range(len(poly)))
    tris = []
    guard = 0
    while len(idx) > 3 and guard < 100000:
        guard += 1
        n = len(idx); found = False
        for k in range(n):
            i0, i1, i2 = idx[(k - 1) % n], idx[k], idx[(k + 1) % n]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if cross(a, b, c) <= 1e-10: continue
            inside = False
            for m in idx:
                if m in (i0, i1, i2): continue
                p = poly[m]
                if p == a or p == b or p == c: continue
                if cross(a, b, p) >= -1e-10 and cross(b, c, p) >= -1e-10 and cross(c, a, p) >= -1e-10:
                    inside = True; break
            if inside: continue
            tris.append((i0, i1, i2)); idx.pop(k); found = True; break
        if not found:                          # degenerate leftovers - drop a sliver
            idx.pop(0)
    if len(idx) == 3: tris.append(tuple(idx))
    return tris

def extrude(outer, holes, h):
    """Returns list of triangles (3x3 arrays) for a prism of a polygon with holes, z in [0,h]."""
    poly = bridge_holes(outer, holes)
    tris2d = earclip(poly)
    out = []
    for (i, j, k) in tris2d:
        a, b, c = poly[i], poly[j], poly[k]
        out.append([(a[0], a[1], h), (b[0], b[1], h), (c[0], c[1], h)])
        out.append([(a[0], a[1], 0), (c[0], c[1], 0), (b[0], b[1], 0)])
    for ring in [orient(outer, True)] + [orient(hh, False) for hh in holes]:
        for i in range(len(ring)):
            a, b = ring[i], ring[(i + 1) % len(ring)]
            out.append([(a[0], a[1], 0), (b[0], b[1], 0), (b[0], b[1], h)])
            out.append([(a[0], a[1], 0), (b[0], b[1], h), (a[0], a[1], h)])
    return np.array(out)

def place(tris, axes, offset):
    """axes: tuple mapping local (u,v,w) -> global index, e.g. (0,2,1) puts w along y.
       Fixes winding if the mapping is a mirror."""
    M = np.zeros((3, 3))
    for li, gi in enumerate(axes): M[gi, li] = 1
    out = tris @ M.T + np.array(offset)
    if np.linalg.det(M) < 0: out = out[:, [0, 2, 1], :]
    return out


def place_basis(tris, origin, eu, ev, ew):
    """Map local (u,v,w) -> origin + u*eu + v*ev + w*ew; fixes winding for mirrored bases."""
    M = np.column_stack([eu, ev, ew]).astype(float)
    out = tris @ M.T + np.array(origin, float)
    if np.linalg.det(M) < 0: out = out[:, [0, 2, 1], :]
    return out

def write_stl(path, tri_lists, name):
    tris = np.concatenate(tri_lists)
    with open(path, "wb") as f:
        f.write(name.encode().ljust(80, b" "))
        f.write(struct.pack("<I", len(tris)))
        for t in tris:
            n = np.cross(t[1] - t[0], t[2] - t[0]); L = np.linalg.norm(n)
            n = n / L if L > 0 else n
            f.write(struct.pack("<12fH", *n, *t[0], *t[1], *t[2], 0))
    return tris

