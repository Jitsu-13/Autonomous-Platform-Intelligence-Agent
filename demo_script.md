# Demo Script — Autonomous Platform Intelligence Agent
# ~18-Minute Video Walkthrough

> **Before you start recording:**
> - Terminal font size: 18+ (readable in video)
> - Browser: Linear workspace open in another tab
> - Split screen: terminal on left, Linear on right (or switch between them)
> - `memory.db` already has warm runs (do NOT delete it — the improvement story depends on prior runs)
> - Run `python main.py memory` once just before — confirm 16 capabilities show up
> - Run `python test_llm.py` — confirm all [PASS]

---

## [0:00 – 1:00] Opening — The Problem (60 seconds)

> Speak to camera or narrate over a slide

**Say:**
"Most SaaS platforms are built for humans — you click, you read, you decide.
The moment you want to automate that, you're writing brittle API wrappers that break on
every update.

The harder problem isn't automation. It's intelligent automation — a system that takes a
natural language instruction, figures out how to execute it on a platform it has learned about,
remembers what it's done before, and gets measurably better over time.

That's what I built. An autonomous agent for Linear — the project management platform.
Let me show you how it works."

---

## [1:00 – 3:00] Architecture Overview (2 minutes)

> Show ARCHITECTURE.md or a quick hand-drawn diagram on screen

**Say:**
"The agent has four main components.

First — a Planner. It takes a natural language instruction and decomposes it into steps.
But crucially, the planner doesn't plan in a vacuum — it reads memory first.
It knows what worked last time, what failed, how many API calls similar tasks took.
That's how the plan changes based on experience.

Second — an Executor. It runs each step against the Linear API, resolves values from
prior steps — like passing a team ID fetched in step 0 into step 2 — and handles
partial failures without silently producing a broken result.

Third — a Capability Synthesizer. When the agent hits a task it doesn't have a tool for,
it doesn't fail. It introspects Linear's GraphQL schema, asks the LLM to write a Python
function, tests it against the real API, and if it works — registers it in memory.
Next time, it finds it immediately.

Fourth — a Learning Loop. After every run, the agent extracts structured knowledge:
what operations succeeded, which ones are risky, how long it took.
I'll show you real numbers in a moment.

Everything persists in SQLite — two layers: execution memory and capability memory.
Not logs. Structured knowledge that changes decisions.

One more thing worth calling out: none of this uses LangChain, LlamaIndex, CrewAI, or
any agent framework. Every component — the planner, executor, memory, synthesizer,
learning loop — is written from scratch in plain Python with no agent abstractions.
That was a deliberate choice. Frameworks hide the parts that matter most here:
how memory actually changes planning decisions, how synthesis gets validated before
it's trusted, how a partial failure is represented differently from a full failure.
When you build it yourself, every design decision is explicit and explainable."

> Show `python main.py memory` output briefly

```
python main.py memory
```

**Say:**
"Right now you can see 16 seed capabilities — the built-in toolkit for Linear.
Their success and failure counts update after every run.
Watch what happens after each demo instruction."

---

## [3:00 – 6:00] Code Walkthrough (3 minutes)

> Open the project in your editor. Split screen: code on left, you narrating on right.
> Move fast — one idea per file, don't read every line.

---

### Folder structure (15 seconds)

> Open the file tree and show it

```
agent/
  llm/provider.py         ← unified LLM interface, two-tier model selection
  core/
    models.py             ← pydantic: PlannedStep, ExecutionPlan, StepResult, ExecutionReport
    planner.py            ← single LLM call → structured JSON execution plan
    executor.py           ← runs steps, resolves placeholders, handles synthesis fallback
    orchestrator.py       ← top-level: planner → executor → learning loop
  memory/
    schema.py             ← 7-table SQLite schema (zero external deps)
    manager.py            ← boot(), get_planner_context() (the memory→planner bridge)
  platform/linear/
    base_ops.py           ← 16 seed capabilities: GraphQL queries + composite Python
    client.py             ← httpx wrapper around Linear GraphQL
  synthesis/
    synthesizer.py        ← gap detect → introspect → codegen → exec() test → register
  learning/
    feedback.py           ← record metrics, extract learnings, surface improvement report
main.py                   ← CLI: run / memory / improvement
requirements.txt          ← 6 deps, no agent framework
```

