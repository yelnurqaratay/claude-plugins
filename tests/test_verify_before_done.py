import json
import tempfile
import unittest
from pathlib import Path

from hookrun import run_hook


def user(text):
    return {"type": "user", "message": {"role": "user", "content": text}}


def tool_result():
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}}


def edit(path, tool="Edit"):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t", "name": tool, "input": {"file_path": path}}]}}


def bash(command):
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": command}}]}}


class StopHookTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.cwd = Path(self.dir.name)

    def stop(self, entries, active=False):
        transcript = self.cwd / "t.jsonl"
        transcript.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        event = {"hook_event_name": "Stop", "transcript_path": str(transcript),
                 "cwd": str(self.cwd), "stop_hook_active": active}
        return run_hook("verify-before-done", "check_verified.py", event)

    def blocked(self, entries, **kw):
        data = self.stop(entries, **kw)["json"]
        return bool(data) and data.get("decision") == "block"

    def test_edit_without_verification_is_blocked(self):
        result = self.stop([user("fix it"), edit("/r/app/src/Foo.kt"), tool_result()])
        self.assertEqual(result["json"]["decision"], "block")
        self.assertIn("Foo.kt", result["json"]["reason"])

    def test_edit_then_tests_passes(self):
        for cmd in ("./gradlew :feature:auth:testDebugUnitTest", "cd app && ./gradlew compileDebugKotlin",
                    "python3 -m unittest discover -s tests", "npm test", "pnpm run build",
                    "xcodebuild test -scheme App", "go test ./...", "cargo check", "pytest -q",
                    "bash -n script.sh"):
            with self.subTest(cmd=cmd):
                self.assertFalse(self.blocked([user("fix"), edit("/r/a.kt"), tool_result(), bash(cmd)]))

    def test_edit_after_the_last_test_run_is_blocked(self):
        self.assertTrue(self.blocked([user("fix"), edit("/r/a.kt"), bash("./gradlew test"),
                                      tool_result(), edit("/r/b.kt"), tool_result()]))

    def test_second_stop_is_always_released(self):
        self.assertFalse(self.blocked([user("fix"), edit("/r/a.kt")], active=True))

    def test_non_code_edits_do_not_count(self):
        for path in ("/r/README.md", "/r/notes.txt", "/r/config.json", "/r/CHANGELOG.md"):
            with self.subTest(path=path):
                self.assertFalse(self.blocked([user("docs"), edit(path)]))

    def test_only_the_current_turn_counts(self):
        # The edit belongs to an earlier turn; this turn only answered a question.
        self.assertFalse(self.blocked([user("fix"), edit("/r/a.kt"), tool_result(),
                                       user("what did you change?")]))

    def test_tool_results_are_not_prompts(self):
        self.assertTrue(self.blocked([user("fix"), bash("./gradlew test"), tool_result(),
                                      edit("/r/a.kt"), tool_result()]))

    def test_write_tool_counts_as_edit(self):
        self.assertTrue(self.blocked([user("add"), edit("/r/New.swift", tool="Write")]))

    def test_project_config(self):
        (self.cwd / ".claude").mkdir()
        cfg = self.cwd / ".claude" / "verify-before-done.json"
        cfg.write_text('{"enabled": false}')
        self.assertFalse(self.blocked([user("fix"), edit("/r/a.kt")]))
        cfg.write_text('{"verify_patterns": ["^\\\\./ci/check"]}')
        self.assertFalse(self.blocked([user("fix"), edit("/r/a.kt"), bash("./ci/check all")]))
        cfg.write_text('{"code_extensions": [".proto"]}')
        self.assertTrue(self.blocked([user("fix"), edit("/r/api.proto")]))

    def test_missing_transcript_and_broken_input_never_block(self):
        event = {"hook_event_name": "Stop", "transcript_path": "/nonexistent.jsonl", "cwd": "/"}
        self.assertIsNone(run_hook("verify-before-done", "check_verified.py", event)["json"])
        self.assertEqual(run_hook("verify-before-done", "check_verified.py", {})["code"], 0)


if __name__ == "__main__":
    unittest.main()
