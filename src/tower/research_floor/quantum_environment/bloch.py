"""Bloch sphere coordinates + ASCII visualization for 1-qubit subsystems."""
from __future__ import annotations
import math
from typing import Dict, List

from .density import DensityMatrix


def bloch_vector(dm: DensityMatrix, qubit: int = 0) -> Dict[str, float]:
    """For a single qubit (possibly extracted via partial_trace), compute
    (x, y, z) = (<X>, <Y>, <Z>). The Bloch vector length r = sqrt(x²+y²+z²) ≤ 1.
    r = 1 for pure states, < 1 for mixed."""
    if dm.n == 1:
        reduced = dm
    else:
        reduced = dm.partial_trace([qubit])
    x = reduced.expectation("X")
    y = reduced.expectation("Y")
    z = reduced.expectation("Z")
    r = math.sqrt(x * x + y * y + z * z)
    return {"x": x, "y": y, "z": z, "r": r, "pure": r > 0.999}


def purity(dm: DensityMatrix) -> float:
    """Tr(ρ²). Pure → 1. Maximally mixed n-qubit → 1/2^n."""
    return dm.purity()


def ascii_bloch_z(z: float, width: int = 30) -> str:
    """One-line ASCII slice of the Bloch sphere's Z-axis."""
    pos = int(round((z + 1.0) / 2.0 * (width - 1)))
    line = ["·"] * width
    line[0] = "|"; line[-1] = "|"; line[width // 2] = "·"
    if 0 <= pos < width: line[pos] = "●"
    return f"  |1>  {''.join(line)}  |0>   z = {z:+.4f}"


def ascii_bloch_axes(b: dict, width: int = 30) -> str:
    """Three lines: one per Bloch axis."""
    def line(val: float, neg: str, pos_label: str) -> str:
        p = int(round((val + 1.0) / 2.0 * (width - 1)))
        c = ["·"] * width
        c[0] = "|"; c[-1] = "|"; c[width // 2] = "·"
        if 0 <= p < width: c[p] = "●"
        return f"  {neg}  {''.join(c)}  {pos_label}   = {val:+.4f}"
    out = []
    out.append(line(b['x'], "-X", "+X"))
    out.append(line(b['y'], "-Y", "+Y"))
    out.append(line(b['z'], "|1>", "|0>"))
    out.append(f"  Bloch length r = {b['r']:.4f}  " + ("●" * int(round(b['r'] * width))).ljust(width) + "  (1 = pure, 0 = maximally mixed)")
    return "\n".join(out)
