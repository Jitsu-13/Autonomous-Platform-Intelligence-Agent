# Autonomous Platform Intelligence Agent — Linear

An autonomous agent that accepts natural language instructions and executes them on Linear.
It has persistent memory, learns from every execution, and synthesises new capabilities at
runtime when it encounters tasks it hasn't seen before.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in your API keys
python test_llm.py          # verify all connections pass
```

### Required environment variables

| Variable | Description |
|---|---|
| `LLM_PROVIDER` | `openai` or `anthropic` (auto-detects from which key is present) |
| `OPENAI_API_KEY` | OpenAI key — used with `LLM_PROVIDER=openai` (GPT-4o for planning, GPT-4o-mini for synthesis) |
| `ANTHROPIC_API_KEY` | Anthropic key — used with `LLM_PROVIDER=anthropic` (Claude Sonnet for planning, Claude Haiku for synthesis) |
| `LINEAR_API_KEY` | Linear personal API key (Settings → API → Personal API keys) |
| `LINEAR_TEAM_ID` | *(optional)* Restrict to a specific team key (e.g. `BACK`) or team UUID |
| `MEMORY_DB_PATH` | *(optional)* Path to SQLite memory file (default: `./memory.db`) |

At least one of `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` is required.

## Usage

```bash
# Run an instruction
python main.py run "Create a bug report for the login timeout issue affecting mobile users. Label it high priority."

# Compound instruction with live breakdown
python main.py run "Find all open issues that have no assignee, group them by priority, and create a triage summary issue with a breakdown."

# Verbose mode (shows each step as it executes)
python main.py run -v "your instruction"

# JSON output
python main.py run --json-output "your instruction"

# Inspect memory state and capability table
python main.py memory

# Show learning improvement for a type of task (accepts a keyword or exact instruction)
python main.py improvement "create a bug report"
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md).

## How it works

```
Natural language instruction
        │
        ▼
  ┌─────────────┐      ┌──────────────────────────────┐
  │   Planner   │◄─────│  Memory Context               │
  │ (OpenAI /   │      │  • Past similar executions    │
  │  Anthropic) │      │  • Capability success rates   │
  └──────┬──────┘      │  • Discovered constraints      │
         │             └──────────────────────────────┘
         ▼
  ExecutionPlan
  (ordered steps, placeholder refs)
         │
         ▼
  ┌─────────────┐      ┌──────────────────────────────┐
  │  Executor   │─────►│  Capability Synthesizer       │
  │             │      │  (when capability unknown)    │
  └──────┬──────┘      └──────────────────────────────┘
         │
         ▼
  ┌─────────────┐
  │  Learning   │  ← records metrics, extracts learnings,
  │  Feedback   │    updates success rates, persists
  └──────┬──────┘
         │
         ▼
  ExecutionReport
  (structured output)
```

## Memory layers

**Execution Memory** (`executions`, `execution_steps`, `execution_learnings` tables)
Stores what was done, what worked, timing, and structured learnings extracted from each run.

**Capability Memory** (`capabilities`, `discovered_constraints`, `intent_patterns` tables)
Stores registered capabilities (seed + synthesized), success rates per operation, runtime-discovered
constraints (rate limits, validation rules, permission boundaries), and intent → capability mappings.

## Seed capabilities (16 built-in)

| Capability | Type | Description |
|---|---|---|
| `get_teams` | graphql_query | List all Linear teams |
| `get_viewer` | graphql_query | Get authenticated user identity |
| `get_users` | graphql_query | List workspace users |
| `get_labels` | graphql_query | List all workspace issue labels |
| `get_label_by_name` | graphql_query | Find a label by name (case-insensitive) |
| `get_workflow_states` | graphql_query | All workflow states for a team |
| `get_state_by_type` | graphql_query | Single workflow state by type (backlog, started, etc.) |
| `get_cycles` | graphql_query | List cycles (sprints) for a team |
| `get_projects` | graphql_query | List projects accessible to a team |
| `get_unassigned_open_issues` | graphql_query | Open issues with no assignee in a team |
| `get_cycle_issues` | graphql_query | All issues inside a specific cycle |
| `get_backlog_issues` | graphql_query | Open issues not assigned to any cycle |
| `create_issue` | graphql_mutation | Create a new Linear issue |
| `update_issue` | graphql_mutation | Update an existing issue |
| `create_comment` | graphql_mutation | Add a comment to an issue |
| `create_triage_summary_issue` | composite | Group issues by priority and create a formatted summary issue |
