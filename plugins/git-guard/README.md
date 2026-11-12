# git-guard

A `PreToolUse` hook that asks you before git commands that publish, rewrite or discard
history. Claude Code shows its normal confirmation prompt with the reason; you decide
per command.

| Command | Why it asks |
|---|---|
| `git push` | every push; force (`-f`, `--force-with-lease`, `+ref`), delete (`--delete`, `:ref`) and `--mirror/--all/--tags` are called out |
| `git commit --amend` | rewrites the last commit |
| `git rebase` (not `--abort`/`--quit`) | rewrites history |
| `git reset --hard/--merge/--keep` | discards local changes |
| `git clean -f`, `git checkout/switch --force` | deletes files / discards changes |
| `git branch -D`, `git stash drop/clear` | deletes a branch / stashed work |
| `git filter-branch`, `git filter-repo`, `git reflog expire`, `git gc --prune`, `git update-ref -d` | rewrites history or drops recovery points |

The command is parsed, not grepped: `git -C path push`, `a && git push`, multi-line
scripts, `sh -c '…'` and wrappers like `env`, `timeout`, `rtk` are all recognised, while
`git commit -m "push the fix"` or `grep "git push"` are left alone.

In a non-interactive run (`claude -p`) nobody can answer, so such commands do not run.
