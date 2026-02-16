#!/usr/bin/env python3
"""Update task issue statuses in a GitHub Project from pull request events."""

from __future__ import annotations

import os
import sys
from typing import Any

from github_project_utils import (
    DEFAULT_PROJECT_TITLE,
    GitHubClient,
    GitHubError,
    add_issue_to_project,
    available_options,
    canonicalize,
    fetch_project_issue_item_map,
    find_project_id,
    load_project_fields,
    pick_option_id,
    update_single_select_field,
)

MANDATORY_TASK_LABEL = "juke-task"


def fetch_pr_closing_issues(
    client: GitHubClient,
    owner: str,
    repo: str,
    pr_number: int,
) -> list[dict[str, Any]]:
    query = """
    query(
      $owner: String!,
      $repo: String!,
      $prNumber: Int!,
      $after: String
    ) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $prNumber) {
          closingIssuesReferences(first: 100, after: $after) {
            nodes {
              id
              number
              labels(first: 50) {
                nodes {
                  name
                }
              }
            }
            pageInfo {
              hasNextPage
              endCursor
            }
          }
        }
      }
    }
    """

    issues: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        data = client.graphql(
            query,
            {
                "owner": owner,
                "repo": repo,
                "prNumber": pr_number,
                "after": cursor,
            },
        )
        pull_request = data.get("repository", {}).get("pullRequest")
        if pull_request is None:
            raise GitHubError(f"Pull request #{pr_number} was not found.")

        closing = pull_request.get("closingIssuesReferences", {})
        for issue in closing.get("nodes", []):
            if not isinstance(issue, dict):
                continue
            issues.append(issue)

        page_info = closing.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break

    return issues


def is_task_issue(issue: dict[str, Any]) -> bool:
    labels = issue.get("labels", {}).get("nodes", [])
    for label in labels:
        name = label.get("name")
        if isinstance(name, str) and name.lower() == MANDATORY_TASK_LABEL:
            return True
    return False


def main() -> int:
    token = (
        os.environ.get("JUKE_GH_PAT", "").strip()
        or os.environ.get("GH_PAT", "").strip()
        or os.environ.get("GITHUB_TOKEN", "").strip()
    )
    target_status = os.environ.get("TARGET_STATUS", "").strip()
    pr_number_raw = os.environ.get("PR_NUMBER", "").strip()
    project_title = os.environ.get("GH_PROJECT_TITLE", DEFAULT_PROJECT_TITLE).strip()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()

    if not token:
        print("ERROR: JUKE_GH_PAT, GH_PAT, or GITHUB_TOKEN is required.", file=sys.stderr)
        return 1
    if not target_status:
        print("ERROR: TARGET_STATUS is required.", file=sys.stderr)
        return 1
    if not pr_number_raw:
        print("ERROR: PR_NUMBER is required.", file=sys.stderr)
        return 1
    if "/" not in repository:
        print("ERROR: GITHUB_REPOSITORY must be set (owner/repo).", file=sys.stderr)
        return 1

    try:
        pr_number = int(pr_number_raw)
    except ValueError:
        print(f"ERROR: PR_NUMBER must be an integer, got '{pr_number_raw}'.", file=sys.stderr)
        return 1

    owner, repo = repository.split("/", 1)
    client = GitHubClient(token, user_agent="juke-pr-task-status-sync")

    try:
        project_id = find_project_id(client, owner, project_title)
        fields = load_project_fields(client, project_id)
        status_field = fields.get(canonicalize("Status"))
        if not status_field:
            raise GitHubError(f"Project field 'Status' not found in '{project_title}'.")

        option_id, resolved_name = pick_option_id(status_field, target_status)
        if not option_id:
            raise GitHubError(
                f"Status option '{target_status}' not found. Available: "
                f"{available_options(status_field)}"
            )

        issues = fetch_pr_closing_issues(client, owner, repo, pr_number)
        task_issues = [issue for issue in issues if is_task_issue(issue)]
        unique_task_issues: dict[str, dict[str, Any]] = {}
        for issue in task_issues:
            issue_id = issue.get("id")
            if isinstance(issue_id, str):
                unique_task_issues[issue_id] = issue

        if not task_issues:
            print(
                f"No linked task issues found for PR #{pr_number}. "
                "Use 'Closes #<task-issue-number>' in the PR body."
            )
            return 0
        if not unique_task_issues:
            print(f"No valid linked task issue node IDs found for PR #{pr_number}.")
            return 0

        project_item_map = fetch_project_issue_item_map(client, project_id)
        updated = 0
        added_to_project = 0

        for issue in unique_task_issues.values():
            issue_id = issue.get("id")
            issue_number = issue.get("number")
            if not isinstance(issue_id, str):
                continue

            item_id = project_item_map.get(issue_id)
            if not item_id:
                added_now = False
                try:
                    item_id = add_issue_to_project(client, project_id, issue_id)
                    added_now = True
                except GitHubError as exc:
                    if "already exists" in str(exc).lower():
                        project_item_map = fetch_project_issue_item_map(client, project_id)
                        item_id = project_item_map.get(issue_id)
                    else:
                        raise
                if not item_id:
                    raise GitHubError("Issue is in project but item id was not found.")
                project_item_map[issue_id] = item_id
                if added_now:
                    added_to_project += 1

            update_single_select_field(
                client=client,
                project_id=project_id,
                item_id=item_id,
                field_id=status_field.field_id,
                option_id=option_id,
            )
            updated += 1
            print(f"Updated issue #{issue_number} -> Status '{resolved_name}'.")

        print(
            f"Done. PR #{pr_number}: updated={updated}, "
            f"added_to_project={added_to_project}, target_status='{resolved_name}'."
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
