# NexusIQ 04A.3 — development quote-selection evaluation

The pinned local Qwen2.5-0.5B-Instruct model was evaluated on 13 fixed development cases with the benchmark dense index and top five candidates. The sample covers direct facts, paraphrases, exceptions, authorization, exact identifiers, multi-source questions and three unsupported questions. The case IDs and SHA-256 values are in `generation_sample_dev.json`. Held-out cases were not scored.

| Measure | Result |
| --- | ---: |
| Development cases | 13 |
| Invalid outputs rejected by validator | 8 |
| Provider failures | 0 |
| Mean labeled fact coverage, 10 answerable cases | 0.25 |
| Mean labeled claim precision, answered cases with claims | 0.3333 |
| Deliberate abstention, 3 unsupported cases | 0 / 3 |
| Strict evidence-selection proxy passes | 0 / 13 |
| Median end-to-end latency | 19.86 s |

The eight invalid outputs returned no claims and are recorded as failures, not successful abstentions. Two unsupported questions produced irrelevant cited quotes; the third produced invalid output. The three multi-source cases all failed validation. In each of the three answerable cases with claims, one claim matched labeled evidence and two did not; the exact-identifier case covered only one of its two labeled facts.

The proxy requires every labeled evidence fact to appear in a cited quote and every emitted claim to match a label. It measures evidence selection only. A valid exact quote can still be irrelevant, incomplete or misleading, and an unlabeled but useful quote can be marked irrelevant. Labels remain draft and await human review. The main development split has no conflict or adversarial cases; a separate isolated diagnostic was added in `generation_challenges_dev.md`. No semantic citation verification or natural-language answer correctness was assessed.

Run `make generation-eval` to reproduce this fixed sample offline. `PYTHONPATH=src .venv/bin/python -m nexusiq generation-eval --all-dev` is available for the complete 105-case development split; it was not run for this report. The small model remains experimental. Next, add development conflict and adversarial cases without using the held-out labels, and compare a stronger local model or a stricter selection method before promoting generation.
