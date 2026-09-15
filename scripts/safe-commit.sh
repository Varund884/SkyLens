#!/usr/bin/env bash
set -e

MSG="${1:?usage: ./scripts/safe-commit.sh \"commit message\"}"

echo "=== staging ==="
git add -A

echo
echo "=== files to be committed ==="
git status --short

echo
echo "=== scanning for configured patterns ==="
if git diff --cached -- . ':(exclude)scripts/safe-commit.sh' \
   | grep -inE "configured patterns"; then
  echo ">>> BLOCKED: configured pattern found above"; exit 1
fi
echo "clean"

echo
echo "=== scanning for secrets ==="
if git diff --cached -- . ':(exclude)scripts/safe-commit.sh' \
   | grep -inE "password *=|api[_-]?key *=|secret *=|connectionstring|sk-[A-Za-z0-9]{20}|AccountKey="; then
  echo ">>> BLOCKED: possible secret found above"; exit 1
fi
echo "clean"

echo
echo "=== checking tracked files ==="
if git ls-files | grep -iE "\.env$"; then
  echo ">>> BLOCKED: file above should not be tracked"
  echo "    fix: git rm --cached <file> && echo '<file>' >> .gitignore"
  exit 1
fi
echo "clean"

echo
read -p "Commit these files? [y/N] " ok
[[ "$ok" == "y" || "$ok" == "Y" ]] || { echo "aborted"; exit 1; }

git commit -m "$MSG"
echo
echo "done."
