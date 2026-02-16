"""Shared GitHub + Projects v2 helpers for task automation scripts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import requests

API_BASE_URL = "https://api.github.com"
GRAPHQL_URL = f"{API_BASE_URL}/graphql"
DEFAULT_PROJECT_TITLE = "Juke Project"


class GitHubError(RuntimeError):
    """Raised when a GitHub API call fails."""


@dataclass
class ProjectField:
    field_id: str
    name: str
    option_by_key: dict[str, str]
    option_name_by_key: dict[str, str]


class GitHubClient:
    def __init__(self, token: str, user_agent: str = "juke-github-client") -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": user_agent,
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
            raise GitHubError(f"GraphQL HTTP {response.status_code}: {response.text[:500]}")
        payload = response.json()
        errors = payload.get("errors")
        if errors:
            message = "; ".join(error.get("message", "Unknown GraphQL error") for error in errors)
            raise GitHubError(f"GraphQL error: {message}")
        return payload.get("data", {})


def canonicalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def find_project_id(client: GitHubClient, login: str, project_title: str) -> str:
    query_user = """
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
    query_org = """
    query($login: String!, $after: String) {
      organization(login: $login) {
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

    for query, root_key in ((query_user, "user"), (query_org, "organization")):
        cursor: str | None = None
        while True:
            data = client.graphql(query, {"login": login, "after": cursor})
            container = data.get(root_key)
            if not isinstance(container, dict):
                break

            projects = container.get("projectsV2", {})
            for node in projects.get("nodes", []):
                if node.get("title") == project_title and isinstance(node.get("id"), str):
                    return node["id"]

            page_info = projects.get("pageInfo", {})
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if not cursor:
                break

    raise GitHubError(
        f'Could not find project titled "{project_title}" for owner "{login}".'
    )


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

            option_by_key: dict[str, str] = {}
            option_name_by_key: dict[str, str] = {}
            for option in node.get("options", []):
                option_name = option.get("name")
                option_id = option.get("id")
                if not isinstance(option_name, str) or not isinstance(option_id, str):
                    continue
                option_key = canonicalize(option_name)
                option_by_key[option_key] = option_id
                option_name_by_key[option_key] = option_name

            fields[canonicalize(name)] = ProjectField(
                field_id=field_id,
                name=name,
                option_by_key=option_by_key,
                option_name_by_key=option_name_by_key,
            )

        page_info = fields_connection.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break

    return fields


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
        items = data.get("node", {}).get("items", {})
        for node in items.get("nodes", []):
            content = node.get("content")
            if not isinstance(content, dict) or content.get("__typename") != "Issue":
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
    item_id = data.get("addProjectV2ItemById", {}).get("item", {}).get("id")
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


def available_options(field: ProjectField) -> str:
    names = sorted(field.option_name_by_key.values())
    return ", ".join(names) if names else "(none)"


def option_aliases(field_name: str, value_key: str) -> list[str]:
    if field_name == canonicalize("Status"):
        status_aliases: dict[str, list[str]] = {
            canonicalize("ready"): [
                canonicalize("todo"),
                canonicalize("to do"),
                canonicalize("backlog"),
                canonicalize("not started"),
            ],
            canonicalize("in_progress"): [
                canonicalize("in progress"),
                canonicalize("doing"),
                canonicalize("active"),
                canonicalize("wip"),
            ],
            canonicalize("review"): [
                canonicalize("in review"),
                canonicalize("qa"),
                canonicalize("testing"),
                canonicalize("in progress"),
            ],
            canonicalize("blocked"): [
                canonicalize("on hold"),
                canonicalize("hold"),
            ],
            canonicalize("done"): [
                canonicalize("complete"),
                canonicalize("completed"),
                canonicalize("closed"),
            ],
        }
        return status_aliases.get(value_key, [])

    if field_name == canonicalize("Priority"):
        priority_aliases: dict[str, list[str]] = {
            canonicalize("p0"): [canonicalize("critical"), canonicalize("urgent")],
            canonicalize("p1"): [canonicalize("high")],
            canonicalize("p2"): [canonicalize("medium"), canonicalize("normal")],
            canonicalize("p3"): [canonicalize("low"), canonicalize("backlog")],
        }
        return priority_aliases.get(value_key, [])

    return []


def pick_option_id(field: ProjectField, raw_value: Any) -> tuple[str | None, str | None]:
    if raw_value is None:
        return None, None
    value = str(raw_value).strip()
    if not value:
        return None, None

    value_key = canonicalize(value)
    option_id = field.option_by_key.get(value_key)
    if option_id:
        return option_id, field.option_name_by_key.get(value_key)

    for alias_key in option_aliases(canonicalize(field.name), value_key):
        option_id = field.option_by_key.get(alias_key)
        if option_id:
            return option_id, field.option_name_by_key.get(alias_key)

    return None, None
