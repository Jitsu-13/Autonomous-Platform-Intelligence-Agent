# Architecture

## 1. What does your memory system store, and why did you structure it that way?

The memory system has two distinct SQLite layers:

**Execution Memory** stores structured knowledge extracted from every run: the instruction, its decomposition into steps, the outcome of each step (success/failure/skipped), API call counts, timing, and extracted learnings. Crucially, this is not a log — after each run the feedback module extracts structured `execution_learnings` rows (e.g. "step `get_issues` fails when `teamId` is missing") that the planner reads on the next similar instruction.

**Capability Memory** stores what the agent knows how to do: each registered capability (seed or synthesized) with its GraphQL implementation, success/failure counts, average duration, and runtime-discovered constraints (rate limits, permission boundaries, field validation rules). An `intent_patterns` table tracks which capabilities work for which instruction keywords, enabling the planner to prefer higher-success-rate operations over time.

The structure is relational (SQLite) rather than vector/embedding-based because the knowledge extracted here is structured and specific — "operation X has a 60% failure rate when param Y is absent" is better expressed as a row than as a retrieved document. The agent doesn't retrieve similar prompts; it reads structured facts that change its decisions.

## 2. How does capability synthesis work in your implementation?

When the executor encounters a capability name that isn't in memory, it calls the synthesizer:

1. **Gap detection**: The executor looks up the capability by name. If absent, synthesis begins.
2. **Schema introspection**: The synthesizer calls Linear's GraphQL introspection API to discover relevant input types and mutations matching the capability's name/description. This happens at runtime — no pre-fetched schema.
3. **Code generation**: The LLM (Claude Haiku) is prompted with the schema context and asked to write a Python `execute(client, params) -> dict` function.
4. **Testing**: The generated function is `exec()`-ed in an isolated namespace and called with the actual params against the real Linear API.
5. **Registration**: If the call succeeds, the implementation is stored in capability memory under the given name. Future runs find it immediately and skip synthesis.
6. **Failure reporting**: If synthesis fails after 3 attempts, the step is marked failed with a detailed report of what was tried and why it couldn't proceed.

The synthesis mechanism is real — not a lookup table. Each attempt uses the error from the previous attempt as feedback to the LLM.

## 3. What is your learning signal, and what does the agent do differently on run N vs run 1?

The primary learning signal is **API call count per task type**, tracked in the `task_metrics` table keyed by `intent_hash` (a fingerprint of the normalised instruction). Secondary signal is execution time.

**Run 1**: The planner has no prior context. It generates a conservative plan that may include exploratory steps (e.g. fetching teams, then fetching workflow states, then fetching users before creating an issue).

**Run N (same task type)**: The planner receives the execution history for similar instructions. It sees which steps succeeded, which failed, and what the prior API call counts were. It uses this to:

- **Skip redundant lookups**: If prior runs show that `get_workflow_states` always succeeds with the same result, the planner caches that and removes the step.
- **Reorder steps**: If a step ordering consistently causes failures, the planner tries an alternative ordering.
- **Avoid risky operations**: The `risky_operations` context shows operations with < 70% success rate; the planner routes around them or adds guard steps.
- **Use learned constraints**: Rate limit patterns and validation rules from `discovered_constraints` are surfaced, so the planner adds retry hints or correct field values.

Concrete example from demo: on the first "create triage summary" run, the agent makes 5 API calls (fetch team → fetch states → fetch issues → fetch users → create issue). By run 3, it makes 2 (fetch issues with learned filter → create issue with cached state/team IDs), because the planner learns that team and state lookups are stable and unnecessary to repeat.
