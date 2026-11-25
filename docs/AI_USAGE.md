# AI usage

This repository was built with Claude Code (an AI coding agent) working from `SPECS.md` and `CLAUDE.md`.

- The agent wrote the code, infrastructure and docs; the owner defined the requirements and rules.
- Output was reviewed through automated checks only: linters (ruff, golangci-lint, `helm lint`, `terraform validate`),
  unit tests per detector/feature, an integration test through moto + Postgres, a Playwright journey, and CI.
- Everything shown in `proof/` was produced by scripts against the running system, not edited by hand.
- Cloud work was limited to a dedicated AWS profile and torn down by script, with a verification script.
