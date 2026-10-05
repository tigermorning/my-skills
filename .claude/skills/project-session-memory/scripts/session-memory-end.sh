#!/bin/bash
# SessionEnd hook: capture a lightweight excerpt of the just-finished session
# into .claude/memory/inbox/, then commit it locally (no push — see below).
#
# SessionEnd hooks share a very tight timeout budget (default ~1.5s across
# ALL SessionEnd hooks combined; the "timeout" key in settings.json raises the
# ceiling for this specific hook), and their output cannot influence the model
# at all (no additionalContext, no decision control) because the session is
# already tearing down. So this script stays purely mechanical: grab the tail
# of the transcript, append it to a per-session file, then commit it. No
# summarization happens here — that's deferred to the SessionStart hook of the
# *next* session, where Claude itself can read and condense it with full
# judgment.
#
# Deliberately no `git push` here. An earlier draft added push (with pull
# --rebase first), which the Claude Code auto-mode safety classifier
# blocked from being installed: a hook that pushes to a remote unsupervised,
# on every single session end, forever, is a materially different risk than
# one that only touches local disk. Committing locally still gets the
# capture out of "uncommitted and about to vanish" into an ordinary git
# commit — an actual `git push` (by Claude, in the course of normal work,
# or by the user) later in this same checkout carries it along like any
# other local commit. That means this alone does NOT guarantee the very
# last session's capture survives if nothing ever pushes again before the
# container is permanently reclaimed — it reduces that risk to the same
# level ordinary uncommitted dev work already has, no better, no worse.
#
# Commits go only onto the default branch. A feature branch is headed for a
# PR, so a capture commit there gets pushed into a review it has nothing to
# do with (public, if the repo is). Off the default branch (feature branch,
# detached HEAD) the capture goes to session-memory-spool/ in the shared git
# dir instead: outside the work tree so a later `git add -A` cannot sweep it
# into feature work, shared by every worktree so removing a worktree does not
# lose it. The next session end on the default branch moves the spool into
# the inbox and commits it. Cost: a session that only ever runs on feature
# branches in a container that is then reclaimed loses its captures.
set -euo pipefail

input="$(cat)"
transcript_path="$(printf '%s' "$input" | jq -r '.transcript_path // empty')"
session_id="$(printf '%s' "$input" | jq -r '.session_id // empty')"

[ -n "$transcript_path" ] && [ -f "$transcript_path" ] && [ -n "$session_id" ] || exit 0

project_dir="${CLAUDE_PROJECT_DIR:-$(pwd)}"
inbox="$project_dir/.claude/memory/inbox"

# origin/HEAD is what the remote calls its default; without a remote, fall back to
# init.defaultBranch, then to whichever of main/master exists.
default_branch() {
  local ref name
  if ref="$(git -C "$project_dir" symbolic-ref -q refs/remotes/origin/HEAD)"; then
    echo "${ref#refs/remotes/origin/}"
    return
  fi
  name="$(git -C "$project_dir" config init.defaultBranch || true)"
  for b in $name main master; do
    git -C "$project_dir" show-ref -q --verify "refs/heads/$b" && { echo "$b"; return; }
  done
}

spool=""
on_default=0
if git -C "$project_dir" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  spool="$(git -C "$project_dir" rev-parse --path-format=absolute --git-common-dir)/session-memory-spool"
  branch="$(git -C "$project_dir" symbolic-ref -q --short HEAD || true)"
  [ -n "$branch" ] && [ "$branch" = "$(default_branch)" ] && on_default=1
fi
if [ "$on_default" -eq 1 ] || [ -z "$spool" ]; then dest="$inbox"; else dest="$spool"; fi
out="$dest/$session_id.md"

# Idempotent: if this session already has an entry (in either place), don't duplicate it.
if [ -f "$inbox/$session_id.md" ] || { [ -n "$spool" ] && [ -f "$spool/$session_id.md" ]; }; then
  exit 0
fi

mkdir -p "$dest"

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

[ "$on_default" -eq 1 ] || exit 0

# --- commit locally, best-effort (no push — see header comment) ---
# Failures here (no git repo, detached HEAD, nothing to commit) are
# swallowed on purpose: SessionEnd output is discarded by the harness
# anyway, so there is no way to surface an error, and this must never
# block the session from actually ending. Restricted to this one file
# (git add -- / commit --only --) so we never sweep up or commit whatever
# else the user had staged mid-work.
#
# Never commit while a merge or rebase is open: the commit would move HEAD under it and the merge
# would fail ("cannot lock ref 'HEAD'"). That covers a conflicted merge and a merge gate that holds a
# clean merge open while it runs checks (it leaves merge-gate.running in the git dir; one older than an
# hour is a gate that was killed, so it is ignored). The capture stays on disk, and because the commit
# below takes every file in the inbox, the next session end carries it along.
(
  cd "$project_dir" || exit 0
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
  gitdir="$(git rev-parse --absolute-git-dir)" || exit 0
  for open in MERGE_HEAD rebase-merge rebase-apply CHERRY_PICK_HEAD; do
    [ -e "$gitdir/$open" ] && exit 0
  done
  [ -n "$(find "$gitdir" -maxdepth 1 -name merge-gate.running -mmin -60 2>/dev/null)" ] && exit 0

  for f in "$spool"/*.md; do
    [ -f "$f" ] && mv -n -- "$f" "$inbox/"
  done

  git add -- "$inbox" || exit 0
  git diff --cached --quiet -- "$inbox" && exit 0
  git commit -q --only -m "project-session-memory: capture session $session_id" -- "$inbox" || exit 0
) || true