**Say:**
"Six packages, every boundary intentional. Let me walk through the interesting ones."

---

### 1. `requirements.txt` (15 seconds)

> Open the file

**Say:**
"Six dependencies. OpenAI, httpx, pydantic, click, rich, python-dotenv.
No LangChain. No agent framework. Everything you're about to see is custom.
That was a deliberate choice — I'll explain why in a moment."

---

### 2. `agent/llm/provider.py` (20 seconds)

> Open the file, point to the `complete()` function and the `fast` parameter

**Say:**
"Single entry point for every LLM call in the entire codebase.
The `fast` flag is the key design here — `fast=False` uses GPT-4o for planning,
where quality matters. `fast=True` uses GPT-4o-mini for synthesis, where we're
generating and testing code in a tight loop and cost matters.
One function, two models, zero duplication."

---

### 3. `agent/core/models.py` (20 seconds)

> Open the file, show the four classes

**Say:**
"Four pydantic models define the entire data contract.
`PlannedStep` has a `params` dict that contains placeholder strings.
`StepResult` has `outcome` — success, failure, or skipped — not a boolean.
`ExecutionReport` has `memory_applied`, `learnings_extracted`, `synthesized_capabilities`
as first-class fields. These aren't log messages — they're structured outputs that
drive the next run."

---

### 4. `agent/core/planner.py` (30 seconds)

> Open the file, scroll to `SYSTEM_PROMPT` — show the placeholder block and planning rules

**Say:**
"The planner is a single LLM call. The system prompt has three critical sections.

First — the placeholder syntax. `<<stepN.path.to.value>>`. The planner writes
`<<step0.teams.nodes.0.id>>` without knowing the actual UUID. The executor
resolves it at runtime. This is what lets the planner generate the full plan
in one shot before any step runs.

Second — exact paths. I explicitly tell the planner which path to use for each
capability's output, because LLMs hallucinate paths. This eliminated 80% of the
runtime errors we saw early on.

Third — planning rules. Rule 9 is particularly interesting: 'When the instruction
asks to create a summary or breakdown, use `create_triage_summary_issue`, NEVER
`create_issue` with a static description.' That rule exists because the planner
got it wrong on the first few runs — this is memory influencing the prompt."

> Scroll to `build_plan()`, show the `user_message` f-string

**Say:**
"And here — the memory context injected into every planning call.
Similar past executions, risky operations, the full capability list.
This is how memory changes behaviour — not by changing code, by changing the prompt."

---

### 5. `agent/core/executor.py` (40 seconds)

> Open the file, show `_resolve_string` first

**Say:**
"The placeholder resolver. It regex-matches `<<step0.teams.nodes.0.id>>`,
splits the path, walks the stored output dict recursively. If any node in the
path is missing — because a prior step failed — it returns the original string
unchanged. Then `_preprocess_params` strips anything still looking like
`<<...>>` before it reaches the GraphQL API.
Partial failures don't crash downstream steps. They just lose their inputs."

> Scroll to `_preprocess_params`

**Say:**
"This function handles the messiness between the planner and the API.
Priority coercion — Linear requires an integer, the planner sometimes sends a string.
LabelIds normalisation — must be a list, never a bare string.
None stripping — unresolved placeholders get dropped.
All the edge cases the planner doesn't know about, handled in one place."

> Scroll to `_postprocess_result`

**Say:**
"This one fixed a live bug. Linear was returning Frontend before Backend in the
teams list — the planner always picks `nodes[0]`. So after every `get_teams` call,
we reorder results to put the `LINEAR_TEAM_ID` team first.
The planner never needs to know this happened."

> Scroll to the synthesis fallback in `execute_step`

**Say:**
"And here — if the capability isn't found in memory, the synthesizer kicks in.
If synthesis succeeds, the step continues as if the capability was always there.
If synthesis fails, the step is marked failed and downstream steps are skipped.
No silent errors."

