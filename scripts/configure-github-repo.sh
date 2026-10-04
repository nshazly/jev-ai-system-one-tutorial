#!/usr/bin/env bash
# Configure GitHub security and permission settings for this public repository.
#
# Usage:
#   scripts/configure-github-repo.sh [OWNER/REPO]           # dry run: print what would change
#   scripts/configure-github-repo.sh [OWNER/REPO] --apply   # apply the settings
#
# Options:
#   --apply                make the changes (the default is a dry run)
#   --allow-admin-bypass   let repository admins bypass the main-branch ruleset
#   --no-sha-pinning       don't require workflows to pin actions to a full commit SHA
#
# Requires gh (logged in as an admin of the repo, token scopes: repo, workflow) and jq.
# Run it after the repo exists on GitHub and main has been pushed once.
# Safe to re-run: every call sets an absolute value, and the ruleset is updated in place.

set -euo pipefail

REPO=""
APPLY=false
ADMIN_BYPASS=false
SHA_PINNING=true

for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=true ;;
    --allow-admin-bypass) ADMIN_BYPASS=true ;;
    --no-sha-pinning) SHA_PINNING=false ;;
    -h | --help) sed -n '2,16p' "$0"; exit 0 ;;
    -*) echo "unknown option: $arg" >&2; exit 2 ;;
    *) REPO="$arg" ;;
  esac
done

command -v gh >/dev/null || { echo "gh is required: https://cli.github.com" >&2; exit 1; }
command -v jq >/dev/null || { echo "jq is required" >&2; exit 1; }

if [[ -z "$REPO" ]]; then
  REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null) || {
    echo "Pass OWNER/REPO, or run this from a clone that has a GitHub remote." >&2
    exit 2
  }
fi

RULESET_NAME="protect-main"
REQUIRED_CHECKS=("lint" "test (3.12)" "test (3.13)")  # job names from .github/workflows/ci.yml
GITHUB_ACTIONS_APP_ID=15368                    # accept those checks only from GitHub Actions
ADMIN_ROLE_ID=5                                # built-in repository "admin" role
TOPICS='["jev","ollama","nimble","decision-models","llm-guardrails","python","tutorial"]'

failures=()

# api METHOD PATH [JSON_BODY]: PATH is relative to repos/OWNER/REPO.
api() {
  local method=$1 path=$2 body=${3:-}
  if ! $APPLY; then
    echo "    would: $method /repos/$REPO$path${body:+ $(jq -c . <<<"$body")}"
    return 0
  fi
  local args=(--method "$method"
    -H "Accept: application/vnd.github+json"
    -H "X-GitHub-Api-Version: 2022-11-28"
    "repos/$REPO$path")
  if [[ -n "$body" ]]; then
    gh api "${args[@]}" --input - <<<"$body" >/dev/null
  else
    gh api "${args[@]}" >/dev/null
  fi
}

# step "description" METHOD PATH [JSON_BODY]: keep going on failure, report at the end.
step() {
  local desc=$1
  shift
  echo "  - $desc"
  if ! api "$@"; then
    echo "    FAILED: $desc" >&2
    failures+=("$desc")
  fi
}

echo "Repository: $REPO ($($APPLY && echo "apply" || echo "dry run; add --apply to make changes"))"
repo_exists=false
if repo_json=$(gh api "repos/$REPO" 2>/dev/null); then
  repo_exists=true
  read -r visibility default_branch is_admin < <(jq -r '[.visibility, .default_branch, .permissions.admin] | @tsv' <<<"$repo_json")
  echo "  visibility=$visibility default_branch=$default_branch admin=$is_admin"
  [[ "$is_admin" == true ]] || { echo "You need admin access to $REPO." >&2; exit 1; }
  [[ "$visibility" == public ]] || echo "  warning: the repo is $visibility; several features below are free only for public repos." >&2
elif $APPLY; then
  echo "Repository $REPO not found. Create it and push main first." >&2
  exit 1
else
  echo "  (repository not found yet; showing the planned changes only)"
fi

echo
echo "General"
step "Issues on; wiki and projects off; squash merges only; delete branches after merge" \
  PATCH "" "$(jq -n '{
    has_issues: true, has_wiki: false, has_projects: false,
    allow_squash_merge: true, allow_merge_commit: false, allow_rebase_merge: false,
    allow_auto_merge: false, delete_branch_on_merge: true, allow_update_branch: true,
    squash_merge_commit_title: "PR_TITLE", squash_merge_commit_message: "PR_BODY"}')"
step "Topics" PUT /topics "$(jq -n --argjson t "$TOPICS" '{names: $t}')"

