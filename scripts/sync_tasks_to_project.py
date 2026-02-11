#!/usr/bin/env python3
"""Sync task markdown files to GitHub Issues and a user Project (Projects v2)."""

from __future__ import annotations

import hashlib
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import yaml

API_BASE_URL = "https://api.github.com"
GRAPHQL_URL = f"{API_BASE_URL}/graphql"
TASK_GLOB = "tasks/**/*.md"
TASK_MARKER_PREFIX = "juke-task-id: "
TASK_STABLE_MARKER_PREFIX = "juke-task-key: "
MANDATORY_LABEL = "juke-task"
EXCLUDED_TASK_BASENAMES = {"README.md"}
DEFAULT_PROJECT_TITLE = "Juke Project"
DEFAULT_REPO = "juke"


class GitHubError(RuntimeError):
    """Raised when a GitHub API call fails."""


@dataclass
class ProjectField:
    field_id: str
    name: str
    option_by_key: dict[str, str]


class GitHubClient:
    def __init__(self, token: str) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "juke-task-sync",
            }
        )

    def rest(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{API_BASE_URL}{path}"
        response = self._session.request(method=method, url=url, timeout=30, **kwargs)
        if response.status_code >= 400:
            details = ""
            try:
                payload = response.json()
                details = payload.get("message", "")
            except ValueError:
                details = response.text
            raise GitHubError(
                f"{method} {path} failed with {response.status_code}: {details}"
            )
        if response.status_code == 204:
            return None
        return response.json()

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> Any:
        response = self._session.post(
            GRAPHQL_URL,
            json={"query": query, "variables": variables or {}},
            timeout=30,
        )
        if response.status_code >= 400:
            raise GitHubError(
                f"GraphQL HTTP {response.status_code}: {response.text[:500]}"
            )
        payload = response.json()
        errors = payload.get("errors")
        if errors:
            message = "; ".join(error.get("message", "Unknown GraphQL error") for error in errors)
            raise GitHubError(f"GraphQL error: {message}")
        return payload.get("data", {})


def canonicalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def parse_frontmatter(content: str) -> tuple[dict[str, Any] | None, str]:
    match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", content, re.DOTALL)
    if not match:
        return None, content

    raw_meta, body = match.groups()
    try:
        metadata = yaml.safe_load(raw_meta) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML frontmatter: {exc}") from exc

    if not isinstance(metadata, dict):
        raise ValueError("Frontmatter must parse as a YAML object.")

    return metadata, body


def parse_labels(metadata: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    raw = metadata.get("labels")
    if raw is None and "label" in metadata:
        raw = metadata.get("label")
    if raw is None:
        raw = []
    if isinstance(raw, str):
        labels = [raw]
    elif isinstance(raw, list):
        labels = [str(value) for value in raw]

    deduped: list[str] = []
    seen: set[str] = set()
    for label in labels + [MANDATORY_LABEL]:
        normalized = label.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped


def color_for_label(name: str) -> str:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return digest[:6]


def ensure_label_exists(client: GitHubClient, owner: str, repo: str, label: str) -> None:
    label_path = quote(label, safe="")
    try:
        client.rest("GET", f"/repos/{owner}/{repo}/labels/{label_path}")
        return
    except GitHubError as exc:
        if "404" not in str(exc):
            raise

    try:
        client.rest(
            "POST",
            f"/repos/{owner}/{repo}/labels",
            json={
                "name": label,
                "color": color_for_label(label),
                "description": "Managed by tasks sync automation",
            },
        )
        print(f"Created missing label: {label}")
    except GitHubError as exc:
        # Handles rare race conditions where another run created the label first.
        if "already_exists" in str(exc) or "422" in str(exc):
            return
        raise


def build_issue_body(task_path: str, markdown_body: str, stable_task_key: str | None) -> str:
    clean_body = markdown_body.rstrip()
    marker = f"<!-- {TASK_MARKER_PREFIX}{task_path} -->"
    stable_marker = (
        f"<!-- {TASK_STABLE_MARKER_PREFIX}{stable_task_key} -->"
        if stable_task_key
        else None
    )
    source = f"_Source: `{task_path}`_"
    header_lines = [marker]
    if stable_marker:
        header_lines.append(stable_marker)
    header = "\n".join(header_lines)
    if clean_body:
        return f"{header}\n{source}\n\n{clean_body}\n"
    return f"{header}\n{source}\n"


def derive_title(task_path: str, metadata: dict[str, Any]) -> str:
    title = metadata.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    return Path(task_path).name


def derive_stable_task_key(metadata: dict[str, Any]) -> str | None:
    for key_name in ("task_id", "id"):
        raw = metadata.get(key_name)
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            return value
    return None


def extract_marker_value(body: str, marker_prefix: str) -> str | None:
    pattern = rf"<!--\s*{re.escape(marker_prefix)}(.*?)\s*-->"
    match = re.search(pattern, body, re.DOTALL)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def create_issue(
    client: GitHubClient,
    owner: str,
    repo: str,
    title: str,
    body: str,
    labels: list[str],
) -> dict[str, Any]:
    return client.rest(
        "POST",
        f"/repos/{owner}/{repo}/issues",
        json={"title": title, "body": body, "labels": labels},
    )


def update_issue(
    client: GitHubClient,
    owner: str,
    repo: str,
    issue_number: int,
    title: str,
    body: str,
    labels: list[str],
) -> dict[str, Any]:
    return client.rest(
        "PATCH",
        f"/repos/{owner}/{repo}/issues/{issue_number}",
        json={"title": title, "body": body, "labels": labels},
    )


def issue_needs_update(issue: dict[str, Any], title: str, body: str, labels: list[str]) -> bool:
    existing_title = issue.get("title", "")
    existing_body = issue.get("body", "")
    existing_labels = sorted(
        label_obj.get("name", "")
        for label_obj in issue.get("labels", [])
        if isinstance(label_obj, dict)
    )
    desired_labels = sorted(labels)
    return (
        existing_title != title
        or existing_body != body
        or existing_labels != desired_labels
    )


def find_project_id(client: GitHubClient, owner: str, project_title: str) -> str:
    query = """
    query($login: String!, $after: String) {
      user(login: $login) {
        projectsV2(first: 50, after: $after) {
          nodes {
            id
            title
          }
          pageInfo {
            hasNextPage
            endCursor
          }
        }
      }
    }
    """

    cursor: str | None = None
    while True:
        data = client.graphql(query, {"login": owner, "after": cursor})
        projects = data.get("user", {}).get("projectsV2", {})
        nodes = projects.get("nodes", [])
        for node in nodes:
            if node.get("title") == project_title and isinstance(node.get("id"), str):
                return node["id"]

        page_info = projects.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break

    raise GitHubError(f'Could not find user project titled "{project_title}".')


def load_project_fields(client: GitHubClient, project_id: str) -> dict[str, ProjectField]:
    query = """
    query($projectId: ID!, $after: String) {
      node(id: $projectId) {
        ... on ProjectV2 {
          fields(first: 50, after: $after) {
            nodes {
              __typename
              ... on ProjectV2FieldCommon {
                id
                name
                dataType
              }
              ... on ProjectV2SingleSelectField {
                options {
                  id
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
    fields: dict[str, ProjectField] = {}
    cursor: str | None = None

    while True:
        data = client.graphql(query, {"projectId": project_id, "after": cursor})
        fields_connection = data.get("node", {}).get("fields", {})
        for node in fields_connection.get("nodes", []):
            if not node or node.get("__typename") != "ProjectV2SingleSelectField":
                continue
            name = node.get("name")
            field_id = node.get("id")
            if not isinstance(name, str) or not isinstance(field_id, str):
                continue
            options = node.get("options", [])
            option_by_key: dict[str, str] = {}
            for option in options:
                option_name = option.get("name")
                option_id = option.get("id")
                if not isinstance(option_name, str) or not isinstance(option_id, str):
                    continue
                option_by_key[canonicalize(option_name)] = option_id

            fields[canonicalize(name)] = ProjectField(
                field_id=field_id,
                name=name,
                option_by_key=option_by_key,
            )

        page_info = fields_connection.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break

    return fields


def load_project(
    client: GitHubClient, owner: str, project_title: str
) -> tuple[str, dict[str, ProjectField]]:
    project_id = find_project_id(client, owner, project_title)
    fields = load_project_fields(client, project_id)
    return project_id, fields


def index_existing_task_issues(
    client: GitHubClient, owner: str, repo: str
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_path: dict[str, dict[str, Any]] = {}
    by_stable_key: dict[str, dict[str, Any]] = {}
    page = 1

    while True:
        issues = client.rest(
            "GET",
            f"/repos/{owner}/{repo}/issues",
            params={
                "state": "all",
                "labels": MANDATORY_LABEL,
                "per_page": 100,
                "page": page,
            },
        )
        if not isinstance(issues, list) or not issues:
            break

        for issue in issues:
            if "pull_request" in issue:
                continue
            body = issue.get("body") or ""
            if not isinstance(body, str):
                continue

            marker_path = extract_marker_value(body, TASK_MARKER_PREFIX)
            marker_stable_key = extract_marker_value(body, TASK_STABLE_MARKER_PREFIX)
            if not marker_path and not marker_stable_key:
                continue

            number = issue.get("number")
            if marker_path:
                existing = by_path.get(marker_path)
                if existing and isinstance(number, int):
                    existing_number = existing.get("number")
                    if isinstance(existing_number, int) and existing_number < number:
                        print(
                            f"WARNING [{marker_path}] Duplicate task marker; using #{existing_number}."
                        )
                        issue = existing
                    else:
                        print(
                            f"WARNING [{marker_path}] Duplicate task marker; using #{number}."
                        )
                by_path[marker_path] = issue

            if marker_stable_key:
                existing_key_issue = by_stable_key.get(marker_stable_key)
                if existing_key_issue and isinstance(number, int):
                    existing_number = existing_key_issue.get("number")
                    if isinstance(existing_number, int) and existing_number < number:
                        print(
                            f"WARNING [stable:{marker_stable_key}] Duplicate stable marker; "
                            f"using #{existing_number}."
                        )
                        issue = existing_key_issue
                    else:
                        print(
                            f"WARNING [stable:{marker_stable_key}] Duplicate stable marker; "
                            f"using #{number}."
                        )
                by_stable_key[marker_stable_key] = issue

        if len(issues) < 100:
            break
        page += 1

    return by_path, by_stable_key


def fetch_project_issue_item_map(client: GitHubClient, project_id: str) -> dict[str, str]:
    query = """
    query($projectId: ID!, $after: String) {
      node(id: $projectId) {
        ... on ProjectV2 {
          items(first: 100, after: $after) {
            nodes {
              id
              content {
                __typename
                ... on Issue {
                  id
                  number
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
    mapping: dict[str, str] = {}
    cursor: str | None = None

    while True:
        data = client.graphql(query, {"projectId": project_id, "after": cursor})
        items = (
            data.get("node", {})
            .get("items", {})
        )
        for node in items.get("nodes", []):
            content = node.get("content")
            if not isinstance(content, dict):
                continue
            if content.get("__typename") != "Issue":
                continue
            issue_id = content.get("id")
            item_id = node.get("id")
            if isinstance(issue_id, str) and isinstance(item_id, str):
                mapping[issue_id] = item_id

        page_info = items.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break

    return mapping


def add_issue_to_project(client: GitHubClient, project_id: str, issue_node_id: str) -> str:
    mutation = """
    mutation($projectId: ID!, $contentId: ID!) {
      addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
        item {
          id
        }
      }
    }
    """
    data = client.graphql(mutation, {"projectId": project_id, "contentId": issue_node_id})
    item_id = (
        data.get("addProjectV2ItemById", {})
        .get("item", {})
        .get("id")
    )
    if not isinstance(item_id, str):
        raise GitHubError("Failed to add issue to project: missing item id.")
    return item_id


def update_single_select_field(
    client: GitHubClient,
    project_id: str,
    item_id: str,
    field_id: str,
    option_id: str,
) -> None:
    mutation = """
    mutation(
      $projectId: ID!,
      $itemId: ID!,
      $fieldId: ID!,
      $optionId: String!
    ) {
      updateProjectV2ItemFieldValue(
        input: {
          projectId: $projectId
          itemId: $itemId
          fieldId: $fieldId
          value: {singleSelectOptionId: $optionId}
        }
      ) {
        projectV2Item {
          id
        }
      }
    }
    """
    client.graphql(
        mutation,
        {
            "projectId": project_id,
            "itemId": item_id,
            "fieldId": field_id,
            "optionId": option_id,
        },
    )


def task_files() -> list[Path]:
    files: list[Path] = []
    for path in Path(".").glob(TASK_GLOB):
        if not path.is_file():
            continue
        if path.name in EXCLUDED_TASK_BASENAMES:
            continue
        if path.name.startswith("_"):
            continue
        files.append(path)
    return sorted(files)


def pick_option_id(field: ProjectField, raw_value: Any) -> str | None:
    if raw_value is None:
        return None
    value = str(raw_value).strip()
    if not value:
        return None
    return field.option_by_key.get(canonicalize(value))


def main() -> int:
    gh_pat = os.environ.get("JUKE_GH_PAT", "").strip()
    if not gh_pat:
        gh_pat = os.environ.get("GH_PAT", "").strip()
    gh_project_title = DEFAULT_PROJECT_TITLE
    gh_repo = DEFAULT_REPO

    gh_owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "").strip()
    if not gh_owner:
        repo_from_action = os.environ.get("GITHUB_REPOSITORY", "").strip()
        if "/" in repo_from_action:
            gh_owner = repo_from_action.split("/", 1)[0].strip()
    if not gh_owner:
        gh_owner = os.environ.get("GH_OWNER", "").strip()

    if not gh_pat:
        print("ERROR: JUKE_GH_PAT (or GH_PAT) is required.", file=sys.stderr)
        return 1
    if not gh_owner:
        print(
            "ERROR: Could not determine GitHub owner from GITHUB_REPOSITORY_OWNER "
            "or GITHUB_REPOSITORY.",
            file=sys.stderr,
        )
        return 1

    client = GitHubClient(gh_pat)
    project_id, project_fields = load_project(client, gh_owner, gh_project_title)
    project_item_map = fetch_project_issue_item_map(client, project_id)
    existing_issues_by_path, existing_issues_by_stable_key = index_existing_task_issues(
        client, gh_owner, gh_repo
    )

    tasks = task_files()
    print(f"Discovered {len(tasks)} task markdown file(s).")

    synced_count = 0
    skipped_count = 0
    failed_count = 0
    warning_count = 0
    ensured_labels: set[str] = set()

    def warn(message: str) -> None:
        nonlocal warning_count
        warning_count += 1
        print(f"WARNING {message}")

    for path in tasks:
        rel_path = path.as_posix()
        try:
            raw = path.read_text(encoding="utf-8")
            metadata, markdown_body = parse_frontmatter(raw)
            if metadata is None:
                skipped_count += 1
                print(f"Skipped {rel_path}: missing YAML frontmatter.")
                continue
            title = derive_title(rel_path, metadata)
            labels = parse_labels(metadata)
            stable_task_key = derive_stable_task_key(metadata)

            for label in labels:
                label_key = label.lower()
                if label_key in ensured_labels:
                    continue
                ensure_label_exists(client, gh_owner, gh_repo, label)
                ensured_labels.add(label_key)

            issue_body = build_issue_body(rel_path, markdown_body, stable_task_key)
            existing = existing_issues_by_path.get(rel_path)
            if not existing and stable_task_key:
                existing = existing_issues_by_stable_key.get(stable_task_key)

            if existing:
                issue_number = existing["number"]
                issue_node_id = existing["node_id"]
                if issue_needs_update(existing, title, issue_body, labels):
                    existing = update_issue(
                        client=client,
                        owner=gh_owner,
                        repo=gh_repo,
                        issue_number=issue_number,
                        title=title,
                        body=issue_body,
                        labels=labels,
                    )
                    print(f"Updated issue #{issue_number} for {rel_path}")
                else:
                    print(f"No issue changes for {rel_path} (#{issue_number})")
            else:
                created = create_issue(
                    client=client,
                    owner=gh_owner,
                    repo=gh_repo,
                    title=title,
                    body=issue_body,
                    labels=labels,
                )
                issue_number = created["number"]
                issue_node_id = created["node_id"]
                existing = created
                print(f"Created issue #{issue_number} for {rel_path}")

            existing_issues_by_path[rel_path] = existing
            if stable_task_key:
                existing_issues_by_stable_key[stable_task_key] = existing

            item_id = project_item_map.get(issue_node_id)
            if not item_id:
                try:
                    item_id = add_issue_to_project(client, project_id, issue_node_id)
                    print(f"Added issue #{existing['number']} to project")
                except GitHubError as exc:
                    # Race-safe recovery for "already exists in project".
                    if "already exists" in str(exc).lower():
                        project_item_map = fetch_project_issue_item_map(client, project_id)
                        item_id = project_item_map.get(issue_node_id)
                    else:
                        raise
                if not item_id:
                    raise GitHubError("Issue is in project but item id was not found.")
                project_item_map[issue_node_id] = item_id

            for field_name, metadata_key in (("Status", "status"), ("Priority", "priority")):
                if metadata_key not in metadata:
                    continue
                field = project_fields.get(canonicalize(field_name))
                if not field:
                    warn(f"[{rel_path}] Project field '{field_name}' not found; skipping.")
                    continue
                option_id = pick_option_id(field, metadata.get(metadata_key))
                if not option_id:
                    warn(
                        f"[{rel_path}] Option '{metadata.get(metadata_key)}' "
                        f"not found in '{field_name}'; skipping."
                    )
                    continue
                try:
                    update_single_select_field(
                        client=client,
                        project_id=project_id,
                        item_id=item_id,
                        field_id=field.field_id,
                        option_id=option_id,
                    )
                except GitHubError as exc:
                    warn(f"[{rel_path}] Failed to set {field_name}: {exc}")

            synced_count += 1
        except Exception as exc:  # noqa: BLE001 - continue processing remaining tasks
            failed_count += 1
            warn(f"[{rel_path}] Failed to sync task: {exc}")
            continue

    print(f"Synced {synced_count} tasks.")
    print(
        f"Summary: skipped={skipped_count} failed={failed_count} warnings={warning_count}"
    )

    fail_on_errors = os.environ.get("FAIL_ON_TASK_ERRORS", "0").strip() == "1"
    if fail_on_errors and failed_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
