# claude-plugins

Guardrail hooks for [Claude Code](https://docs.claude.com/en/docs/claude-code): small
plugins that turn "please always…" rules from `CLAUDE.md` into checks the harness
enforces, whatever the model remembers.

| Plugin | Hook | What it does |
|---|---|---|
| [no-ai-attribution](plugins/no-ai-attribution) | `PreToolUse` | Denies `Co-Authored-By: Claude`, "Generated with Claude Code" and similar lines in commits, tags, PRs/MRs and review comments |
| [git-guard](plugins/git-guard) | `PreToolUse` | Asks you before `git push`, force-push, `commit --amend`, `rebase`, `reset --hard` and other history-rewriting or destructive commands |
| [token-hygiene](plugins/token-hygiene) | `UserPromptSubmit`, `PreToolUse` | Keeps tokens out of prompts, commands and output; `/token-hygiene:token` stores them in the macOS Keychain |
| [verify-before-done](plugins/verify-before-done) | `Stop` | If code changed and nothing was built or tested afterwards, sends Claude back once to verify |

## Install

```bash
/plugin marketplace add yelnurqaratay/claude-plugins
/plugin install no-ai-attribution@yelnurqaratay
/plugin install git-guard@yelnurqaratay
/plugin install token-hygiene@yelnurqaratay
/plugin install verify-before-done@yelnurqaratay
```

Restart Claude Code after installing so the hooks load.

## Requirements

- `python3` on `PATH` (the hooks use the standard library only).
- macOS for the Keychain part of token-hygiene; its prompt and command checks work anywhere.

## How the hooks behave

- Every hook fails open: if a hook itself crashes, it prints a warning and lets the
  action through rather than breaking the session.
- `deny` means Claude sees the reason and has to change the command; `ask` means
  Claude Code shows you its normal confirmation prompt; a blocked prompt is not sent
  to the model at all.
- In non-interactive runs (`claude -p`) an `ask` cannot be answered, so the command
  does not run.

## Development

```bash
python3 -m unittest discover -s tests
claude plugin validate .
```

The tests run each hook script exactly as Claude Code does: event JSON on stdin,
decision JSON on stdout.

## License

[MIT](LICENSE)