---

### 6. `agent/memory/schema.py` (20 seconds)

> Open the file, show the CREATE TABLE statements

**Say:**
"Seven tables, pure SQLite stdlib. Two logical layers.

Execution memory: `executions`, `execution_steps`, `execution_learnings`.
Every run stored. Every step traced. Structured learnings extracted after each run.

Capability memory: `capabilities`, `intent_patterns`, `discovered_constraints`, `task_metrics`.
The `intent_patterns` table maps instruction keywords to capability names with a success weight.
This is how the planner knows — without being told — that 'bug report' tasks use
`get_label_by_name` before `create_issue`."

---

### 7. `agent/memory/manager.py` — `get_planner_context()` (20 seconds)

> Open the file, scroll to `get_planner_context()`

**Say:**
"This is the bridge between memory and planning. It takes the current instruction,
finds the three most similar past executions by keyword, extracts which operations
succeeded and which failed, flags any capability with under 70% success rate as risky,
and returns a structured dict.

That dict gets injected into the planner's prompt on every single run.
This is what makes run 6 different from run 1 — not different code, different context."

---

### 8. `agent/platform/linear/base_ops.py` (20 seconds)

> Open the file, show a targeted query then `_COMPOSITE_TRIAGE_SUMMARY`

**Say:**
"Two patterns worth showing. First — targeted queries.
`get_unassigned_open_issues` takes `teamId` and `first` as scalars.
The filter logic is baked inside the GraphQL string.
Early versions had a generic `get_issues($filter: IssueFilter)` where the planner
had to construct nested comparator objects. It never got it right.
Rule: only expose scalars to the planner. Never filter objects.

Second — the composite pattern. This is Python code stored as a string.
The executor `exec()`s it at runtime. It receives the actual issues array
from the prior step, groups by priority, formats markdown, calls the API.
The issue body has real live data — not a template, not a placeholder."

---

### 9. `agent/synthesis/synthesizer.py` (20 seconds)

> Open the file, show the `synthesize_capability` function

**Say:**
"The synthesizer in five steps.
One — gap detection: if the capability isn't in memory, start synthesis.
Two — schema introspection: call Linear's GraphQL `__type` endpoint to get
the actual input types and mutations at runtime. No hardcoded schema.
Three — codegen: pass schema context to GPT-4o-mini, get back a Python
`execute(client, params)` function.
Four — test: `exec()` the code in an isolated namespace, call it with real params
against the real Linear API.
Five — register: only if the test passes. If it fails, feed the error back to the LLM
and try again, up to three attempts."

---

### 10. `agent/learning/feedback.py` (15 seconds)

> Open the file, show `record_and_learn()` and point at `get_improvement_report()`

**Say:**
"After every run, `record_and_learn` is called. It extracts structured learnings
from failed steps, updates intent patterns for successful ones, and records
api_calls and duration in `task_metrics` keyed by instruction hash.

`get_improvement_report` queries that table — you saw the output earlier.
The fuzzy match means you can type `'create a bug report'` and it finds
`'Create a bug report for the login timeout issue...'`. That's a small thing
that makes a big difference when you're demoing."

---

> Close editor, move to terminal

**Say:**
"That's the full codebase — ten files, every design decision explicit.
Let me show it running."

---

## [6:00 – 8:30] Demo 1 — Simple Instruction: Agent Core (2.5 minutes)

> Terminal: run the command live

**Type and run:**
```
python main.py run -v "Create a bug report for the login timeout issue affecting mobile users. Label it high priority."
```

> While it runs, narrate each step as it appears

**Say:**
"Step 0 — it fetches available teams. It needs a team ID to create the issue.
Notice it's not hardcoded — the agent discovers the workspace structure at runtime.

Step 1 — it fetches the 'High Priority' label by name. Labels are workspace-level in Linear,
not team-scoped — the agent learned that from prior runs.

Step 2 — creates the issue. Priority 2 (High), with the correct label ID resolved from step 1."

> Wait for report to print

