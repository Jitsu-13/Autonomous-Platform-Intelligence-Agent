# Architecture

## 1. What does your memory system store, and why did you structure it that way?

The memory system has two distinct SQLite layers:

**Execution Memory** stores structured knowledge extracted from every run: the instruction,
its decomposition into steps, the outcome of each step (success/failure/skipped), API call counts,
timing, and extracted learnings. Crucially, this is not a log — after each run the feedback module
extracts structured `execution_learnings` rows (e.g. "step `get_label_by_name` failed when `teamId`
was provided — labels are workspace-level") that the planner reads on the next similar instruction.

**Capability Memory** stores what the agent knows how to do: each registered capability (seed or
synthesized) with its GraphQL/Python implementation, success/failure counts, average duration, and
runtime-discovered constraints (rate limits, permission boundaries, field validation rules).
An `intent_patterns` table tracks which capabilities work for which instruction keywords, enabling
the planner to prefer higher-success-rate operations over time.

The structure is relational (SQLite) rather than vector/embedding-based because the knowledge
extracted here is structured and specific — "operation X has a 60% failure rate when param Y is
absent" is better expressed as a row than as a retrieved document. The agent doesn't retrieve
similar prompts; it reads structured facts that change its decisions.

## 2. How does capability synthesis work in your implementation?

When the executor encounters a capability name that isn't in memory, it calls the synthesizer:

1. **Gap detection**: The executor looks up the capability by name. If absent, synthesis begins.
2. **Schema introspection**: The synthesizer calls Linear's GraphQL introspection API to discover
   relevant input types and mutations matching the capability's name/description. This happens at
   runtime — no pre-fetched schema.
3. **Code generation**: The LLM (GPT-4o-mini with `LLM_PROVIDER=openai`, or Claude Haiku with
   `LLM_PROVIDER=anthropic`) is prompted with the schema context and asked to write a Python
   `execute(client, params) -> dict` function.
4. **Testing**: The generated function is `exec()`-ed in an isolated namespace and called with
   the actual params against the real Linear API.
5. **Registration**: If the call succeeds, the implementation is stored in capability memory under
   the given name. Future runs find it immediately and skip synthesis entirely.
6. **Failure reporting**: If synthesis fails after 3 attempts, the step is marked failed with a
   detailed report of what was tried and why it couldn't proceed.

The synthesis mechanism is real — not a lookup table. Each attempt uses the error from the
previous attempt as feedback to the LLM.

**Composite capabilities** are a related concept: pre-registered Python functions that receive
resolved runtime data (e.g. the full list of issues from a prior step) and operate on it.
`create_triage_summary_issue` is an example — it groups issues by priority and creates a
formatted markdown breakdown, which is impossible with a plain GraphQL mutation that receives
only static parameters.

## 3. What is your learning signal, and what does the agent do differently on run N vs run 1?

The primary learning signal is **outcome progression per task type**, tracked in the `task_metrics`
table keyed by `intent_hash` (a fingerprint of the normalised instruction). Secondary signals are
API call count and execution time. The `python main.py improvement <keyword>` command surfaces this.

**Run 1**: The planner has no prior context. It generates a plan without knowing which capabilities
work in this workspace or which step sequences are reliable. The result may be a partial failure
if a parameter is wrong or a filter is structured incorrectly.

**Run N (same task type)**: The planner receives the execution history for similar instructions
in its context. It reads which steps succeeded, which failed, and what memory insights were
recorded. It uses this to:

- **Avoid failed capability sequences**: If prior runs show that a specific step failed repeatedly,
  the planner routes around it or substitutes a proven alternative.
- **Prefer validated step orderings**: Successful prior runs are surfaced as examples the planner
  can follow directly, reducing planning uncertainty.
- **Use correct composite capabilities**: After run 1 of a triage-style task, the planner learns
  to use `create_triage_summary_issue` (which embeds live data into the issue body) instead of
  `create_issue` with a static description.
- **Avoid risky operations**: The `risky_operations` context shows capabilities with < 70%
  success rate; the planner routes around them when alternatives exist.

**Concrete example from real runs:**

```
"Create a bug report for the login timeout issue..."

Run 1:  partial  (2 API calls, 8007ms)   ← label lookup or priority encoding failed
Run 2:  partial  (3 API calls, 7208ms)   ← still learning correct sequence
Run 5:  partial  (2 API calls, 9977ms)
Run 6:  success  (3 API calls, 8176ms)   ← memory reinforced correct step ordering
Run 7:  success  (3 API calls, 7772ms)
Run 9:  success  (3 API calls, 7660ms)   ← stable, -347ms faster than run 1
```

The agent went from partial failures to 100% success on the same instruction type.
The improvement report (run `python main.py improvement "create a bug report"`) shows
this journey with the text: *"The agent learned to succeed at this task."*

## 4. Capability design: why targeted queries instead of generic filters?

Early versions used a generic `get_issues($filter: IssueFilter)` capability where the planner
was expected to construct a nested filter object like `{team: {id: {eq: "uuid"}}}`. This always
failed because the planner cannot reliably construct GraphQL `IDComparator` nested objects.

The fix: replace every generic filter capability with **targeted scalar-param queries** where
filter logic is baked into the GraphQL template and only scalar values (ID, String, Int) are
exposed as variables. The planner only passes values, never constructs objects.

| Removed | Reason | Replacement |
|---|---|---|
| `get_issues($filter: IssueFilter)` | Planner can't construct IDComparator objects | `get_unassigned_open_issues(teamId, first)` |
| — | — | `get_cycle_issues(cycleId, first)` |
| — | — | `get_backlog_issues(teamId, first)` |

This principle generalises: all capabilities in this codebase expose only scalar variables.
Complex filter/input objects are built inside the GraphQL template string, not by the planner.
