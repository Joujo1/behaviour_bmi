"""
Generates grid test sheets for camera resolution testing.
Prints to PDF — open and print at 100% scale (no scaling/fit to page).

Usage:
    python grid_test.py
"""

import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_pdf import PdfPages

A3_W_MM = 297
A3_H_MM = 420

GRID_SIZES_MM = [2, 5, 10, 20]  # square sizes to test


def draw_grid(ax, spacing_mm, page_w=A3_W_MM, page_h=A3_H_MM):
    ax.set_xlim(0, page_w)
    ax.set_ylim(0, page_h)
    ax.set_aspect("equal")
    ax.axis("off")

    # Vertical lines
    x = 0
    while x <= page_w:
        ax.axvline(x, color="black", linewidth=0.4)
        x += spacing_mm

    # Horizontal lines
    y = 0
    while y <= page_h:
        ax.axhline(y, color="black", linewidth=0.4)
        y += spacing_mm

    # Label
    ax.set_title(f"{spacing_mm} mm grid", fontsize=14, fontweight="bold", pad=10)

    # Scale bar (50mm)
    bar_x, bar_y = 10, page_h - 15
    ax.plot([bar_x, bar_x + 50], [bar_y, bar_y], color="black", linewidth=2)
    ax.text(bar_x + 25, bar_y + 3, "50 mm", ha="center", fontsize=9)


with PdfPages("grid_test.pdf") as pdf:
    for size in GRID_SIZES_MM:
        fig, ax = plt.subplots(figsize=(A3_W_MM / 25.4, A3_H_MM / 25.4))
        fig.subplots_adjust(left=0, right=1, top=0.95, bottom=0)
        draw_grid(ax, size)
        pdf.savefig(fig, dpi=300)
        plt.close(fig)
        print(f"Generated {size}mm grid")

print("Saved: grid_test.pdf  (4 pages — print on A3 at 100% scale, no fit-to-page)")
