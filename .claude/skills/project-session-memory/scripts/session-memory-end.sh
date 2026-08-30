#!/bin/bash
# SessionEnd hook: capture a lightweight excerpt of the just-finished session
# into .claude/memory/inbox/, then commit and push it so the capture survives
# past this container's teardown.
#
# SessionEnd hooks share a very tight timeout budget (default ~1.5s across
# ALL SessionEnd hooks combined; the "timeout" key in settings.json raises the
# ceiling for this specific hook), and their output cannot influence the model
# at all (no additionalContext, no decision control) because the session is
# already tearing down. So this script stays purely mechanical: grab the tail
# of the transcript, append it to a per-session file, then commit+push it. No
# summarization happens here — that's deferred to the SessionStart hook of the
# *next* session, where Claude itself can read and condense it with full
# judgment.
#
# The commit+push step is what makes the capture actually survive: in an
# environment where every new session gets a fresh clone (Claude Code on the
# web), anything left only on local disk disappears the moment this
# container is reclaimed. Committing means the raw transcript excerpt is
# what ends up in git history — accept that before enabling this on a repo
# whose history is visible to people you wouldn't otherwise show a
# transcript to.
set -euo pipefail

input="$(cat)"
transcript_path="$(printf '%s' "$input" | jq -r '.transcript_path // empty')"
session_id="$(printf '%s' "$input" | jq -r '.session_id // empty')"

[ -n "$transcript_path" ] && [ -f "$transcript_path" ] && [ -n "$session_id" ] || exit 0

project_dir="${CLAUDE_PROJECT_DIR:-$(pwd)}"
inbox="$project_dir/.claude/memory/inbox"
out="$inbox/$session_id.md"

# Idempotent: if this session already has an inbox entry, don't duplicate it.
[ -f "$out" ] && exit 0

mkdir -p "$inbox"

{
  echo "### $(date -u +"%Y-%m-%dT%H:%M:%SZ") (session $session_id)"
  echo
  tail -n 300 "$transcript_path" | jq -r '
    select(.type == "user" or .type == "assistant")
    | .message.content
    | if type == "array" then (map(select(.type == "text") | .text) | join(" "))
      elif type == "string" then .
      else empty end
    | select(length > 0)
  ' 2>/dev/null | tail -n 40
  echo
} >> "$out"

# --- commit + push, best-effort ---
# Failures here (no git repo, detached HEAD, no push access, network
# hiccup, a real conflict) are swallowed on purpose: SessionEnd output is
# discarded by the harness anyway, so there is no way to surface an error,
# and a failed push must never block the session from actually ending.
# Restricted to this one file (git add -- / commit --only --) so we never
# sweep up or commit whatever else the user had staged mid-work.
(
  cd "$project_dir" || exit 0
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
  branch="$(git symbolic-ref --short -q HEAD)" || exit 0
  [ -n "$branch" ] || exit 0

  git add -- "$out" || exit 0
  git diff --cached --quiet -- "$out" && exit 0
  git commit -q --only -m "project-session-memory: capture session $session_id" -- "$out" || exit 0

  if ! timeout 5 git pull -q --rebase origin "$branch" >/dev/null 2>&1; then
    git rebase --abort >/dev/null 2>&1 || true
  fi
  timeout 8 git push -q origin "HEAD:$branch" >/dev/null 2>&1 || true
) || true
