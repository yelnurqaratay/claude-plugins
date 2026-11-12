import unittest

from hookrun import bash_event, decision, run_hook

# Fake tokens are assembled at runtime so the repo itself never contains a string
# that secret scanners (or this plugin) would flag.
FAKE = {
    "gitlab": "gl" + "pat-" + "x1Y2z3" * 4,
    "github": "gh" + "p_" + "A1b2C3" * 7,
    "github_fine": "github" + "_pat_" + "a1B2_c3D4" * 6,
    "anthropic": "sk" + "-ant-" + "api03" + "Zz9" * 10,
    "aws": "AK" + "IA" + "ABCDEFGHIJKLMNOP",
    "slack": "xo" + "xb-" + "1234567890-abcdef",
    "jwt": "ey" + "J" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0" + "." + "abcdefghijklmnop",
}


def scan(event):
    return run_hook("token-hygiene", "scan_secrets.py", event)


def prompt(text):
    return scan({"hook_event_name": "UserPromptSubmit", "prompt": text})


def bash(command):
    event = bash_event(command)
    event["hook_event_name"] = "PreToolUse"
    return scan(event)


class PromptTest(unittest.TestCase):
    def test_tokens_in_prompt_are_blocked(self):
        for kind, token in FAKE.items():
            with self.subTest(kind=kind):
                data = prompt(f"вот мой токен {token}, используй его")["json"]
                self.assertEqual(data["decision"], "block")
                self.assertIn("claude-token-", data["reason"])

    def test_private_key_in_prompt_is_blocked(self):
        key = "-----BEGIN " + "OPENSSH PRIVATE KEY-----\nabc\n"
        self.assertEqual(prompt(key)["json"]["decision"], "block")

    def test_ordinary_prompt_passes(self):
        for text in ("сделай ревью MR !22", "почему падает sk-learn импорт?",
                     "ключ ABC-123 возьми в работу", "use the claude-token-gitlab entry"):
            with self.subTest(text=text):
                self.assertIsNone(prompt(text)["json"])


class CommandTest(unittest.TestCase):
    def test_literal_token_in_command_is_denied(self):
        for kind, token in FAKE.items():
            with self.subTest(kind=kind):
                self.assertEqual(decision(bash(f"curl -H 'X: {token}' https://x")), "deny")

    def test_literal_header_value_is_denied(self):
        self.assertEqual(decision(bash(
            'curl -H "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123" https://jira')), "deny")
        self.assertEqual(decision(bash(
            'curl -H "PRIVATE-TOKEN: abcdefghijklmnopqrstuv" https://gitlab')), "deny")

    def test_header_from_variable_or_keychain_passes(self):
        for cmd in ('curl -H "PRIVATE-TOKEN: $GITLAB_TOKEN" https://gitlab',
                    'curl -H "Authorization: Bearer ${JIRA_PAT}" https://jira',
                    "curl -H @<(printf 'PRIVATE-TOKEN: %s' \"$(security find-generic-password "
                    "-s claude-token-gitlab -a \"$USER\" -w)\") https://gitlab",
                    'T="$(security find-generic-password -s claude-token-jira -a "$USER" -w)" && curl -s x',
                    'curl -H "Authorization: Bearer <token>" https://example'):
            with self.subTest(cmd=cmd):
                self.assertIsNone(bash(cmd)["json"])

    def test_printing_keychain_secret_is_denied(self):
        for cmd in ('security find-generic-password -s claude-token-gitlab -a "$USER" -w',
                    "security find-generic-password -w -s x | pbcopy"):
            with self.subTest(cmd=cmd):
                self.assertEqual(decision(bash(cmd)), "deny")

    def test_checking_keychain_entry_without_value_passes(self):
        cmd = 'security find-generic-password -s claude-token-gitlab -a "$USER" >/dev/null && echo stored'
        self.assertIsNone(bash(cmd)["json"])

    def test_printing_secret_variables_is_denied(self):
        for cmd in ('echo "$GITLAB_TOKEN"', "echo $JIRA_PAT", 'printf "%s" "${API_KEY}"',
                    "printenv OPENAI_API_KEY", 'cd x && echo "token: $MY_SECRET"'):
            with self.subTest(cmd=cmd):
                self.assertEqual(decision(bash(cmd)), "deny")

    def test_checking_variable_without_value_passes(self):
        for cmd in ('[ -n "$GITLAB_TOKEN" ] && echo set', 'echo "$HOME"', "echo done"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(bash(cmd)["json"])

    def test_dumping_environment_asks(self):
        for cmd in ("env", "printenv", "cd x && env"):
            with self.subTest(cmd=cmd):
                self.assertEqual(decision(bash(cmd)), "ask")
        self.assertIsNone(bash("env FOO=1 make")["json"])

    def test_other_tools_and_broken_input_are_ignored(self):
        self.assertIsNone(scan({"hook_event_name": "PreToolUse", "tool_name": "Read",
                                "tool_input": {"file_path": FAKE["gitlab"]}})["json"])
        self.assertEqual(scan({})["code"], 0)


if __name__ == "__main__":
    unittest.main()
