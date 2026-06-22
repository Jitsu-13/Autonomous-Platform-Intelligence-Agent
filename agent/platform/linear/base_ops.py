"""
Seed capabilities for Linear — a minimal starting set, not exhaustive.
The agent synthesizes additional capabilities at runtime.
These are registered into capability memory on boot.
"""

from agent.memory.capability_store import Capability, register_capability

# --- GraphQL templates ---

GQL_GET_VIEWER = """
query GetViewer {
  viewer { id name email }
}
"""

GQL_GET_TEAMS = """
query GetTeams {
  teams { nodes { id name key description } }
}
"""

# Targeted: unassigned open issues in a team (backlog/todo/in-progress, no assignee)
GQL_GET_UNASSIGNED_OPEN_ISSUES = """
query GetUnassignedOpenIssues($teamId: ID!, $first: Int) {
  issues(filter: {
    team: { id: { eq: $teamId } }
    assignee: { null: true }
    state: { type: { in: ["backlog", "unstarted", "started"] } }
  }, first: $first) {
    nodes {
      id identifier title priority
      state { name type }
      labels { nodes { id name } }
      createdAt updatedAt
    }
  }
}
"""

# Targeted: all issues inside a specific cycle
GQL_GET_CYCLE_ISSUES = """
query GetCycleIssues($cycleId: String!, $first: Int) {
  issues(filter: {
    cycle: { id: { eq: $cycleId } }
  }, first: $first) {
    nodes {
      id identifier title priority
      assignee { id name }
      state { name type }
      labels { nodes { id name } }
      createdAt updatedAt
    }
  }
}
"""

# Targeted: backlog issues not assigned to any cycle
GQL_GET_BACKLOG_ISSUES = """
query GetBacklogIssues($teamId: ID!, $first: Int) {
  issues(filter: {
    team: { id: { eq: $teamId } }
    cycle: { null: true }
    state: { type: { in: ["backlog", "unstarted", "started"] } }
  }, first: $first) {
    nodes {
      id identifier title priority
      assignee { id name }
      state { name type }
      labels { nodes { id name } }
      createdAt updatedAt
    }
  }
}
"""

GQL_CREATE_ISSUE = """
mutation CreateIssue(
  $teamId: String!
  $title: String!
  $description: String
  $priority: Int
  $stateId: String
  $labelIds: [String!]
  $assigneeId: String
  $cycleId: String
) {
  issueCreate(input: {
    teamId: $teamId
    title: $title
    description: $description
    priority: $priority
    stateId: $stateId
    labelIds: $labelIds
    assigneeId: $assigneeId
    cycleId: $cycleId
  }) {
    success
    issue { id identifier title url state { name } priority }
  }
}
"""

GQL_UPDATE_ISSUE = """
mutation UpdateIssue(
  $id: String!
  $title: String
  $description: String
  $priority: Int
  $stateId: String
  $labelIds: [String!]
  $assigneeId: String
) {
  issueUpdate(id: $id, input: {
    title: $title
    description: $description
    priority: $priority
    stateId: $stateId
    labelIds: $labelIds
    assigneeId: $assigneeId
  }) {
    success
    issue { id identifier title state { name } priority assignee { name } }
  }
}
"""

GQL_GET_WORKFLOW_STATES = """
query GetWorkflowStates($teamId: ID!) {
  workflowStates(filter: { team: { id: { eq: $teamId } } }) {
    nodes { id name type color position }
  }
}
"""

# Targeted: find a single state by its type keyword (backlog/unstarted/started/completed/cancelled/triage)
GQL_GET_STATE_BY_TYPE = """
query GetStateByType($teamId: ID!, $type: String!) {
  workflowStates(filter: { team: { id: { eq: $teamId } }, type: { eq: $type } }) {
    nodes { id name type }
  }
}
"""

GQL_GET_USERS = """
query GetUsers {
  users { nodes { id name email active } }
}
"""

GQL_GET_LABELS = """
query GetLabels {
  issueLabels(first: 50) {
    nodes { id name color }
  }
}
"""

# Targeted: find a single label by name — workspace-level, no teamId needed
GQL_GET_LABEL_BY_NAME = """
query GetLabelByName($name: String!) {
  issueLabels(filter: { name: { containsIgnoreCase: $name } }) {
    nodes { id name color }
  }
}
"""

GQL_GET_CYCLES = """
query GetCycles($teamId: ID!) {
  cycles(filter: { team: { id: { eq: $teamId } } }) {
    nodes { id name number startsAt endsAt completedAt }
  }
}
"""

GQL_CREATE_COMMENT = """
mutation CreateComment($issueId: String!, $body: String!) {
  commentCreate(input: { issueId: $issueId, body: $body }) {
    success
    comment { id body createdAt }
  }
}
"""

GQL_GET_PROJECTS = """
query GetProjects($teamId: ID) {
  projects(filter: { accessibleTeams: { id: { eq: $teamId } } }) {
    nodes { id name description state url }
  }
}
"""

