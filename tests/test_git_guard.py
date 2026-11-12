import unittest

from hookrun import bash_event, decision, run_hook


def guard(command):
    return run_hook("git-guard", "guard.py", bash_event(command))


def reason(result):
    return result["json"]["hookSpecificOutput"]["permissionDecisionReason"]


class AskTest(unittest.TestCase):
    CASES = {
        "git push": "push to a remote",
        "git push origin feature/x": "push to a remote",
        "git push -f origin x": "FORCE",
        "git push --force-with-lease": "FORCE",
        "git push origin +main": "FORCE",
        "git push origin --delete old": "deletes a remote",
        "git push origin :old": "deletes a remote",
        "git commit --amend --no-edit": "amend",
        "git rebase -i HEAD~3": "rebase",
        "git reset --hard origin/main": "reset --hard",
        "git clean -fd": "clean -f",
        "git checkout -f main": "checkout --force",
        "git branch -D topic": "force-deletes",
        "git stash drop": "stash drop",
        "git filter-repo --path x --invert-paths": "filter-repo",
        "git reflog expire --expire=now --all": "reflog expire",
        "git gc --prune=now": "gc --prune",
    }

    def test_risky_commands_ask(self):
        for cmd, expected in self.CASES.items():
            with self.subTest(cmd=cmd):
                result = guard(cmd)
                self.assertEqual(decision(result), "ask")
                self.assertIn(expected, reason(result))

    def test_global_options_and_chains(self):
        for cmd in ('git -C "/path with space/repo" push',
                    "git -c push.default=current push",
                    "git add . && git commit -m x && git push",
                    "git status; git push",
                    "git status\ngit push",
                    "GIT_SSH_COMMAND='ssh -i k' git push",
                    "bash -c 'cd repo && git push'",
                    "/usr/bin/git push",
                    "rtk git push origin main",
                    "env GIT_TRACE=1 git push",
                    "caffeinate git push --force",
                    "env -i git push",
                    "timeout 30 git push",
                    "nice -n 5 git push"):
            with self.subTest(cmd=cmd):
                self.assertEqual(decision(guard(cmd)), "ask")

    def test_every_risk_in_a_chain_is_listed(self):
        text = reason(guard("git commit --amend --no-edit && git push --force"))
        self.assertIn("amend", text)
        self.assertIn("FORCE", text)


class SilentTest(unittest.TestCase):
    def test_safe_commands_pass(self):
        for cmd in ("git status", "git log --oneline -5", "git diff HEAD~1",
                    'git commit -m "push the fix"', "git fetch origin",
                    "git pull --ff-only", "git rebase --abort", "git stash list",
                    "git reset --soft HEAD~1", "git branch -d merged",
                    'grep -rn "git push" docs/', "echo git push",
                    "git log --grep=push"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(guard(cmd)["json"])

    def test_non_bash_tools_are_ignored(self):
        event = {"tool_name": "Write", "tool_input": {"content": "git push --force"}}
        self.assertIsNone(run_hook("git-guard", "guard.py", event)["json"])

    def test_broken_input_never_blocks(self):
        self.assertEqual(run_hook("git-guard", "guard.py", {"tool_name": "Bash"})["code"], 0)


if __name__ == "__main__":
    unittest.main()
