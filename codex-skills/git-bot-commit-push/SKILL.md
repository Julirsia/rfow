---
name: git-bot-commit-push
description: Use when the user wants Codex to commit and push with a bot identity instead of a person's local account. Configure repo-local git author settings, validate the remote host/org, and only push through a bot-managed credential such as a GitHub App or dedicated bot URL.
---

# Git Bot Commit Push

Use this skill when the user wants commits authored by Codex or a bot identity, not the machine owner's OS account.

## Workflow

1. Configure repo-local git identity first:
   - Run `scripts/configure_git_bot.sh <repo>`
   - This sets `user.name`, `user.email`, and `user.useConfigOnly=true` in the target repo only.
2. Stage only the intended files with explicit `git add`.
3. If validation is required, set `CODEX_GIT_TEST_COMMAND` before commit.
4. Push only through a bot-managed channel:
   - Preferred: set `CODEX_GIT_PUSH_URL` to a GitHub App or dedicated bot credential URL.
   - Alternative: set `CODEX_GIT_ALLOW_EXISTING_ORIGIN=1` only when the existing `origin` already uses a bot/deploy-key path.
5. Run `scripts/guarded_commit_push.sh <repo> "<commit message>"`.

## Rules

- Never rely on global git identity.
- Never leave `user.useConfigOnly` unset.
- Never use this flow if only a personal credential is available and the user asked for a non-person actor.
- If `CODEX_GIT_PUSH_URL` is missing and existing `origin` is not explicitly allowed, stop before creating the commit.
- Prefer `git push --force-with-lease` only when the user explicitly asked to rewrite history.

## Environment

- `CODEX_GIT_AUTHOR_NAME`
  - Default: `Codex Bot`
- `CODEX_GIT_AUTHOR_EMAIL`
  - Default: `codex-bot@company.com`
- `CODEX_GIT_ALLOWED_HOSTS`
  - Comma-separated allowlist, default `github.com`
- `CODEX_GIT_ALLOWED_ORGS`
  - Optional comma-separated allowlist such as `my-org,infra-team`
- `CODEX_GIT_TEST_COMMAND`
  - Optional validation command executed before commit
- `CODEX_GIT_PUSH_URL`
  - Bot-managed push target URL
- `CODEX_GIT_ALLOW_EXISTING_ORIGIN`
  - Set to `1` only when the current origin is already bot-managed

## Notes

- Commit author and push actor are different things.
- This skill can guarantee bot commit metadata locally.
- It can only guarantee a non-person push actor when the environment provides a bot/App push credential.
