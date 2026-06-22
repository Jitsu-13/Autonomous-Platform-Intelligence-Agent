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

GQL_GET_ISSUES = """
query GetIssues($filter: IssueFilter, $first: Int, $after: String) {
  issues(filter: $filter, first: $first, after: $after) {
    nodes {
      id identifier title description state { name type }
      priority assignee { id name } labels { nodes { id name } }
      createdAt updatedAt dueDate
      cycle { id name }
      team { id name key }
    }
    pageInfo { hasNextPage endCursor }
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
        name="get_issues",
        description=(
            "Fetch issues with optional IssueFilter. Params: filter (object), first (int), after (string). "
            "Returns: {issues: {nodes: [{id, identifier, title, state, priority, assignee, labels, createdAt, updatedAt, team, cycle}], pageInfo}}. "
            "Placeholder for first issue id: <<stepN.issues.nodes.0.id>>"
        ),
        operation_type="graphql_query",
        implementation=GQL_GET_ISSUES,
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
]


def seed_capabilities() -> None:
    """Register seed capabilities into capability memory. Idempotent."""
    for cap in SEED_CAPABILITIES:
        register_capability(cap)
