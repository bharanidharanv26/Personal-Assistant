# Roadmap

## v0.1 — Foundation

- Isolated repository, Python package, locked dependencies and native Windows workflow.
- Authenticated local API and CLI.
- Explicit SQLite memory with FTS5 search, editing, deletion, sharing control and export.
- Demo and hosted model providers, bounded context, conversation history and structured plans.
- Persistent tasks and action-bound approval, dry-run execution, audit and recovery.
- Scoped manual-observation consent, feedback and episode/evaluation records.
- Automated boundary tests and operational documentation.

## Next milestone — Narrow browser automation

Add an optional Playwright adapter and one tightly scoped operation in a dedicated browser context. Begin with navigating to an explicitly approved URL, with a preview of the target and declared side effects. Decide URL restrictions, redirects, download handling, credential/profile isolation, cancellation and unknown-outcome recovery before broader interaction. Validate actual browser behaviour separately from the existing dry-run metrics.

## Later — Observation and retrieval

Introduce only user-selected observation sources with clear start/stop controls, expiry, retention and inspection/deletion. Add semantic retrieval only after evaluating where FTS5 misses useful memories. Assess small local models against actual device memory and latency, and keep hosted/local provider selection explicit.

## Later — Learning and greater autonomy

Build a versioned evaluation dataset from explicitly selected outcomes. Separate planning errors, tool errors and user preference mismatches. Evaluate simple preference rules or contextual-bandit policies before introducing heavier reinforcement-learning or fine-tuning frameworks. Record policy versions, measure held-out performance, and retain rollback.

Scheduled work, desktop automation, a graphical UI, additional model providers and training exports each need their own scoped implementation plan. Their presence in this roadmap does not enable them in v0.1.
