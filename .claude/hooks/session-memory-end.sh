#!/bin/bash
# SessionEnd hook: capture a lightweight excerpt of the just-finished session
# into .claude/memory/inbox/ so the next session can pick it up.
#
# SessionEnd hooks share a very tight timeout budget (default ~1.5s across
# ALL SessionEnd hooks combined), and their output cannot influence the model
# at all (no additionalContext, no decision control) because the session is
# already tearing down. So this script stays purely mechanical: grab the tail
# of the transcript and append it to a per-session file. No summarization
# happens here — that's deferred to the SessionStart hook of the *next*
# session, where Claude itself can read and condense it with full judgment.
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
