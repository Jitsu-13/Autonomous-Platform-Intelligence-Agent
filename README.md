# Autonomous Platform Intelligence Agent — Linear

An autonomous agent that accepts natural language instructions and executes them on Linear. It has persistent memory, learns from every execution, and synthesises new capabilities at runtime when it encounters tasks it hasn't seen before.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # fill in your API keys
```

### Required environment variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key |
| `LINEAR_API_KEY` | Linear personal API key (Settings → API → Personal API keys) |
| `LINEAR_TEAM_ID` | *(optional)* Restrict to a specific team ID |
| `MEMORY_DB_PATH` | *(optional)* Path to SQLite memory file (default: `./memory.db`) |

## Usage

```bash
# Run an instruction
python main.py run "create a bug report for the login timeout issue, label it high priority"

# Compound instruction
python main.py run "find all unassigned open issues, group by priority, and create a triage summary issue"

# Verbose mode (shows each step as it executes)
python main.py run -v "your instruction"

# JSON output
python main.py run -j "your instruction"

# Inspect memory state
python main.py memory

# Show learning improvement for a type of task
python main.py improvement "create a bug report"
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md).

## Demo scenarios

See [DEMO.md](DEMO.md).

## How it works

```
Natural language instruction
        │
        ▼
  ┌─────────────┐      ┌──────────────────────────────┐
  │   Planner   │◄─────│  Memory Context               │
  │  (Claude)   │      │  • Past similar executions    │
  └──────┬──────┘      │  • Capability success rates   │
         │             │  • Discovered constraints      │
         ▼             └──────────────────────────────┘
  ExecutionPlan
  (ordered steps)
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
Stores registered capabilities (seed + synthesized), success rates per operation, runtime-discovered constraints (rate limits, validation rules, permission boundaries), and intent → capability mappings.
