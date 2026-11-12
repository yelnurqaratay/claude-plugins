#!/usr/bin/env python3
"""PreToolUse hook: ask the user before git commands that publish or rewrite history.

Splits a Bash command into git invocations (handling `-C`/`-c`, `&&`, `;`, `|`,
newlines and `sh -c "..."`) and answers "ask" with a reason for every risky one.
Claude Code then shows its own confirmation prompt; the user decides per command.
"""
import json
import re
import shlex
import sys
from pathlib import Path

SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", "|&", ";;"}
GIT_VALUE_OPTIONS = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}
# Commands that run their arguments as another command (`rtk git push`, `env X=1 git push`).
WRAPPERS = {"command", "exec", "nohup", "time", "sudo", "env", "rtk", "caffeinate", "nice", "timeout"}


def emit_ask(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": reason,
    }}, ensure_ascii=False))


def tokenize(text: str) -> list:
    lex = shlex.shlex(text, posix=True, punctuation_chars=";&|()")
    lex.whitespace_split = True
    return list(lex)


def segments(command: str) -> list:
    """Token lists, one per simple command; nested `sh -c` scripts are expanded."""
    try:
        toks = tokenize(command.replace("\n", " ; "))
    except ValueError:
        try:
            toks = tokenize(command)
        except ValueError:
            toks = command.split()
    out, cur = [], []
    for tok in toks:
        if tok in SEPARATORS:
            if cur:
                out.append(cur)
            cur = []
        else:
            cur.append(tok)
    if cur:
        out.append(cur)
    nested = []
    for seg in out:
        for i, tok in enumerate(seg[:-1]):
            if Path(tok).name in ("sh", "bash", "zsh") and "-c" in seg[i + 1:i + 3]:
                k = seg.index("-c", i + 1)
                if k + 1 < len(seg):
                    nested += segments(seg[k + 1])
    return out + nested


def git_call(seg: list):
    """(subcommand, args) if the segment runs git, else None. Env assignments are skipped."""
    i = 0
    while i < len(seg):
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", seg[i]):
            i += 1
        elif Path(seg[i]).name in WRAPPERS:
            i += 1
            # the wrapper's own options and values: `env -i`, `timeout 30`, `nice -n 5`
            while i < len(seg) and (seg[i].startswith("-") or re.match(r"^\d+[smhd]?$", seg[i])):
                i += 1
        else:
            break
    if i >= len(seg) or Path(seg[i]).name != "git":
        return None
    i += 1
    while i < len(seg) and seg[i].startswith("-"):
        opt = seg[i]
        i += 2 if opt in GIT_VALUE_OPTIONS else 1
    if i >= len(seg):
        return None
    return seg[i], seg[i + 1:]


def has(args: list, *flags) -> bool:
    for a in args:
        for f in flags:
            if a == f or (f.startswith("--") and a.startswith(f + "=")):
                return True
    return False


def short_flag(args: list, letter: str) -> bool:
    """True for -f, but also combined short flags like -fd."""
    return any(re.match(r"^-[A-Za-z]+$", a) and letter in a[1:] for a in args)


def risks(sub: str, args: list) -> list:
    found = []
    if sub == "push":
        if has(args, "--force", "--force-with-lease", "--force-if-includes") or short_flag(args, "f") \
                or any(a.startswith("+") for a in args):
            found.append("FORCE push: rewrites the remote branch")
        if has(args, "--delete", "-d") or any(re.match(r"^:[^/]", a) for a in args):
            found.append("deletes a remote branch or tag")
        if has(args, "--mirror", "--all", "--tags"):
            found.append("pushes more than the current branch (--mirror/--all/--tags)")
        if not found:
            found.append("push to a remote")
    elif sub == "commit" and has(args, "--amend"):
        found.append("amend: rewrites the last commit")
    elif sub == "rebase" and not has(args, "--abort", "--quit", "--show-current-patch", "--edit-todo"):
        found.append("rebase: rewrites history")
    elif sub == "reset" and has(args, "--hard", "--merge", "--keep"):
        found.append("reset --hard: discards local changes")
    elif sub == "clean" and (has(args, "--force") or short_flag(args, "f")):
        found.append("clean -f: deletes untracked files")
    elif sub in ("checkout", "switch") and (has(args, "--force", "--discard-changes") or short_flag(args, "f")):
        found.append(f"{sub} --force: discards local changes")
    elif sub == "branch" and (has(args, "-D") or (has(args, "--delete", "-d") and has(args, "--force", "-f"))):
        found.append("force-deletes a local branch")
    elif sub == "stash" and args[:1] in (["drop"], ["clear"]):
        found.append(f"stash {args[0]}: deletes stashed changes")
    elif sub in ("filter-branch", "filter-repo"):
        found.append(f"{sub}: rewrites history")
    elif sub == "reflog" and args[:1] == ["expire"]:
        found.append("reflog expire: drops recovery points")
    elif sub == "gc" and has(args, "--prune"):
        found.append("gc --prune: deletes unreachable commits for good")
    elif sub == "update-ref" and has(args, "-d"):
        found.append("update-ref -d: deletes a ref")
    return found


def main() -> int:
    event = json.load(sys.stdin)
    if event.get("tool_name") != "Bash":
        return 0
    command = (event.get("tool_input") or {}).get("command", "")
    if "git" not in command:
        return 0
    found = []
    for seg in segments(command):
        call = git_call(seg)
        if call:
            sub, args = call
            for risk in risks(sub, args):
                found.append(f"`git {sub}`: {risk}")
    if found:
        emit_ask("git-guard — needs your confirmation:\n- " + "\n- ".join(dict.fromkeys(found)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never break the session on a hook bug
        print(f"git-guard: hook error, check skipped: {exc}", file=sys.stderr)
        sys.exit(0)
