from pathlib import Path
import py_compile
import ast
import os

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SERVER = ROOT / "src/dashboard/server.py"

print("============================================================")
print(" QSB TOWER — FLOOR 38 DASHBOARD SYNTAX REPAIR")
print(" Fixes literal \\n dashboard patch issue")
print("============================================================")

if not SERVER.exists():
    raise SystemExit(f"Missing dashboard server: {SERVER}")

current = SERVER.read_text(encoding="utf-8")
repair_backup = SERVER.with_suffix(".py.backup_broken_floor38_literal_newline")
repair_backup.write_text(current, encoding="utf-8")
print(f"Backed up current server.py to: {repair_backup}")

def can_parse(text):
    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False

def compile_server():
    py_compile.compile(str(SERVER), doraise=True)

# ------------------------------------------------------------
# 1. First repair the literal backslash-n insertions.
# ------------------------------------------------------------
text = current

literal_fixes = {
    'safe_dashboard("tower.simulation_labs", "SimulationLabs"),\\n        "sandbox_operations"':
    'safe_dashboard("tower.simulation_labs", "SimulationLabs"),\n        "sandbox_operations"',

    '("tower.simulation_labs", "SimulationLabs"),\\n            "/api/sandbox_operations"':
    '("tower.simulation_labs", "SimulationLabs"),\n            "/api/sandbox_operations"',

    '"floor_37": "simulation_labs",\\n    "floor_38"':
    '"floor_37": "simulation_labs",\n    "floor_38"',

    'const simLabs = data.simulation_labs || {};\\n  const sandboxOps':
    'const simLabs = data.simulation_labs || {};\n  const sandboxOps',
}

for bad, good in literal_fixes.items():
    text = text.replace(bad, good)

# ------------------------------------------------------------
# 2. If still broken, restore clean pre-Floor38 dashboard backup.
# ------------------------------------------------------------
if not can_parse(text):
    print("Literal repair was not enough. Searching for clean dashboard backup...")
    backups = [
        ROOT / "src/dashboard/server.py.backup_before_floor38_retry",
        ROOT / "src/dashboard/server.py.backup_before_floor38_v11",
        ROOT / "src/dashboard/server.py.backup_before_floor37_v11",
        ROOT / "src/dashboard/server.py.backup_before_floor26_v11",
        ROOT / "src/dashboard/server.py.backup_before_floor25_v11",
    ]

    restored = False
    for b in backups:
        if b.exists():
            candidate = b.read_text(encoding="utf-8")
            if can_parse(candidate):
                text = candidate
                restored = True
                print(f"Restored clean base from: {b}")
                break

    if not restored:
        SERVER.write_text(text, encoding="utf-8")
        compile_server()
        raise SystemExit("No clean backup found, but server.py still has syntax problems.")

# ------------------------------------------------------------
# 3. Patch Floor 38 into dashboard safely with real newlines.
# ------------------------------------------------------------
def ensure_line_after(source, marker, line):
    if line in source:
        return source

    idx = source.find(marker)
    if idx < 0:
        print(f"Marker not found, skipped: {marker}")
        return source

    line_start = source.rfind("\n", 0, idx) + 1
    line_end = source.find("\n", idx)
    if line_end < 0:
        line_end = len(source)

    marker_line = source[line_start:line_end]
    if not marker_line.rstrip().endswith(","):
        marker_line = marker_line.rstrip() + ","

    return source[:line_start] + marker_line + "\n" + line + source[line_end:]

text = ensure_line_after(
    text,
    '"simulation_labs": safe_dashboard("tower.simulation_labs", "SimulationLabs")',
    '        "sandbox_operations": safe_dashboard("tower.sandbox_operations", "SandboxOperations")'
)

text = ensure_line_after(
    text,
    '"/api/simulation_labs": ("tower.simulation_labs", "SimulationLabs")',
    '            "/api/sandbox_operations": ("tower.sandbox_operations", "SandboxOperations")'
)

text = ensure_line_after(
    text,
    '"floor_37": "simulation_labs",',
    '    "floor_38": "sandbox_operations",'
)

text = ensure_line_after(
    text,
    "const simLabs = data.simulation_labs || {};",
    "  const sandboxOps = data.sandbox_operations || {};"
)

# ------------------------------------------------------------
# 4. Add Floor 38 panel if missing.
# ------------------------------------------------------------
panel = '''
    <div class="panel">
      <h2>Floor 38 Sandbox Operations <span class="badge good">contained</span></h2>
      <div class="panel-grid" id="sandboxGrid"></div>
    </div>
'''

if 'id="sandboxGrid"' not in text:
    marker = '''    <div class="panel">
      <h2>Lift Network <span class="badge blue">click lift</span></h2>'''
    if marker in text:
        text = text.replace(marker, panel + "\n" + marker)
        print("Inserted Floor 38 Sandbox panel.")
    else:
        print("Lift Network marker not found; panel insertion skipped.")

# ------------------------------------------------------------
# 5. Add Floor 38 render grid if missing.
# ------------------------------------------------------------
render = '''
  renderGrid("sandboxGrid", [
    ["Status", safe(sandboxOps.status), sandboxOps.status === "healthy" ? "good" : "warn"],
    ["Envelopes", safe(sandboxOps.envelope_count), "blue"],
    ["Contained", safe(sandboxOps.contained_envelopes), "good"],
    ["Rejected", safe(sandboxOps.rejected_envelopes), sandboxOps.rejected_envelopes ? "bad" : "good"],
    ["Network", yesNo(sandboxOps.network_enabled), sandboxOps.network_enabled ? "bad" : "good"],
    ["Mode", sandboxOps.dry_run_only ? "sealed_metadata" : "unknown", "blue"]
  ]);
'''

if 'renderGrid("sandboxGrid"' not in text:
    idx = text.find('renderGrid("simulationGrid"')
    if idx >= 0:
        end = text.find("  ]);", idx)
        if end >= 0:
            end += len("  ]);")
            text = text[:end] + "\n\n" + render + text[end:]
            print("Inserted Floor 38 Sandbox render grid.")
        else:
            print("Could not find end of simulationGrid render block.")
    else:
        print("simulationGrid render block not found; render insertion skipped.")

# ------------------------------------------------------------
# 6. Final write and compile.
# ------------------------------------------------------------
SERVER.write_text(text, encoding="utf-8")
compile_server()

print("server.py compiles cleanly.")
print("Floor 38 dashboard repair complete.")
