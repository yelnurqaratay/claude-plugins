#!/usr/bin/env python3
"""PreToolUse hook: deny AI attribution in commits, tags, PRs/MRs and review comments.

Reads the hook event from stdin. For a Bash command that writes history or talks to
a forge (git commit/tag/notes/..., gh, glab, curl) it scans the command text and any
message file the command points at. For an MCP tool that creates or edits PRs, MRs,
issues or comments it scans the tool input. A match is denied with a reason, so the
model rewrites the text instead of publishing it.
"""
import json
import re
import shlex
import sys
from pathlib import Path

ATTRIBUTION = [
    (re.compile(r"co-authored-by:[^\n]*\b(claude|anthropic)\b", re.I), "Co-Authored-By trailer naming Claude"),
    (re.compile(r"generated\s+(with|by)\s+\[?claude", re.I), '"Generated with Claude" line'),
    (re.compile(r"noreply@anthropic\.com", re.I), "noreply@anthropic.com address"),
    (re.compile(r"claude\.(com|ai)/(claude-code|code)\b", re.I), "link to Claude Code"),
]

GIT_HISTORY = ("commit", "tag", "notes", "merge", "rebase", "cherry-pick", "revert", "am")
OUTWARD_TOOLS = ("gh", "glab", "curl", "http", "xh")
MCP_WRITE = re.compile(
    r"(create|update|edit|add|post|submit|reply|merge|push)[_-]?.*"
    r"(pull|merge|mr|issue|comment|review|note|discussion|thread|release|commit|file)", re.I)

# Options whose value is a file with the text that gets published.
FILE_OPTIONS = {"-F", "--file", "--body-file", "--message-file", "--description-file"}


def emit_deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason,
    }}, ensure_ascii=False))


def find_attribution(text: str) -> list:
    return [label for rx, label in ATTRIBUTION if rx.search(text)]


def tokens(command: str) -> list:
    try:
        lex = shlex.shlex(command, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        return command.split()


def is_outward(toks: list) -> bool:
    for i, tok in enumerate(toks):
        name = Path(tok).name
        if name in OUTWARD_TOOLS:
            return True
        if name == "git":
            j = i + 1
            while j < len(toks) and toks[j].startswith("-"):
                j += 2 if toks[j] in ("-C", "-c") else 1
            if j < len(toks) and toks[j] in GIT_HISTORY:
                return True
    return False


def message_files(toks: list, cwd: Path) -> list:
    files = []
    for i, tok in enumerate(toks):
        value = None
        if tok in FILE_OPTIONS and i + 1 < len(toks):
            value = toks[i + 1]
        elif "=" in tok and tok.split("=", 1)[0] in FILE_OPTIONS:
            value = tok.split("=", 1)[1]
        elif tok.startswith("@") and len(tok) > 1 and i > 0 and toks[i - 1].startswith(("-d", "--data")):
            value = tok[1:]
        elif tok.startswith(("--data=@", "--data-binary=@", "--data-raw=@")):
            value = tok.split("=@", 1)[1]
        if value and value != "-":
            path = Path(value).expanduser()
            files.append(path if path.is_absolute() else cwd / path)
    return files


def check_bash(command: str, cwd: Path) -> list:
    toks = tokens(command)
    if not is_outward(toks):
        return []
    found = find_attribution(command)
    for path in message_files(toks, cwd):
        try:
            found += find_attribution(path.read_text(errors="replace"))
        except OSError:
            pass
    return found


def main() -> int:
    event = json.load(sys.stdin)
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    cwd = Path(event.get("cwd") or ".")

    if tool == "Bash":
        found = check_bash(tool_input.get("command", ""), cwd)
    elif tool.startswith("mcp__") and MCP_WRITE.search(tool):
        found = find_attribution(json.dumps(tool_input, ensure_ascii=False))
    else:
        return 0

    if found:
        emit_deny(
            "AI attribution is not allowed in commits, PRs/MRs or comments. Found: "
            + ", ".join(dict.fromkeys(found))
            + ". Remove those lines and run the command again; do not add any other "
              "mention of Claude or Anthropic as an author.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never break the session on a hook bug
        print(f"no-ai-attribution: hook error, check skipped: {exc}", file=sys.stderr)
        sys.exit(0)
