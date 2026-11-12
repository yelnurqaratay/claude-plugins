#!/usr/bin/env python3
"""Keep secrets out of the transcript.

UserPromptSubmit: a prompt that contains a token is blocked before the model sees it,
and the user is told how to store the token in the Keychain instead.

PreToolUse (Bash): a command is denied when it
  - carries a literal token (instead of reading it from the Keychain or a variable),
  - prints a Keychain secret (`security find-generic-password -w` outside `$(...)`),
  - echoes/prints a variable whose name says it holds a secret.
`env` / `printenv` without arguments dump every variable, so they need confirmation.
"""
import json
import re
import sys

TOKEN_PATTERNS = [
    (re.compile(r"\bglpat-[0-9A-Za-z_-]{20,}"), "GitLab personal access token"),
    (re.compile(r"\bgh[pousr]_[0-9A-Za-z]{36,}"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[0-9A-Za-z_]{40,}"), "GitHub fine-grained token"),
    (re.compile(r"\bsk-ant-[0-9A-Za-z_-]{20,}"), "Anthropic API key"),
    (re.compile(r"\bsk-(?:proj-)?[0-9A-Za-z_-]{32,}"), "OpenAI-style API key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}"), "Slack token"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "Google API key"),
    (re.compile(r"\beyJ[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}"), "JWT"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    # A header with a literal value. `$VAR`, `${VAR}`, `$(...)`, `<placeholder>` are fine.
    (re.compile(r"(?i)\b(?:private-token|authorization|x-api-key|api-key)\s*:\s*"
                r"(?:bearer\s+|basic\s+|token\s+)?(?![$<{])[0-9A-Za-z._~+/=-]{20,}"), "token in an HTTP header"),
]

SECRET_NAME = r"[A-Za-z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|PAT|CREDENTIALS?)[A-Za-z0-9_]*"
PRINT_SECRET_VAR = re.compile(
    r"(?:^|[;&|(\n]\s*)(?:echo|printf|print)\b[^;&|\n]*\$\{?" + SECRET_NAME + r"\b", re.I)
PRINTENV_SECRET = re.compile(r"(?:^|[;&|(\n]\s*)printenv\s+" + SECRET_NAME + r"\b", re.I)
DUMP_ENV = re.compile(r"(?:^|[;&|(\n]\s*)(?:env|printenv|export\s+-p|set)\s*(?:$|[;&|\n])")
KEYCHAIN_READ = re.compile(r"\bsecurity\s+find-(?:generic|internet)-password\b[^;&|\n]*\s-w\b")

KEYCHAIN_HINT = (
    "Store it in the Keychain from your own terminal (not in this chat): "
    "`security add-generic-password -U -s claude-token-<name> -a \"$USER\" -w` "
    "(it prompts for the value), then ask Claude to use the `claude-token-<name>` entry. "
    "See /token-hygiene:token for details.")


def find_tokens(text: str) -> list:
    return [label for rx, label in TOKEN_PATTERNS if rx.search(text)]


def prints_keychain_secret(command: str) -> bool:
    for m in KEYCHAIN_READ.finditer(command):
        before = command[:m.start()].rstrip(" \t\"'")
        if not (before.endswith("$(") or before.endswith("`")):
            return True
    return False


def emit(decision: str, reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}, ensure_ascii=False))


def on_prompt(event: dict) -> int:
    found = find_tokens(event.get("prompt", ""))
    if found:
        print(json.dumps({
            "decision": "block",
            "reason": "token-hygiene: your message looks like it contains a secret ("
                      + ", ".join(dict.fromkeys(found))
                      + ") and was not sent. If it is a real token, revoke it if it may have leaked. "
                      + KEYCHAIN_HINT,
        }, ensure_ascii=False))
    return 0


def on_bash(event: dict) -> int:
    command = (event.get("tool_input") or {}).get("command", "")
    found = find_tokens(command)
    if found:
        emit("deny", "The command contains a literal secret (" + ", ".join(dict.fromkeys(found))
             + "). Never put tokens into commands: read them from the Keychain inside the command, e.g. "
               "`curl -H @<(printf 'PRIVATE-TOKEN: %s' \"$(security find-generic-password "
               "-s claude-token-gitlab -a \"$USER\" -w)\") ...`. " + KEYCHAIN_HINT)
    elif prints_keychain_secret(command):
        emit("deny", "`security find-generic-password -w` prints the secret into the transcript. "
                     "Use it only inside `$(...)` so the value goes straight into the command.")
    elif PRINT_SECRET_VAR.search(command) or PRINTENV_SECRET.search(command):
        emit("deny", "The command prints a variable that holds a secret. Check it without "
                     "printing the value, e.g. `[ -n \"$GITLAB_TOKEN\" ] && echo set`.")
    elif DUMP_ENV.search(command):
        emit("ask", "This dumps all environment variables, which may include tokens.")
    return 0


def main() -> int:
    event = json.load(sys.stdin)
    name = event.get("hook_event_name")
    if name == "UserPromptSubmit":
        return on_prompt(event)
    if name == "PreToolUse" and event.get("tool_name") == "Bash":
        return on_bash(event)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never break the session on a hook bug
        print(f"token-hygiene: hook error, check skipped: {exc}", file=sys.stderr)
        sys.exit(0)