_COMPOSITE_TRIAGE_SUMMARY = '''
_PRIORITY_LABELS = {0: "No Priority", 1: "Urgent", 2: "High", 3: "Medium", 4: "Low"}
_PRIORITY_ORDER = [1, 2, 3, 4, 0]

_GQL_CREATE = """
mutation CreateTriageSummary(
  $teamId: String!
  $title: String!
  $description: String!
  $priority: Int!
) {
  issueCreate(input: {
    teamId: $teamId
    title: $title
    description: $description
    priority: $priority
  }) { success issue { id identifier title url } }
}
"""

def execute(client, params):
    team_id = params.get("teamId") or params.get("team_id", "")
    issues = params.get("issues_data") or []

    if not team_id:
        raise ValueError("teamId is required")

    grouped = {}
    for issue in issues:
        p = issue.get("priority", 0) if isinstance(issue, dict) else 0
        grouped.setdefault(p, []).append(issue)

    total = len(issues)
    lines = [
        f"## Triage Report: {total} Unassigned Open Issues",
        "",
        "| Priority | Count |",
        "|----------|-------|",
    ]
    for p in _PRIORITY_ORDER:
        if p in grouped:
            lines.append(f"| {_PRIORITY_LABELS[p]} | {len(grouped[p])} |")

    for p in _PRIORITY_ORDER:
        if p not in grouped:
            continue
        lines.append("")
        lines.append(f"### {_PRIORITY_LABELS[p]} ({len(grouped[p])})")
        for iss in grouped[p]:
            if not isinstance(iss, dict):
                continue
            identifier = iss.get("identifier", "")
            title = iss.get("title", "untitled")
            state = (iss.get("state") or {}).get("name", "")
            label_nodes = (iss.get("labels") or {}).get("nodes", [])
            labels = ", ".join(l["name"] for l in label_nodes if isinstance(l, dict))
            label_str = f" `{labels}`" if labels else ""
            lines.append(f"- **{identifier}**: {title} - _{state}_{label_str}")

    lines.extend(["", "*Auto-generated by Autonomous Linear Agent*"])
    description = "\\n".join(lines)

    return client.execute(_GQL_CREATE, {
        "teamId": team_id,
        "title": f"[Triage] {total} Unassigned Issues Need Assignment",
        "description": description,
        "priority": 2,
    })
'''


