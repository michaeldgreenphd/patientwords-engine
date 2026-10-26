#!/usr/bin/env bash
# Publish an explicit CI output list without stashing or resetting the source artifacts.
set -euo pipefail
MESSAGE=$1
LIST=$2
SOURCE_ROOT=$PWD
git fetch origin "$BRANCH"
PUBLISH_ROOT=$(mktemp -d "$RUNNER_TEMP/judge-publish.XXXXXX")
git worktree add --detach "$PUBLISH_ROOT" "origin/$BRANCH"
trap 'git -C "$SOURCE_ROOT" worktree remove --force "$PUBLISH_ROOT"' EXIT
refuse_changed_remote_file() {
  local source=$1 relative=$2
  if git -C "$PUBLISH_ROOT" ls-files --error-unmatch -- "$relative" >/dev/null 2>&1; then
    if ! cmp -s "$source" "$PUBLISH_ROOT/$relative"; then
      echo "judge_publish_remote_collision: $relative" >&2
      exit 1
    fi
  fi
}
while IFS= read -r path; do
  case "$path" in
    ""|/*|..|../*|*/../*|*/..) echo "judge_publish_invalid_path: $path" >&2; exit 1 ;;
  esac
  case "$path" in
    data/advice/*|data/petri/runs/*|data/petri/rejudge/*|data/petri/secondary/*|data/action_annotations/runs/action_*.report.json) ;;
    *) echo "judge_publish_invalid_path: $path" >&2; exit 1 ;;
  esac
  if [ -d "$SOURCE_ROOT/$path" ]; then
    while IFS= read -r -d '' source; do
      refuse_changed_remote_file "$source" "${source#"$SOURCE_ROOT/"}"
    done < <(find "$SOURCE_ROOT/$path" -type f -print0)
    mkdir -p "$PUBLISH_ROOT/$path"
    cp -R "$SOURCE_ROOT/$path/." "$PUBLISH_ROOT/$path/"
  elif [ -f "$SOURCE_ROOT/$path" ]; then
    refuse_changed_remote_file "$SOURCE_ROOT/$path" "$path"
    mkdir -p "$PUBLISH_ROOT/$(dirname "$path")"
    cp "$SOURCE_ROOT/$path" "$PUBLISH_ROOT/$path"
  else
    echo "judge_publish_missing: $path" >&2
    exit 1
  fi
  git -C "$PUBLISH_ROOT" add -f -- "$path"
done < "$LIST"
cd "$PUBLISH_ROOT"
if git diff --cached --quiet; then exit 0; fi
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git commit -m "$MESSAGE"
for i in 1 2 3 4 5; do
  if git pull --rebase origin "$BRANCH" && git push origin HEAD:"refs/heads/$BRANCH"; then exit 0; fi
  git rebase --abort 2>/dev/null || true
  sleep $((i * 2))
done
exit 1