echo
echo "Security"
step "Dependabot alerts" PUT /vulnerability-alerts
step "Dependabot security updates" PUT /automated-security-fixes
step "Secret scanning and push protection" PATCH "" \
  '{"security_and_analysis":{"secret_scanning":{"status":"enabled"},"secret_scanning_push_protection":{"status":"enabled"}}}'
step "Private vulnerability reporting (SECURITY.md points here)" PUT /private-vulnerability-reporting
step "CodeQL default setup for Python and GitHub Actions" PATCH /code-scanning/default-setup \
  '{"state":"configured","query_suite":"default","languages":["python","actions"]}'

echo
echo "Actions"
step "Allow only selected actions; require full-SHA pinning: $SHA_PINNING" PUT /actions/permissions \
  "$(jq -n --argjson pin "$SHA_PINNING" '{enabled: true, allowed_actions: "selected", sha_pinning_required: $pin}')"
step "Allow-list: GitHub-owned actions and astral-sh/setup-uv" PUT /actions/permissions/selected-actions \
  '{"github_owned_allowed":true,"verified_allowed":false,"patterns_allowed":["astral-sh/setup-uv@*"]}'
step "GITHUB_TOKEN read-only by default; workflows can't approve pull requests" PUT /actions/permissions/workflow \
  '{"default_workflow_permissions":"read","can_approve_pull_request_reviews":false}'
step "Require approval before running workflows from any outside contributor" \
  PUT /actions/permissions/fork-pr-contributor-approval '{"approval_policy":"all_external_contributors"}'

echo
echo "Branch ruleset"
checks=$(printf '%s\n' "${REQUIRED_CHECKS[@]}" |
  jq -R --argjson app "$GITHUB_ACTIONS_APP_ID" '{context: ., integration_id: $app}' | jq -s .)
ruleset=$(jq -n --arg name "$RULESET_NAME" --argjson checks "$checks" \
  --argjson bypass "$ADMIN_BYPASS" --argjson role "$ADMIN_ROLE_ID" '{
  name: $name, target: "branch", enforcement: "active",
  conditions: {ref_name: {include: ["~DEFAULT_BRANCH"], exclude: []}},
  bypass_actors: (if $bypass then [{actor_id: $role, actor_type: "RepositoryRole", bypass_mode: "always"}] else [] end),
  rules: [
    {type: "deletion"},
    {type: "non_fast_forward"},
    {type: "pull_request", parameters: {
      required_approving_review_count: 0, dismiss_stale_reviews_on_push: false,
      require_code_owner_review: false, require_last_push_approval: false,
      required_review_thread_resolution: false, allowed_merge_methods: ["squash"]}},
    {type: "required_status_checks", parameters: {
      strict_required_status_checks_policy: false, required_status_checks: $checks}}
  ]}')
desc="'$RULESET_NAME' on the default branch: no deletion or force push; PR (squash) with passing ${REQUIRED_CHECKS[*]}; admin bypass: $ADMIN_BYPASS"
existing_id=""
if $repo_exists; then
  existing_id=$(gh api "repos/$REPO/rulesets" --jq ".[] | select(.name == \"$RULESET_NAME\") | .id" 2>/dev/null || true)
fi
if [[ -n "$existing_id" ]]; then
  step "Update ruleset $desc" PUT "/rulesets/$existing_id" "$ruleset"
else
  step "Create ruleset $desc" POST /rulesets "$ruleset"
fi

if $APPLY; then
  echo
  echo "Resulting settings"
  gh api "repos/$REPO" --jq '{visibility, has_wiki, has_projects, allow_squash_merge, allow_merge_commit,
    allow_rebase_merge, delete_branch_on_merge, secret_scanning: .security_and_analysis.secret_scanning.status,
    push_protection: .security_and_analysis.secret_scanning_push_protection.status}' || true
  if gh api "repos/$REPO/vulnerability-alerts" --silent 2>/dev/null; then
    echo '{"dependabot_alerts":"enabled"}'
  else
    echo '{"dependabot_alerts":"disabled"}'
  fi
  gh api "repos/$REPO/private-vulnerability-reporting" || true
  gh api "repos/$REPO/code-scanning/default-setup" --jq '{codeql: .state, languages}' || true
  gh api "repos/$REPO/actions/permissions" || true
  gh api "repos/$REPO/actions/permissions/workflow" || true
  gh api "repos/$REPO/actions/permissions/fork-pr-contributor-approval" || true
  gh api "repos/$REPO/rulesets" --jq '[.[] | {id, name, enforcement}]' || true
fi

echo
if ((${#failures[@]})); then
  echo "${#failures[@]} step(s) failed:" >&2
  printf '  - %s\n' "${failures[@]}" >&2
  exit 1
fi
echo "Done."
