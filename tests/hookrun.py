"""Run a plugin hook script the way Claude Code does: event JSON on stdin."""
import json
import subprocess
import sys
from pathlib import Path

PLUGINS = Path(__file__).resolve().parents[1] / "plugins"


def run_hook(plugin: str, script: str, event: dict) -> dict:
    """Return {"code", "stdout", "stderr", "json"} for one hook invocation."""
    proc = subprocess.run(
        [sys.executable, "-I", str(PLUGINS / plugin / "hooks" / script)],
        input=json.dumps(event), capture_output=True, text=True, timeout=30)
    out = proc.stdout.strip()
    return {"code": proc.returncode, "stdout": out, "stderr": proc.stderr,
            "json": json.loads(out) if out else None}


def bash_event(command: str, cwd: str = ".") -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "Bash",
            "tool_input": {"command": command}, "cwd": cwd}


def decision(result: dict):
    """PreToolUse decision ("deny"/"ask"/...) or None when the hook stays silent."""
    data = result["json"] or {}
    return (data.get("hookSpecificOutput") or {}).get("permissionDecision")