SEED_CAPABILITIES: list[Capability] = [
    Capability(
        name="get_viewer",
        description=(
            "Get the authenticated user's identity. "
            "Returns: {viewer: {id, name, email}}. "
            "Placeholder: <<stepN.viewer.id>>"
        ),
        operation_type="graphql_query",
        implementation=GQL_GET_VIEWER,
    ),
    Capability(
        name="get_teams",
        description=(
            "List all Linear teams. No params needed. "
            "Returns: {teams: {nodes: [{id, name, key}]}}. "
            "Placeholder for first team id: <<stepN.teams.nodes.0.id>>"
        ),
        operation_type="graphql_query",
        implementation=GQL_GET_TEAMS,
    ),
    Capability(
        name="get_unassigned_open_issues",
        description=(
            "Fetch open issues (backlog/todo/in-progress) with NO assignee in a team. "
            "Params: teamId (ID! — required), first (Int — optional, default 50). "
            "Returns: {issues: {nodes: [{id, identifier, title, priority, state, labels, createdAt, updatedAt}]}}. "
            "Placeholder for first issue id: <<stepN.issues.nodes.0.id>>. "
            "Use this for triage queries — finding unassigned work."
        ),
        operation_type="graphql_query",
        implementation=GQL_GET_UNASSIGNED_OPEN_ISSUES,
    ),
    Capability(
        name="get_cycle_issues",
        description=(
            "Fetch all issues inside a specific cycle (sprint). "
            "Params: cycleId (String! — required), first (Int — optional). "
            "Returns: {issues: {nodes: [{id, identifier, title, priority, assignee, state, labels}]}}. "
            "Placeholder for first issue id: <<stepN.issues.nodes.0.id>>. "
            "Use this when the instruction mentions 'current cycle', 'current sprint', or 'sprint issues'."
        ),
        operation_type="graphql_query",
        implementation=GQL_GET_CYCLE_ISSUES,
    ),
    Capability(
        name="get_backlog_issues",
        description=(
            "Fetch open issues in a team's backlog (not assigned to any cycle). "
            "Params: teamId (ID! — required), first (Int — optional). "
            "Returns: {issues: {nodes: [{id, identifier, title, priority, assignee, state, labels, createdAt}]}}. "
            "Placeholder for first issue id: <<stepN.issues.nodes.0.id>>. "
            "Use this for backlog health analysis or backlog debt reports."
        ),
        operation_type="graphql_query",
        implementation=GQL_GET_BACKLOG_ISSUES,
    ),
    Capability(
        name="create_issue",
        description=(
            "Create a new Linear issue. "
            "Params: teamId (String! — required), title (String! — required), description (String), "
            "priority (Int: 0=none 1=urgent 2=high 3=medium 4=low — MUST be integer not string), "
            "stateId (String), labelIds ([String!] — must be array of IDs), assigneeId (String), cycleId (String). "
            "Returns: {issueCreate: {success, issue: {id, identifier, title, url, state, priority}}}. "
            "Placeholder for created issue id: <<stepN.issueCreate.issue.id>>"
        ),
        operation_type="graphql_mutation",
        implementation=GQL_CREATE_ISSUE,
    ),
    Capability(
        name="update_issue",
        description=(
            "Update an existing issue. "
            "Params: id (String! — the issue UUID, required), title, description, "
            "priority (Int: 0=none 1=urgent 2=high 3=medium 4=low), stateId, labelIds ([String!]), assigneeId. "
            "Returns: {issueUpdate: {success, issue: {id, identifier, title, state, priority, assignee}}}."
        ),
        operation_type="graphql_mutation",
        implementation=GQL_UPDATE_ISSUE,
    ),
    Capability(
        name="get_workflow_states",
        description=(
            "Get ALL workflow states for a team. Params: teamId (ID! — required). "
            "Returns: {workflowStates: {nodes: [{id, name, type, color}]}}. "
            "Placeholder for first state id: <<stepN.workflowStates.nodes.0.id>>. "
            "State types: triage, backlog, unstarted, started, completed, cancelled."
        ),
        operation_type="graphql_query",
        implementation=GQL_GET_WORKFLOW_STATES,
    ),
    Capability(
        name="get_state_by_type",
        description=(
            "Find a single workflow state by its type. Params: teamId (ID! — required), "
            "type (String — one of: triage, backlog, unstarted, started, completed, cancelled). "
            "Returns: {workflowStates: {nodes: [{id, name, type}]}}. "
            "Placeholder for state id: <<stepN.workflowStates.nodes.0.id>>. "
            "Use this instead of get_workflow_states when you need a specific state type."
        ),
        operation_type="graphql_query",
        implementation=GQL_GET_STATE_BY_TYPE,
    ),
    Capability(
        name="get_users",
        description=(
            "List all workspace users. No params needed. "
            "Returns: {users: {nodes: [{id, name, email, active}]}}. "
            "Placeholder for first user id: <<stepN.users.nodes.0.id>>"
        ),
        operation_type="graphql_query",
        implementation=GQL_GET_USERS,
    ),
    Capability(
        name="get_labels",
        description=(
            "List all workspace issue labels. No params needed. "
            "Returns: {issueLabels: {nodes: [{id, name, color}]}}. "
            "Placeholder for first label id: <<stepN.issueLabels.nodes.0.id>>. "
            "Use get_label_by_name when you need a specific label by name."
        ),
        operation_type="graphql_query",
        implementation=GQL_GET_LABELS,
    ),
    Capability(
        name="get_label_by_name",
        description=(
            "Find a label by name (case-insensitive). "
            "Params: name (String! — the label name, e.g. 'Bug', 'Feature', 'High Priority'). No teamId needed. "
            "Returns: {issueLabels: {nodes: [{id, name, color}]}}. "
            "Placeholder for label id: <<stepN.issueLabels.nodes.0.id>>. "
            "Use this to get the exact label ID before passing to create_issue labelIds."
        ),
        operation_type="graphql_query",
        implementation=GQL_GET_LABEL_BY_NAME,
    ),
    Capability(
        name="get_cycles",
        description=(
            "List all cycles (sprints) for a team. Params: teamId (ID! — required). "
            "Returns: {cycles: {nodes: [{id, name, number, startsAt, endsAt, completedAt}]}}. "
            "Placeholder for first cycle id: <<stepN.cycles.nodes.0.id>>. "
            "The active cycle has completedAt=null and startsAt <= today <= endsAt."
        ),
        operation_type="graphql_query",
        implementation=GQL_GET_CYCLES,
    ),
    Capability(
        name="create_comment",
        description=(
            "Add a comment to an existing issue. "
            "Params: issueId (String! — required), body (String! — markdown supported). "
            "Returns: {commentCreate: {success, comment: {id, body, createdAt}}}."
        ),
        operation_type="graphql_mutation",
        implementation=GQL_CREATE_COMMENT,
    ),
    Capability(
        name="get_projects",
        description=(
            "List projects accessible to a team. Params: teamId (ID — optional). "
            "Returns: {projects: {nodes: [{id, name, description, state, url}]}}. "
            "Placeholder for first project id: <<stepN.projects.nodes.0.id>>"
        ),
        operation_type="graphql_query",
        implementation=GQL_GET_PROJECTS,
    ),
    Capability(
        name="create_triage_summary_issue",
        description=(
            "Group a list of issues by priority and create a formatted triage summary issue in Linear. "
            "Use this when the instruction asks to summarise, report, or create a breakdown of fetched issues. "
            "Params: teamId (String! — required), issues_data (List — the resolved issues array, "
            "e.g. <<stepN.issues.nodes>>). "
            "Returns: {issueCreate: {success, issue: {id, identifier, title, url}}}."
        ),
        operation_type="composite",
        implementation=_COMPOSITE_TRIAGE_SUMMARY,
    ),
]


def seed_capabilities() -> None:
    """Register seed capabilities into capability memory. Idempotent."""
    for cap in SEED_CAPABILITIES:
        register_capability(cap)
