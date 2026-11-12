# verify-before-done

A `Stop` hook. When Claude is about to end a turn, it reads the transcript of that turn:
if a source file was edited (`Edit`, `Write`, `MultiEdit`, `NotebookEdit`) and no build,
test or lint command ran after the last edit, the stop is blocked once with a request
to build and run the relevant tests — or to tell you plainly what is left unverified.

The second stop of the same turn is always let through, so it can never loop.

Recognised verification commands include Gradle, Maven, `xcodebuild`, `swift build/test`,
npm/pnpm/yarn/bun `test|build|lint`, Jest, Vitest, `tsc`, ESLint, pytest,
`python -m unittest`, mypy, ruff, `go test/build/vet`, Cargo, `dotnet`, `make`, detekt,
ktlint, SwiftLint, RSpec, PHPUnit, Flutter, `bash -n`, ShellCheck.

## Per-project config

`.claude/verify-before-done.json` in the project:

```json
{
  "enabled": true,
  "verify_patterns": ["^\\./scripts/ci"],
  "code_extensions": [".proto"]
}
```

- `enabled: false` turns the check off for that project.
- `verify_patterns` — extra regexes that count as verification.
- `code_extensions` — extra file extensions that count as code. Markdown, JSON and
  plain text edits never trigger the check.

Edits made through Bash (`sed -i`, scripts) are not seen.
