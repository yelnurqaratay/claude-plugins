---
description: Store, check or remove an API token in the macOS Keychain without it ever entering the chat
argument-hint: "set|check|forget|list [name]"
allowed-tools: ["Bash(security find-generic-password:*)", "Bash(security dump-keychain:*)"]
---

# token

Tokens live in the macOS Keychain as generic passwords named `claude-token-<name>`,
account `$USER`. The value is **never** typed into this chat and never printed: Claude
reads it inside a command with `$(...)`, so it goes straight to the tool that needs it.

Arguments: `$ARGUMENTS` — `set <name>`, `check <name>`, `forget <name>` or `list`.
`<name>` is a short lowercase id such as `gitlab`, `jira`, `github`.

## set <name>

Do not ask the user for the value and do not run anything. Tell them to run this in
their own terminal app (it prompts for the token with hidden input):

```bash
security add-generic-password -U -s claude-token-<name> -a "$USER" -w
```

Then offer to run `check <name>`.

## check <name>

Confirm the entry exists without reading the value:

```bash
security find-generic-password -s claude-token-<name> -a "$USER" >/dev/null 2>&1 && echo "claude-token-<name>: stored" || echo "claude-token-<name>: missing"
```

## forget <name>

This deletes the entry. Ask the user to confirm first, then tell them to run in their
terminal:

```bash
security delete-generic-password -s claude-token-<name> -a "$USER"
```

## list

```bash
security dump-keychain 2>/dev/null | grep -o '"claude-token-[^"]*"' | sort -u
```

## Using a token in a command

Read it inside the command, never into a separate step:

```bash
curl -sS -H @<(printf 'PRIVATE-TOKEN: %s' "$(security find-generic-password -s claude-token-gitlab -a "$USER" -w)") \
  "https://gitlab.example.com/api/v4/user"
```

`-H @<(...)` hands the header to curl through a file descriptor, so the token is not
visible in the process list either. Never `echo` the token, never write it to a file in
the repo, never paste it into a commit, comment or log.
