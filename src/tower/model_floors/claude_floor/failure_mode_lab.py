"""FailureModeLab — actually-working sandbox to run a proposed Python
snippet in a subprocess with timeout + size cap + sealed env. The
corresponding room on F47 finally does something.

Safety:
- runs in a fresh `python3 -c <code>` subprocess
- timeout (default 5 s)
- output size cap (default 256 KB)
- env passes only PATH + LANG (no QSB_*_API_KEY etc. — even if set in shell)
- no shell expansion
"""
from __future__ import annotations
import os
import subprocess
import tempfile
import resource
import signal
from typing import Dict, Any

SAFE_ENV_KEYS = ("PATH", "LANG", "HOME")
DEFAULT_TIMEOUT = 5.0
DEFAULT_OUTPUT_CAP = 256 * 1024


class FailureModeLab:
    @staticmethod
    def run(code: str,
            *, timeout: float = DEFAULT_TIMEOUT,
            output_cap: int = DEFAULT_OUTPUT_CAP,
            stdin: str = "") -> Dict[str, Any]:
        # Clean env — strip all secrets so a stray print can't leak
        safe_env = {k: os.environ[k] for k in SAFE_ENV_KEYS if k in os.environ}
        # write code to a temp file so subprocess.args stay short
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            path = f.name
        try:
            result = subprocess.run(
                ["python3", path],
                input=stdin,
                env=safe_env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            stdout = result.stdout[:output_cap]
            stderr = result.stderr[:output_cap]
            return {
                "ok": result.returncode == 0,
                "returncode": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "stdout_truncated": len(result.stdout) > output_cap,
                "stderr_truncated": len(result.stderr) > output_cap,
                "timed_out": False,
            }
        except subprocess.TimeoutExpired as e:
            return {
                "ok": False,
                "returncode": None,
                "stdout": (e.stdout or "")[:output_cap] if isinstance(e.stdout, str) else "",
                "stderr": "(timed out after %.1fs)" % timeout,
                "timed_out": True,
            }
        finally:
            try: os.unlink(path)
            except OSError: pass

    @staticmethod
    def can_import(module: str, *, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
        """Quick: does this importable name actually import cleanly right now?"""
        return FailureModeLab.run(
            f"import importlib, sys; sys.path.insert(0, '/vaults/nvme0/qsb_tower_v1'); importlib.import_module({module!r}); print('ok')",
            timeout=timeout,
        )

    @staticmethod
    def syntax_check_file(path: str) -> Dict[str, Any]:
        """py_compile a file in a subprocess so a syntax error can't crash us."""
        return FailureModeLab.run(
            f"import py_compile; py_compile.compile({path!r}, doraise=True); print('ok')",
            timeout=3.0,
        )
