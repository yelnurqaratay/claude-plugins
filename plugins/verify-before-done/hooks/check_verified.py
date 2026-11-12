#!/usr/bin/env python3
"""Stop hook: don't let a turn end with unverified code changes.

Reads the transcript of the current turn (everything after the last real user
prompt). If a source file was edited and no build/test/lint command ran after the
last edit, the stop is blocked once with a reason, so the model either verifies the
change or tells the user plainly what was not verified. The second stop of the same
turn (`stop_hook_active`) is always let through, so the hook can never loop.

Optional per-project config `.claude/verify-before-done.json`:
  {"enabled": false}                         turn the check off for this project
  {"verify_patterns": ["^\\./scripts/ci"]}   extra regexes that count as verification
  {"code_extensions": [".proto"]}            extra file extensions that count as code
"""
import json
import re
import sys
from pathlib import Path

CODE_EXTENSIONS = {
    ".kt", ".kts", ".java", ".scala", ".groovy", ".gradle", ".swift", ".m", ".mm", ".h",
    ".c", ".cc", ".cpp", ".hpp", ".rs", ".go", ".py", ".rb", ".php", ".cs", ".dart",
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte", ".sh", ".sql",
}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
VERIFY = re.compile(r"""(?x)
    (^|[\s;&|(/])(
        gradlew | gradle\s | mvnw? \s | xcodebuild | swift\s+(build|test) | tuist\s+(test|build)
      | (npm|pnpm|yarn|bun)\s+(run\s+)?(test|build|lint|typecheck|check) | npx\s+(jest|vitest|tsc|eslint)
      | jest | vitest | tsc\b | eslint
      | pytest | python3?\s+(-\S+\s+)*-m\s+(unittest|pytest|py_compile|mypy) | mypy | ruff\s+check
      | go\s+(test|build|vet) | cargo\s+(test|build|check|clippy) | dotnet\s+(build|test)
      | make(\s|$) | bats\s | bash\s+-n\s | shellcheck | detekt | ktlint | swiftlint
      | rspec | bundle\s+exec\s+(rspec|rake) | phpunit | flutter\s+(test|analyze)
    )""")


def load_config(cwd: Path) -> dict:
    path = cwd / ".claude" / "verify-before-done.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def is_real_prompt(entry: dict) -> bool:
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        kinds = {b.get("type") for b in content if isinstance(b, dict)}
        return "tool_result" not in kinds and bool(kinds & {"text", "image"})
    return False


def turn_tool_uses(transcript: Path) -> list:
    entries = []
    for line in transcript.read_text(errors="replace").splitlines():
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
    start = max((i for i, e in enumerate(entries) if is_real_prompt(e)), default=-1)
    uses = []
    for e in entries[start + 1:]:
        if e.get("type") != "assistant" or e.get("isSidechain"):
            continue
        for block in (e.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                uses.append(block)
    return uses


def main() -> int:
    event = json.load(sys.stdin)
    if event.get("stop_hook_active"):
        return 0
    cwd = Path(event.get("cwd") or ".")
    config = load_config(cwd)
    if config.get("enabled") is False:
        return 0
    transcript = Path(event.get("transcript_path") or "")
    if not transcript.is_file():
        return 0

    extensions = CODE_EXTENSIONS | {e.lower() for e in config.get("code_extensions", [])}
    extra = [re.compile(p) for p in config.get("verify_patterns", [])]

    edited, last_edit, last_verify = [], -1, -1
    for i, use in enumerate(turn_tool_uses(transcript)):
        name, tool_input = use.get("name"), use.get("input") or {}
        if name in EDIT_TOOLS:
            path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
            if Path(path).suffix.lower() in extensions:
                edited.append(path)
                last_edit = i
        elif name == "Bash":
            command = tool_input.get("command", "")
            if VERIFY.search(command) or any(p.search(command) for p in extra):
                last_verify = i

    if last_edit < 0 or last_verify > last_edit:
        return 0

    files = list(dict.fromkeys(edited))
    shown = ", ".join(Path(f).name for f in files[:5]) + (f" and {len(files) - 5} more" if len(files) > 5 else "")
    print(json.dumps({
        "decision": "block",
        "reason": f"verify-before-done: code was changed in this turn ({shown}), but no build, "
                  "test or lint command ran after the last edit. Build the affected module and run "
                  "the relevant tests now. If that is impossible here, say so to the user explicitly "
                  "and name what is left unverified instead of reporting the task as done.",
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never trap the session on a hook bug
        print(f"verify-before-done: hook error, check skipped: {exc}", file=sys.stderr)
        sys.exit(0)
