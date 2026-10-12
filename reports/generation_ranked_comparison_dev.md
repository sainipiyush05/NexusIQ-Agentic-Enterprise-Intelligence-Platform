# NexusIQ 04A.4 — ranked evidence selector comparison

The existing Qwen2.5-0.5B quote selector and a new deterministic `ranked_extracts` selector were measured on the same frozen **105-case draft development split**, benchmark dense index, top-five candidate cutoff and exact-quote validator. The new selector uses the already cached cross-encoder to rank authorized chunks and their sentences. It checks explicit entities and topic scope, emits at most two exact quotes, and abstains when its ranking rule has insufficient support. Configuration and strategy version are pinned in `config/ranked_extracts.json`.

| Measure | Local Qwen selector | Ranked extracts v6 |
| --- | ---: | ---: |
| Strict evidence-selection proxy passes | 0 / 105 | **98 / 105** |
| Validator rejections | 71 | **0** |
| Answerable cases with all labeled facts quoted | 27 / 102 | **95 / 102** |
| Mean labeled claim precision | 0.2870 | **0.9314** |
| Deliberate abstention, unsupported cases | 0 / 3 | **3 / 3** |
| False abstention, answerable cases | 0 / 102 | **0 / 102** |
| Median request latency | 12.32 s | **33.05 ms** |
| 95th percentile request latency | 27.85 s | **47.43 ms** |

All seven remaining ranked-selector failures are refund-destination questions. The selected source is the correct refund policy, but the chosen sentence states the refund window rather than where the approved refund is sent. This is a sentence-selection weakness; returning the whole source would hide it from the proxy without improving the answer's focus.

On the separate three-case development challenge set, ranked extracts passed all three labeled selection checks: both approved and draft refund-period quotes, the instruction to report malicious text without repeating the malicious command, and abstention for the unsupported plan. These are artificial diagnostics. Selecting both conflict quotes does not establish that the system can explain which policy governs.

The comparison measures **source-linked quote selection**, not free-form answer generation. The ranked selector is a rule-based candidate extractor; its cross-encoder logits are ranking signals, not calibrated probabilities. It was revised against development failures, so the 98/105 score is an in-sample engineering result. The questions are synthetic and largely templated, the labels await human review, and no held-out cases were scored. Do not present this as production accuracy or cite it as an LLM-generation improvement.

Reproduce with `make generation-ranked-full` and `make generation-ranked-challenges`. Case-level results are in `generation_ranked_full_dev.json` and `generation_ranked_challenges_dev.json`. `make serve-ranked` starts an optional localhost preview on port 8005. A live smoke check returned the 30-day APAC Enterprise refund quote, then deliberately abstained on an Antarctica policy question. The default demo mode remains unchanged.

Next: 04B semantic citation verification and human review of independent benchmark questions. Keep the seven destination failures visible; address them with a general answer-type selection rule or a stronger model evaluated against the same frozen set.
