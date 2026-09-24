#!/usr/bin/env bash
# Stage everything, refuse the commit if it looks like a credential or a
# locally-excluded pattern is about to be published, then commit.
#
# Extra project-specific patterns can be kept in .git/local-scan-patterns.txt,
# one grep -E pattern per line. That file lives inside .git, so it is never
# pushed and never appears in the repository.
set -e

MSG="${1:?usage: ./scripts/safe-commit.sh \"commit message\"}"
LOCAL_PATTERNS=".git/local-scan-patterns.txt"

echo "=== staging ==="
git add -A

echo
echo "=== files to be committed ==="
git status --short

echo
echo "=== scanning for secrets ==="
if git diff --cached -- . ':(exclude)scripts/safe-commit.sh' \
   | grep -inE "(password|api[_-]?key|secret|token) *= *[\"'][^\"'\$]{6,}|connectionstring *=|sk-[A-Za-z0-9]{20}|AccountKey[=]"; then
  echo ">>> BLOCKED: possible secret found above"; exit 1
fi
echo "clean"

if [ -s "$LOCAL_PATTERNS" ]; then
  echo
  echo "=== scanning for locally-excluded patterns ==="
  if git diff --cached -- . ':(exclude)scripts/safe-commit.sh' | grep -inEf "$LOCAL_PATTERNS"; then
    echo ">>> BLOCKED: locally-excluded pattern found above"; exit 1
  fi
  if git ls-files | grep -iEf "$LOCAL_PATTERNS"; then
    echo ">>> BLOCKED: file above should not be tracked"; exit 1
  fi
  echo "clean"
fi

echo
echo "=== checking tracked files ==="
if git ls-files | grep -iE "(^|/)\.env$|local\.settings\.json$|\.pem$|\.pfx$"; then
  echo ">>> BLOCKED: credential file above should not be tracked"
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
