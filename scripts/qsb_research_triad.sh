#!/usr/bin/env bash
# qsb_research_triad.sh — F37 Quantum Triad Sandbox CLI.
# Usage:
#   qsb_research_triad.sh bell [shots]    # Bell pair (entanglement)
#   qsb_research_triad.sh ghz  [shots]    # 3-qubit GHZ
#   qsb_research_triad.sh coin [shots]    # quantum vs classical coin
#   qsb_research_triad.sh custom <n_qubits> "H 0" "CNOT 0 1" ...
#   qsb_research_triad.sh log [N]         # last N experiments from the registry
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CMD="${1:-bell}"

case "${CMD}" in
  bell|ghz|coin)
    SHOTS="${2:-1024}"
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.research_floor.quantum_triad_sandbox import triad_ask, probability_bars
r = triad_ask("${CMD}", shots=${SHOTS})
print(json.dumps(r, indent=2, default=str))
print()
print("=== probability bars ===")
print(probability_bars(r["lanes"]["quantum"]["probabilities"]))
PY
    ;;
  chsh)
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.research_floor.quantum_triad_sandbox import chsh_test
r = chsh_test()
print(json.dumps(r, indent=2, default=str))
PY
    ;;
  grover)
    NQ="${2:-3}"; T="${3:-5}"; SH="${4:-2000}"
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.research_floor.quantum_triad_sandbox import grover_search, probability_bars, QuantumLane, Gates
r = grover_search(n_qubits=${NQ}, target=${T}, shots=${SH})
print(json.dumps(r, indent=2, default=str))
# rebuild final state to show bars properly
q = QuantumLane(${NQ})
for i in range(${NQ}): q.apply(Gates.H, i)
import math
N = 2 ** ${NQ}
iters = max(1, round((math.pi / 4) * math.sqrt(N)))
for _ in range(iters):
    q.state[${T}] = -q.state[${T}]
    for i in range(${NQ}): q.apply(Gates.H, i)
    for i in range(N):
        if i != 0: q.state[i] = -q.state[i]
    for i in range(${NQ}): q.apply(Gates.H, i)
print()
print("=== probability bars (after Grover) ===")
print(probability_bars(q.probabilities(), width=50, threshold=0.005))
PY
    ;;
  custom)
    NQ="${2:?n_qubits}"
    shift 2
    python3 - <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.research_floor.quantum_triad_sandbox import TriadQuery
gates = [${@@Q}] if False else sys.argv[1:]   # placeholder; bash passes via args
PY
    # Actually: use a smarter Python invocation
    python3 - "$@" <<PY
import sys, json; sys.path.insert(0, "${ROOT}")
from src.tower.research_floor.quantum_triad_sandbox import TriadQuery
gates = sys.argv[1:]
r = TriadQuery.custom(n_qubits=${NQ}, gates=gates)
print(json.dumps(r, indent=2, default=str))
PY
    ;;
  log)
    N="${2:-5}"
    python3 - <<PY
import json
LOG = "/vaults/nvme0/qsb_tower_v1/data/registries/qsb_research_quantum_triad_log.jsonl"
try:
    lines = open(LOG).read().splitlines()
except FileNotFoundError:
    print("(no experiments yet)"); raise SystemExit(0)
for line in lines[-${N}:]:
    if not line.strip(): continue
    d = json.loads(line)
    print(f"--- {d['envelope']['ts']}  {d['question']}")
    for note in d.get("divergence_notes", []):
        print(f"  · {note}")
PY
    ;;
  *) echo "usage: bell|ghz|coin|custom|log"; exit 1;;
esac
