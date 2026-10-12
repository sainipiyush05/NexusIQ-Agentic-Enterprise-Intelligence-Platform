# Generation development challenges

This folder holds a small, independent development set for local generation behavior. It is separate from `evals/dev.jsonl` and `evals/holdout.jsonl`; its documents are loaded into an isolated in-memory index and never imported into the demo or PostgreSQL database.

`dev_challenges.json` contains source checksums, questions, expected behavior and labeled quotes. The three source files under `fixtures/` represent an approved policy, a conflicting unapproved draft and a malicious training example. Labels are agent-authored and still need human review. The challenge set is a diagnostic test, not a generalization benchmark.

Run `make generation-challenges` after caching the local model. The report is written to `reports/generation_challenges_dev.json`, with a human-readable interpretation in `reports/generation_challenges_dev.md`. No held-out cases are read by this command.
