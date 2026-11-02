#!/usr/bin/env python3
"""Renders pcb_data.json (written by generate_pcb.py) to a PNG preview."""
import json, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, FancyBboxPatch

d = json.load(open("pcb_data.json"))
W, H = d["board"]
fig, ax = plt.subplots(figsize=(12, 9.6), dpi=130)
fig.patch.set_facecolor("#0e1116")
ax.set_facecolor("#0e1116")
ax.add_patch(FancyBboxPatch((0, 0), W, H, boxstyle="round,pad=0,rounding_size=2", fc="#1b4d2e", ec="#e8d27a", lw=1.5))
for (L, a, b, w, net) in d["tracks"]:
    col = "#d9534f" if L == 0 else "#4a90e2"
    ax.plot([a[0], b[0]], [a[1], b[1]], color=col, lw=w * 7.2, solid_capstyle="round", alpha=0.85 if L == 0 else 0.7, zorder=3 if L == 0 else 2)
for (x, y, net) in d["vias"]:
    ax.add_patch(Circle((x, y), 0.4, fc="#c9b26b", ec="none", zorder=5))
    ax.add_patch(Circle((x, y), 0.2, fc="#0e1116", zorder=6))
for (x, y) in d["mount"]:
    ax.add_patch(Circle((x, y), 1.6, fc="#0e1116", ec="#ddd", lw=1, zorder=6))
for p in d["parts"]:
    xs = [pd[1] for pd in p["pads"]]; ys = [pd[2] for pd in p["pads"]]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    if p["ref"] == "U1":
        ax.add_patch(Rectangle((cx - 8.9, cy - 10.8), 17.8, 21, fill=False, ec="white", lw=1, ls="--", zorder=7))
        ax.text(cx, cy - 1, "XIAO\nESP32-S3", color="white", ha="center", va="center", fontsize=9, zorder=8)
        ax.add_patch(Rectangle((cx - 4.5, cy - 12.3), 9, 3, fc="#888", ec="white", zorder=7))
    for (num, x, y, net, shape, size, drill) in p["pads"]:
        if shape == "rect":
            ax.add_patch(Rectangle((x - size / 2, y - size / 2), size, size, fc="#e0b84a", zorder=6))
        else:
            ax.add_patch(Circle((x, y), size / 2, fc="#e0b84a", zorder=6))
        ax.add_patch(Circle((x, y), drill / 2, fc="#0e1116", zorder=7))
        if p["ref"] == "U1":
            left = x < cx
            ax.text(x + (-1.3 if left else 1.3), y, net.replace("TFT_", ""), color="#f5f5f5", fontsize=5,
                    ha="right" if left else "left", va="center", zorder=9)
        elif p["ref"] in ("J5", "J6", "J7", "J8"):
            right_edge = p["ref"] in ("J6", "J7")
            ax.text(x + (-1.3 if right_edge else 1.3), y, net.replace("TFT_", ""), color="#f5f5f5", fontsize=5,
                    ha="right" if right_edge else "left", va="center", zorder=9)
        elif p["ref"][0] == "J":
            ax.text(x, y + (1.9 if p["ref"] != "J5" else 0), net.replace("TFT_", ""), color="#f5f5f5", fontsize=4.6,
                    ha="center" if p["ref"] != "J5" else "left", va="center", rotation=90 if p["ref"] in "J1J2J3J4" else 0, zorder=9)
    lab_y = min(ys) - 1.8 if p["ref"][0] != "J" else max(ys) - 3.2
    if p["ref"] in ("J5", "J6", "J7", "J8"): lab_y = min(ys) - 2
    if p["ref"] != "U1":
        ax.text(cx, lab_y, f'{p["ref"]} {p["value"]}', color="#ffffff", fontsize=7, ha="center", zorder=9, fontweight="bold")
ax.text(W / 2, -2.2, "TOP: red = front copper, blue = back copper  |  GND pour added in KiCad (press B)",
        color="#bbb", ha="center", fontsize=9)
ax.text(W / 2, H + 2.6, "front of case (displays)  ↓", color="#bbb", ha="center", fontsize=9)
ax.set_xlim(-3, W + 3); ax.set_ylim(H + 4, -4); ax.set_aspect("equal"); ax.axis("off")
plt.tight_layout()
plt.savefig("../../docs/images/pcb_preview.png", facecolor=fig.get_facecolor())
print("ok")
