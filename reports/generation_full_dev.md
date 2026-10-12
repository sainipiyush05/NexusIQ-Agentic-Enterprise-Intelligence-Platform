# NexusIQ 04A.3 — full development generation evaluation

The cached `Qwen/Qwen2.5-0.5B-Instruct` model at revision `7ae557604adf67be50417f59c2c2f167def9a775` was run against **all 105 draft development cases** with the benchmark dense index, five retrieved sources and the existing exact-quote output contract. The development file checksum was `aef90145eb1ba2d7ead54b0d9946209fdcb1a65703a6cd29850ad8bc81fd2303`. Case-level outputs and model/runtime metadata are in `generation_full_dev.json`. No held-out cases were scored.

| Measure | Full development result |
| --- | ---: |
| Cases | 105 |
| Answerable / unsupported | 102 / 3 |
| Invalid outputs rejected by validator | 71 |
| Provider failures | 0 |
| Accepted outputs with claims | 34 |
| Answerable cases with every labeled fact quoted | 27 / 102 |
| Mean labeled fact coverage | 0.2696 |
| Mean labeled claim precision, among outputs with claims | 0.2870 |
| Deliberate abstention on unsupported cases | 0 / 3 |
| Strict evidence-selection proxy passes | 0 / 105 |
| Median / 95th percentile request latency | 12.32 / 27.85 s |

The validator rejected 71 outputs and returned no claims for them. That is a contract failure, **not** a successful semantic abstention. The other 34 outputs contained exact, source-linked quotes. Two of those were answers to unsupported questions. Even when a labeled fact was present, extra irrelevant or unlabeled quotes prevented a strict selection pass. All three multi-source cases failed validation; procedure cases had zero labeled fact coverage. The model did not deliberately abstain on any of the three unsupported development cases.

| Category | Cases | Invalid outputs | Complete labeled evidence | Strict passes |
| --- | ---: | ---: | ---: | ---: |
| Direct fact | 30 | 14 | 16 | 0 |
| Paraphrase | 24 | 19 | 5 | 0 |
| Procedure | 24 | 20 | 0 | 0 |
| Exception | 12 | 10 | 2 | 0 |
| Authorization | 6 | 2 | 4 | 0 |
| Exact identifier | 3 | 2 | 0 | 0 |
| Multi-source | 3 | 3 | 0 | 0 |
| Unanswerable | 3 | 1 | n/a | 0 |

This score is a labeled quote-selection diagnostic. It does not measure semantic entailment, natural-language answer correctness or whether the model would resolve a policy conflict correctly. A useful but unlabeled quote may be marked irrelevant. The 105 development questions are synthetic and mostly templated; labels await human review. Conflict and malicious-text behavior were tested separately with three isolated development diagnostics in `generation_challenges_dev.md`, not with the held-out benchmark cases.

The local model fails the current quality bar and remains experimental. The default extractive/search paths should remain the user-facing demo. The next engineering step is a frozen-set comparison of a stronger local model or a deterministic evidence-selection method, with the same provenance validation and explicit abstention scoring. Human review of independent questions remains necessary before making broad performance claims.

Reproduce with `make generation-eval-full`. A matching checkpoint under `reports/` is saved after each case and used if the command is interrupted. The checkpoint is removed after the final report is written.