**Expected output:**
```
SUCCESS  3/3 steps  3 API calls  ~7500ms

  #   Step                                  Status    API    ms    Note
  0   Retrieve list of teams                success     1   600    teams
  1   Retrieve the 'High Priority' label    success     1   600    issueLabels
  2   Create the bug report issue           success     1   700    issueCreate

Memory applied:
  • Using proven sequence of get_teams, get_label_by_name, and create_issue...
```

**Say:**
"3 API calls, under 8 seconds. Look at the Memory applied section — the planner referenced
successful prior runs to generate this exact step ordering. It knew not to fetch workflow
states or users for this kind of task.

Now let me check Linear."

> Switch to Linear browser tab
**Say:**
"There it is — created live, correct priority, correct label."

---

## [8:30 – 11:30] Demo 2 — Compound Instruction: Composite Capability + Memory (3 minutes)

> Terminal

**Type and run:**
```
python main.py run -v "Find all open issues that have no assignee, group them by priority, and create a triage summary issue with a breakdown."
```

> Narrate as steps execute

**Say:**
"Step 0 — fetches the team. Same pattern as before — team ID flows into step 1.

Step 1 — fetches open, unassigned issues using a targeted filter: no cycle filter,
no complex IssueFilter object — just scalar params. This returned 19 real issues from
the workspace.

Step 2 — here's where it gets interesting. This isn't a standard GraphQL mutation.
This is a COMPOSITE capability — a registered Python function that receives the actual
issues array from step 1 at runtime, groups them by priority level, formats a markdown
table, and creates the issue with the full breakdown embedded in the body."

> Wait for result

**Expected output:**
```
SUCCESS  3/3 steps  3 API calls  ~7800ms

Memory applied:
  • Using create_triage_summary_issue instead of create_issue to reliably generate summary.
```

**Say:**
"Notice the memory insight — the planner specifically chose `create_triage_summary_issue`
instead of `create_issue`. That's a learned decision: on a prior run, it tried the naive
approach of using `create_issue` with a static description, and the result was an empty body.
It learned. Now it always uses the composite."

> Switch to Linear browser tab
**Say:**
"Here's the triage summary issue — real data. Priority breakdown table, every unassigned issue
listed by group, with state and labels. This was generated from live Linear data, not a template."

---

## [11:30 – 14:00] Demo 3 — Capability Synthesis: Runtime Learning (2.5 minutes)

> This shows the synthesizer. The instruction should ask for something not in the seed capabilities.

**Say:**
"This is the instruction the agent might not have a built-in tool for.
Watch what happens when the planner asks for a capability that doesn't exist in memory."

**Type and run:**
```
python main.py run -v "Get the most recently created issue in the Backend team and add a comment saying it has been reviewed by the triage agent."
```

**What to watch for:**
If synthesis triggers, you will see:
```
  [Step 1] Get the most recently created issue  (capability: get_latest_issue)
    [Synthesizer] Generating 'get_latest_issue'...
    [Synthesizer] Testing generated code...
    [Synthesizer] Registered new capability.
    -> OK (2 API calls, ~3500ms)

Synthesized capabilities: get_latest_issue
```

**Say:**
"The synthesizer called Linear's GraphQL introspection endpoint — discovering available
input types for issue filtering. Then it asked GPT-4o-mini to write a Python execute()
function that implements `get_latest_issue`. Then it tested that function against the real
API. It passed — so it registered the implementation in capability memory.

On the next run of any similar instruction, the agent won't synthesize again.
It finds the cached implementation immediately."

> Run:
```
python main.py memory
```

**Say:**
"Now you can see the synthesized capability in the table, marked with a star.
The success count shows it's already been tested and validated."

> **If synthesis doesn't trigger** (planner uses existing capabilities instead):
**Say:**
"The planner solved this with existing tools — that's also a valid outcome. It composed
`get_teams`, `get_unassigned_open_issues`, and `create_comment` to accomplish the task
without needing a new capability. That's the planner doing its job: if tools exist,
use them; if not, synthesize."

---

## [14:00 – 16:30] Demo 4 — Memory Layers: What the Agent Remembers (2.5 minutes)

