# Setup decisions

Ask only what inspection and conversation do not establish. Resolve one question at a time, giving a recommended answer and its effect. The user can revise any default.

1. **Target and goal:** Which agent/version is optimized, and what observable task outcome matters? Define success and excluded behavior.
2. **Evidence:** Which source is ground truth? What are the fixed train and eval datasets, unit of evaluation, labels, hashes, and review status? Is a separate holdout needed? Keep development examples out of a final holdout.
3. **Metric contract:** What individual components are scored, their range and direction, aggregation, minimum improvement, and tie rule? Define failure records detailed enough to explain a miss. Specify a separate aggregation script and which training components it accepts. Eval reports the components but cannot select a parent unless the user explicitly changes the campaign's data roles.
4. **Mutation surface:** Which exact per-iteration files or fields may change? Ask separately about prompt, structured-output schema, backend, model, tool access, and generation settings when relevant. Everything else is fixed for a comparable campaign.
5. **Runner and access:** Which invocation is repeatable, with what model, batch settings, fresh-session isolation, data access, caching, and output validation? Which calls incur separate charges? Where are credentials loaded without recording them?
6. **Lifecycle:** Should the current best scored training run always be the parent? What evidence and hypothesis must precede a child? Where do iterations, analyses, raw runs, metrics, and best pointer live? What is the stopping rule or budget?
7. **Evaluation and promotion:** When may eval be run, who sees its detailed cases, how is a selected version promoted, and what happens if the fixed contract changes?

Recommended starting contract, when the user has not chosen otherwise: maximize a declared mean of training metrics; ties keep the earlier iteration; require one actual training failure and a written hypothesis before a child; allow only prompt edits; evaluate on a fixed split only after choosing a candidate; keep a final holdout sealed; freeze scored iterations and record hashes. These are recommendations, not automatic overrides of existing project decisions.

After resolving the decisions, write the policy, skill, fixed metric/scorer contract, runner, and directory structure. Validate policy structure and path containment, verify dataset counts and hashes, run integrity checks and a scorer dry-run without model calls, and report precise readiness. A future session should be able to execute the campaign using the skill and files alone.
