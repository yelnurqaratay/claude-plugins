# token-hygiene

Keeps API tokens out of the Claude Code transcript.

## Hooks

- **`UserPromptSubmit`** — a message that contains a token (GitLab, GitHub, Anthropic,
  OpenAI-style, AWS, Slack, Google, JWT, private keys) is blocked before the model sees
  it, with instructions to store the token in the Keychain instead.
- **`PreToolUse` (Bash)** — denies a command that
  - contains a literal token or a literal `Authorization` / `PRIVATE-TOKEN` header value,
  - prints a Keychain secret (`security find-generic-password … -w` outside `$(...)`),
  - echoes or `printenv`s a variable named like `*TOKEN*`, `*SECRET*`, `*PASSWORD*`,
    `*API_KEY*`, `*PAT*`;

  and asks before `env` / `printenv` dump the whole environment.

## `/token-hygiene:token`

Tokens are stored as generic passwords `claude-token-<name>` in the macOS Keychain.

- `set <name>` — tells you the command to run in your own terminal; the value never
  enters the chat.
- `check <name>` — confirms the entry exists without reading it.
- `forget <name>` — how to delete it.
- `list` — the stored names.

Claude then reads a token only inside the command that needs it:

```bash
curl -sS -H @<(printf 'PRIVATE-TOKEN: %s' "$(security find-generic-password -s claude-token-gitlab -a "$USER" -w)") \
  "https://gitlab.example.com/api/v4/user"
```

Pattern matching cannot catch every secret format; treat this as a seatbelt, not a vault.
