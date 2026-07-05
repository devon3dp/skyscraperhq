#!/usr/bin/env bash
set -Eeuo pipefail

QSB_ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
PROJECT="/home/ross/qsb_godot_native_cockpit"
REG_DIR="$QSB_ROOT/data/registries"
LOG_DIR="$QSB_ROOT/data/logs"
mkdir -p "$REG_DIR" "$LOG_DIR"

pass=0
fail=0

check_file(){
  if [ -f "$2" ]; then echo "PASS: $1 -> $2"; pass=$((pass+1)); else echo "FAIL: $1 -> $2"; fail=$((fail+1)); fi
}

echo "== QSB GODOT LAUNCH CHECK =="
check_file "project.godot" "$PROJECT/project.godot"
check_file "Main.tscn" "$PROJECT/scenes/Main.tscn"
check_file "Main.gd" "$PROJECT/scripts/Main.gd"
grep -q 'run/main_scene="res://scenes/Main.tscn"' "$PROJECT/project.godot" && { echo "PASS: main scene configured"; pass=$((pass+1)); } || { echo "FAIL: main scene not configured"; fail=$((fail+1)); }

if "$QSB_ROOT/native_cockpit/bin/qsb-godot" --version >/tmp/qsb_godot_launch_version.txt 2>&1; then
  echo "PASS: Godot wrapper works: $(cat /tmp/qsb_godot_launch_version.txt | head -1)"
  pass=$((pass+1))
else
  echo "FAIL: Godot wrapper failed"
  fail=$((fail+1))
fi

cat > "$REG_DIR/qsb_godot_launch_check.json" <<JSON
{
  "project": "$PROJECT",
  "passes": $pass,
  "failures": $fail,
  "main_scene": "$PROJECT/scenes/Main.tscn",
  "run_command": "./scripts/qsb_godot_run.sh"
}
JSON

cat "$REG_DIR/qsb_godot_launch_check.json"
exit "$fail"
