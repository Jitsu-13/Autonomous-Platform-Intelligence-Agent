"""
Seed capabilities for Linear — a minimal starting set, not exhaustive.
The agent synthesizes additional capabilities at runtime.
These are registered into capability memory on boot.
"""

from agent.memory.capability_store import Capability, register_capability

# --- GraphQL templates (not hard-coded handlers — the agent uses these as building blocks) ---

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
mutation CreateIssue($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier title url state { name } priority }
  }
}
"""

GQL_UPDATE_ISSUE = """
mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
  issueUpdate(id: $id, input: $input) {
    success
    issue { id identifier title state { name } priority assignee { name } }
  }
}
"""

GQL_GET_WORKFLOW_STATES = """
query GetWorkflowStates($teamId: String!) {
  workflowStates(filter: { team: { id: { eq: $teamId } } }) {
    nodes { id name type color position }
  }
}
"""

GQL_GET_USERS = """
query GetUsers {
  users { nodes { id name email active } }
}
"""

GQL_GET_LABELS = """
query GetLabels($teamId: String) {
  issueLabels(filter: { team: { id: { eq: $teamId } } }) {
    nodes { id name color }
  }
}
"""

GQL_GET_CYCLES = """
query GetCycles($teamId: String!) {
  cycles(filter: { team: { id: { eq: $teamId } } }) {
    nodes { id name number startsAt endsAt completedAt }
  }
}
"""

GQL_CREATE_COMMENT = """
mutation CreateComment($input: CommentCreateInput!) {
  commentCreate(input: $input) {
    success
    comment { id body createdAt }
  }
}
"""

GQL_GET_PROJECTS = """
query GetProjects($teamId: String) {
  projects(filter: { accessibleTeams: { id: { eq: $teamId } } }) {
    nodes { id name description state url }
  }
}
"""


SEED_CAPABILITIES: list[Capability] = [
    Capability(
        name="get_viewer",
        description="Get the authenticated user's identity",
        operation_type="graphql_query",
        implementation=GQL_GET_VIEWER,
    ),
    Capability(
        name="get_teams",
        description="List all Linear teams accessible to the API key",
        operation_type="graphql_query",
        implementation=GQL_GET_TEAMS,
    ),
    Capability(
        name="get_issues",
        description="Fetch issues with optional filters (state, priority, assignee, label, cycle)",
        operation_type="graphql_query",
        implementation=GQL_GET_ISSUES,
    ),
    Capability(
        name="create_issue",
        description="Create a new issue in a team with title, description, priority, state, and labels",
        operation_type="graphql_mutation",
        implementation=GQL_CREATE_ISSUE,
    ),
    Capability(
        name="update_issue",
        description="Update an existing issue's fields (title, description, state, priority, assignee, labels)",
        operation_type="graphql_mutation",
        implementation=GQL_UPDATE_ISSUE,
    ),
    Capability(
        name="get_workflow_states",
        description="Get all workflow states for a team (triage, todo, in-progress, done, etc.)",
        operation_type="graphql_query",
        implementation=GQL_GET_WORKFLOW_STATES,
    ),
    Capability(
        name="get_users",
        description="List all workspace users with id, name, email",
        operation_type="graphql_query",
        implementation=GQL_GET_USERS,
    ),
    Capability(
        name="get_labels",
        description="List all issue labels available in a team",
        operation_type="graphql_query",
        implementation=GQL_GET_LABELS,
    ),
    Capability(
        name="get_cycles",
        description="List all cycles (sprints) for a team",
        operation_type="graphql_query",
        implementation=GQL_GET_CYCLES,
    ),
    Capability(
        name="create_comment",
        description="Add a comment to an existing issue",
        operation_type="graphql_mutation",
        implementation=GQL_CREATE_COMMENT,
    ),
    Capability(
        name="get_projects",
        description="List projects for a team",
        operation_type="graphql_query",
        implementation=GQL_GET_PROJECTS,
    ),
]


def seed_capabilities() -> None:
    """Register seed capabilities into capability memory. Idempotent."""
    for cap in SEED_CAPABILITIES:
        register_capability(cap)
