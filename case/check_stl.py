#!/usr/bin/env python3
"""Sanity-checks the generated case: every piece closed (watertight), normals outward, sizes."""
import numpy as np, collections, importlib.util, io, contextlib, struct

spec = importlib.util.spec_from_file_location("cg", "case_gen.py"); cg = importlib.util.module_from_spec(spec)
with contextlib.redirect_stdout(io.StringIO()): spec.loader.exec_module(cg)

def check(t):
    vol = np.sum(np.einsum('ij,ij->i', t[:, 0], np.cross(t[:, 1], t[:, 2]))) / 6
    edges = collections.Counter()
    for tri in np.round(t, 4):
        for a, b in ((0, 1), (1, 2), (2, 0)):
            edges[(tuple(tri[a]), tuple(tri[b]))] += 1
    bad = sum(1 for (a, b), c in edges.items() if edges.get((b, a), 0) != c)
    return vol, bad

ok = True
for label, parts in (("body", cg.body), ("bottom", cg.back), ("wheel", cg.wheel), ("glass", cg.glass), ("side glass", cg.side_glass), ("wing", cg.wing)):
    for i, p in enumerate(parts):
        v, b = check(p)
        if v <= 0 or b: ok = False; print(f"{label} piece {i}: volume {v:.1f}, open edges {b}")

def load(path):
    d = open(path, 'rb').read(); n = struct.unpack('<I', d[80:84])[0]
    a = np.frombuffer(d[84:], dtype=np.dtype([('n', '<3f4'), ('v', '<9f4'), ('a', '<u2')]), count=n)
    return a['v'].reshape(-1, 3, 3).astype(float)

for f in ["body", "bottom", "wheel", "windshield", "side_glass", "wing"]:
    t = load(f"stl/hackclock_{f}.stl"); v = np.sum(np.einsum('ij,ij->i', t[:, 0], np.cross(t[:, 1], t[:, 2]))) / 6
    lo, hi = t.reshape(-1, 3).min(0), t.reshape(-1, 3).max(0)
    print(f"hackclock_{f}.stl: {len(t)} triangles, signed volume {v/1000:.1f} cm3, size {np.round(hi - lo, 1)} mm")
    ok &= v > 0
print("ALL PIECES CLOSED + OUTWARD" if ok else "PROBLEMS FOUND")
