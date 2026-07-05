#!/usr/bin/env bash
# qsb_research_quantum_env.sh — F37 Quantum Environment (open quantum systems).
# Usage:
#   qsb_research_quantum_env.sh bell-decay        # Bell pair under depolarizing noise
#   qsb_research_quantum_env.sh chsh-noise        # CHSH violation vs noise level
#   qsb_research_quantum_env.sh bloch <p>          # Bloch vector of |+> under depolarizing(p)
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CMD="${1:-bell-decay}"

case "${CMD}" in
  bell-decay)
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.research_floor.quantum_environment import bell_decay_study
r = bell_decay_study()
print(f"  {r['experiment']}")
print(f"  {r['verdict']}")
print()
print(f"  {'p':>6}  {'<XX>':>9}  {'<YY>':>9}  {'<ZZ>':>9}  {'fidelity':>9}  {'purity':>9}  {'q0 S(bits)':>12}")
print(f"  ──────  ─────────  ─────────  ─────────  ─────────  ─────────  ────────────")
for row in r['rows']:
    print(f"  {row['noise_p']:>6.2f}  {row['<XX>']:>+9.4f}  {row['<YY>']:>+9.4f}  {row['<ZZ>']:>+9.4f}  {row['bell_fidelity']:>9.4f}  {row['purity']:>9.4f}  {row['q0_entropy_bits']:>12.4f}")
PY
    ;;
  chsh-noise)
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.research_floor.quantum_environment import chsh_under_noise_study
r = chsh_under_noise_study()
print(f"  {r['experiment']}")
print(f"  classical_bound = {r['classical_bound']}   tsirelson = {r['tsirelson_bound']:.4f}")
print()
print(f"  {'p':>6}  {'E00':>8}  {'E01':>8}  {'E10':>8}  {'E11':>8}  {'S':>8}  {'frac':>6}  violation?")
print(f"  ──────  ────────  ────────  ────────  ────────  ────────  ──────  ──────────")
for row in r['rows']:
    print(f"  {row['noise_p']:6.2f}  {row['E00']:+8.4f}  {row['E01']:+8.4f}  {row['E10']:+8.4f}  {row['E11']:+8.4f}  {row['S']:+8.4f}  {row['fraction_of_tsirelson']:6.2%}  {'YES ↯ ' if row['violates_classical'] else '  no   '}")
print()
print(f"  {r['verdict']}")
PY
    ;;
  bloch)
    P="${2:-0.0}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.research_floor.quantum_environment import DensityMatrix, depolarizing, bloch_vector
from src.tower.research_floor.quantum_environment.bloch import ascii_bloch_axes
from src.tower.research_floor.quantum_triad_sandbox.quantum_lane import Gates

dm = DensityMatrix(1)
dm.apply_unitary_1q(Gates.H, 0)
dm.apply_kraus_1q(depolarizing(${P}), 0, label="depol(${P})")
b = bloch_vector(dm, qubit=0)
print(f"  |+> after depolarizing(p=${P}):")
print(f"  purity Tr(ρ²) = {dm.purity():.4f}")
print()
print(ascii_bloch_axes(b))
PY
    ;;
  *) echo "usage: bell-decay | chsh-noise | bloch <p>"; exit 1;;
esac
