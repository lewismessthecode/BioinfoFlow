#!/usr/bin/env bash
set -euo pipefail

DEFAULT_BRANCH="${DEFAULT_BRANCH:-main}"
REQUIRED_APPROVALS="${REQUIRED_APPROVALS:-0}"
REPOSITORY="${1:-$(gh repo view --json nameWithOwner --jq .nameWithOwner)}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI is required: https://cli.github.com/" >&2
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "Run 'gh auth login' with repo and workflow scopes first." >&2
  exit 1
fi

echo "Configuring ${REPOSITORY}..."

gh api \
  --method PATCH \
  "repos/${REPOSITORY}" \
  --input - >/dev/null <<'JSON'
{
  "allow_auto_merge": true,
  "allow_merge_commit": false,
  "allow_rebase_merge": true,
  "allow_squash_merge": true,
  "delete_branch_on_merge": true,
  "squash_merge_commit_message": "PR_BODY",
  "squash_merge_commit_title": "PR_TITLE"
}
JSON

gh api \
  --method PUT \
  "repos/${REPOSITORY}/actions/permissions/workflow" \
  --input - >/dev/null <<'JSON'
{
  "default_workflow_permissions": "read",
  "can_approve_pull_request_reviews": false
}
JSON

gh api \
  --method PUT \
  "repos/${REPOSITORY}/branches/${DEFAULT_BRANCH}/protection" \
  --input - >/dev/null <<JSON
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "backend",
      "frontend",
      "docker"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": ${REQUIRED_APPROVALS}
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
JSON

echo "Done."
echo
echo "Required checks: backend, frontend, docker"
echo "Required approvals: ${REQUIRED_APPROVALS}"
echo
echo "For a team repo, rerun with REQUIRED_APPROVALS=1 after adding collaborators:"
echo "  REQUIRED_APPROVALS=1 scripts/github/configure-repo.sh ${REPOSITORY}"
