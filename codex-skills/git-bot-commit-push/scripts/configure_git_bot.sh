#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <repo>" >&2
  exit 2
fi

repo=$1
name=${CODEX_GIT_AUTHOR_NAME:-Codex Bot}
email=${CODEX_GIT_AUTHOR_EMAIL:-codex-bot@company.com}

git -C "$repo" rev-parse --is-inside-work-tree >/dev/null
git -C "$repo" config --local user.name "$name"
git -C "$repo" config --local user.email "$email"
git -C "$repo" config --local user.useConfigOnly true

printf 'configured git bot identity in %s\n' "$repo"
printf 'user.name=%s\n' "$name"
printf 'user.email=%s\n' "$email"
