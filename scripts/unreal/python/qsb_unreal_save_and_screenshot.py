"""UE Python — save current level + take HighResShot. Run via -ExecutePythonScript=."""
import unreal
import os
import time

ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
out_dir = "/vaults/nvme0/qsb_tower_v1/data/screenshots/unreal_cli_driver"
os.makedirs(out_dir, exist_ok=True)
shot = f"{out_dir}/uepy_{ts}.png"

ues = unreal.EditorLevelLibrary  # 5.8 namespace
try:
    ues.save_current_level()
    unreal.log(f"qsb: level saved")
except Exception as e:
    unreal.log(f"qsb: save failed: {e}")

try:
    unreal.SystemLibrary.execute_console_command(None, f"HighResShot 1920x1080 filename={shot}")
    unreal.log(f"qsb: HighResShot queued → {shot}")
except Exception as e:
    unreal.log(f"qsb: screenshot failed: {e}")
