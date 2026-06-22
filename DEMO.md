# Demo Instructions

Three instructions of increasing complexity, run live on the walkthrough call.

---

## Instruction 1 — Simple: Create a bug report

```
Create a bug report for the login timeout issue affecting mobile users.
Label it as high priority and assign it to the backend team.
```

**What the agent does:**
1. Fetches available teams to resolve "backend team" to a Linear team ID
2. Fetches workflow states to find the correct "Triage" or "Todo" state
3. Fetches labels to find or confirm a "Bug" label
4. Creates the issue with title, description, priority=1 (urgent), and label
5. Returns a structured report with the created issue URL

**What to observe:**
- Structured execution report with each step's outcome
- Memory state before/after: new execution record + step success rates updated

---

## Instruction 2 — Compound: Triage unassigned issues

```
Find all open issues in the current cycle that have no assignee,
group them by priority, and create a triage summary issue with a
breakdown table and recommended next actions.
```

**What the agent does:**
1. Fetches the active cycle for the team
2. Queries all open, unassigned issues in that cycle
3. Groups issues by priority level (urgent / high / medium / low)
4. Synthesises a markdown table with counts and issue identifiers per group
5. Creates a new "Triage Summary" issue with the breakdown and recommended owners

**What to observe:**
- Multi-step decomposition with data flowing between steps (cycle ID → issue query → summary creation)
- Memory context from Instruction 1 already present: team/state lookups skip or reuse prior results
- Partial failure handling: if the cycle fetch fails, the agent falls back to all open issues and notes the degradation in the report

---

## Instruction 3 — Novel (requires capability synthesis): Backlog health report

```
Analyze our backlog health: calculate the ratio of bugs to features
in the backlog, identify all issues that have been open for more than
30 days with no comments or updates, and generate a backlog debt report
issue with a severity score and recommended actions for each stale item.
```

**What the agent does:**
1. Plans steps including `calculate_backlog_ratio` and `find_stale_issues` — capabilities that don't exist in the seed set
2. **Synthesis triggered**: For `calculate_backlog_ratio`, the synthesizer introspects Linear's schema, generates a Python function that queries issues with label-type filters and computes the ratio, tests it, and registers it
3. **Synthesis triggered**: For `find_stale_issues`, the synthesizer generates a function that filters by `updatedAt < 30 days ago` and no `comments`, tests it, and registers it
4. Executes both synthesized capabilities with real API calls
5. Generates a severity-scored report and creates the backlog debt issue

**What to observe:**
- Live capability synthesis: watch the agent generate, test, and register two new capabilities
- After the run: `python main.py memory` shows the synthesized capabilities (marked ★) with their implementations
- **Learning improvement**: `python main.py improvement "analyze backlog"` shows run 1 vs run 3 API call counts, demonstrating the synthesized capabilities being reused from memory on subsequent runs rather than re-synthesized