> Show the memory command in detail

**Run:**
```
python main.py memory
```

**Say:**
"Let me walk through this output.

The top section shows the two memory layers.
Execution Memory: every run stored — executions, steps, learnings extracted.
Capability Memory: every registered capability with live success and failure counts.

The capabilities table shows the full toolkit:
- Seed capabilities like `get_teams`, `get_label_by_name`, `create_issue` — built-in
- Composite capabilities like `create_triage_summary_issue` — Python functions
- Any synthesized capabilities marked with a star — generated at runtime

Notice the average duration column — the agent knows how long each operation typically takes.
This feeds into planning: if a step is consistently slow, the planner can deprioritise it."

> Point to intent patterns and execution count

**Say:**
"Behind this table, there's an intent_patterns table that maps instruction keywords to
capability names — built up from every successful run. When I run 'create a bug report'
for the tenth time, the planner doesn't have to figure out from scratch that it needs
get_teams and get_label_by_name. It sees the pattern immediately."

---

## [16:30 – 17:30] Demo 5 — Self-Learning Loop: Real Numbers (1 minute)

> The measurable improvement section

**Run:**
```
python main.py improvement "create a bug report"
```

**Expected output:**
```
Instruction type: create a bug report
Total runs: 9

         Run History
 Run | Outcome  | API Calls | Duration (ms)
-----+----------+-----------+--------------
   1 | partial  |         2 |         8007
   2 | partial  |         3 |         7208
   3 | partial  |         3 |         7851
   ...
   6 | success  |         3 |         8176
   7 | success  |         3 |         7772
   8 | success  |         3 |         7728
   9 | success  |         3 |         7660

 Outcome  | partial → success | improved
 Duration |           8007ms  |  7660ms  |  -347ms

The agent learned to succeed at this task (was partial on run 1, now success consistently)
```

**Say:**
"This is the learning signal. Runs 1 through 5 — partial failures. The agent hadn't yet
reinforced the correct label lookup behavior and priority encoding for this instruction type.
By run 6, with memory surfacing the proven step sequence, it produces a consistent success.
9 runs. Real data. Auditable in the SQLite database.

Now let me show the triage instruction:"

**Run:**
```
python main.py improvement "find all open issues"
```

**Say:**
"Same story — started with a partial failure at 4 API calls, now consistently 3 API calls
and 1 second faster. The improvement is real and measurable."

---

## [17:30 – 18:00] Closing (30 seconds)

**Say:**
"What I'd build next:

Multi-agent decomposition — a planner agent handing subtasks to specialist agents, running
in parallel for compound instructions.

Memory compaction — right now all executions are kept; I'd summarise them into aggregate
capability stats to keep the DB bounded as it scales.

And rollback — the agent tracks every issue it creates; wiring that into an undo command
is the natural next step.

The foundation is solid — persistent, structured memory that changes decisions,
real composite and synthesized capabilities, real learning signal. Thanks for watching."

---

## Post-Recording Checklist

- [ ] `python test_llm.py` — all [PASS] shown before recording?
- [ ] Audio clear throughout?
- [ ] Terminal text readable (font size 18+)?
- [ ] Demo 1 ran SUCCESS 3/3 steps?
- [ ] Demo 2 triage issue created in Linear with real breakdown?
- [ ] Demo 3 showed either synthesis or elegant fallback to existing capabilities?
- [ ] `python main.py memory` showed 15+ capabilities?
- [ ] Improvement numbers shown — partial → success story visible?
- [ ] Video is 14–16 minutes?

---

## Fallback Commands (if something fails live)

```bash
# If memory.db gets corrupted
python -c "from agent.memory.manager import boot; boot()"

# If a run produces an unexpected error, show the JSON output
python main.py run --json-output "Create a bug report for the timeout issue."

# Manually check what's in memory
python -c "
from agent.memory.schema import get_connection
conn = get_connection()
rows = conn.execute('SELECT task_label, run_number, outcome FROM task_metrics ORDER BY run_number').fetchall()
for r in rows: print(r)
"
```
