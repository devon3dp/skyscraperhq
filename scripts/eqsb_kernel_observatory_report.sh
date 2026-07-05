#!/usr/bin/env bash
# EQSB Kernel Observatory Report — short human summary
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
python3 -c "
import json
hwf = json.load(open('data/registries/qsb_hardware_systems_floor.json'))
und = json.load(open('data/registries/eqsb_hardware_understanding.json'))
adv = json.load(open('data/registries/eqsb_performance_advice.json'))
code = json.load(open('data/registries/eqsb_code_observatory.json'))
graph = json.load(open('data/registries/eqsb_system_understanding_graph.json'))
ledger = json.load(open('data/registries/eqsb_claude_upgrade_ledger.json'))
s = und.get('summary') or {}
print('EQSB Kernel Observatory Report')
print('================================')
print('Hardware Systems Floor: floor_%s' % hwf.get('floor_number'))
print('CPU:    %s' % s.get('cpu_model'))
print('GPU:    %s' % ', '.join(s.get('gpu_models') or []))
print('CUDA:   %s (python: %s)' % (s.get('cuda_version'), s.get('cuda_available_python')))
print('RAM:    %s bytes (pressure %s)' % (s.get('mem_total_bytes'), s.get('memory_pressure')))
print('Project storage: %s MiB' % s.get('qsb_project_mb'))
print('OS:     %s (kernel %s, python %s)' % (s.get('hostname'), s.get('kernel_release'), s.get('python_version')))
print('Dashboard PID running: %s · Ollama: %s · AirLLM venv: %s' %
      (s.get('dashboard_pid_running'), s.get('ollama_present'), s.get('airllm_venv_present')))
print('Code observatory: %s files' % code.get('total_files'))
print('System graph: %s nodes / %s edges' % (graph.get('node_count'), graph.get('edge_count')))
print('Claude upgrade ledger phase_count: %s' % ledger.get('phase_count'))
print('Latest phase: %s' % ledger.get('latest_phase'))
print()
print('Performance advice:')
for a in adv.get('advice') or []:
    print(' -', a)
"
