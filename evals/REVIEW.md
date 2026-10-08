# Evaluation set review guide

Status: draft, source-checked by the implementation agent; human review pending.

## What is included

162 cases: 105 development, 57 held out. There are 16 authored intent patterns instantiated across nine region/plan scopes and 18 additional challenge questions. They are not 162 independently collected user questions. Cases cover direct facts, paraphrases, exceptions, procedures, authorization, exact identifiers, temporal changes, conflicting sources, multi-source questions, missing information, and malicious document text.

The benchmark adds four fixtures to the 36-document corpus in memory. These fixtures are benchmark-only and are not loaded by the browser demo. They have explicit source IDs, versions, effective dates and checksums. Do not silently promote them into production data.

## Human review process

1. Check that the question has a natural interpretation and that the selected section and quoted fact are sufficient to support it.
2. Check negative cases against the entire corpus: retrieval silence alone does not prove missing evidence.
3. Check the date and version needed for temporal cases; conflict questions must cite both the approved policy and draft memo.
4. For multi-source questions, verify that every required evidence unit is labeled.
5. Replace templated wording with independently collected questions before treating the set as a strong generalization benchmark.
6. Record reviewer identity, date and decision per case. Update review_status only after a real review. Bump benchmark version and regenerate hashes intentionally after label edits.

## Split rules

All related scope variants stay together. APAC Enterprise, EMEA Growth and AMER Starter belong to holdout. Challenge groups are also kept together. Wording patterns still overlap across splits, so scope grouping alone does not eliminate template leakage. Use development cases for tuning; score holdout only at a deliberate release comparison. The CLI requires --allow-holdout, but this is a process guard, not an access-control system.

## Missing-evidence rationales

- Platinum refunds: the company has only Starter, Growth and Enterprise plans; no Platinum terms exist.
- Retention maximum percentage: approval and expiration are documented, but no maximum percentage is specified.
- Guaranteed resolution time: support explicitly promises initial response only and says resolution time is not guaranteed.
- Biometric storage: administrator authentication and incident reporting do not establish a biometric storage policy.
- Antarctica refunds: no policies for that region exist.

## Metrics and limits

Relevance is keyed by document ID and section; retrieving the Scope section of a policy does not count as retrieving its Rules. Multiple chunks from the same relevant section count once. Recall is recovered evidence units divided by all labeled units; precision uses the requested K as denominator; MRR rewards the first relevant section; nDCG uses binary section relevance with the ideal top-K ranking.

Evidence fact coverage requires the quote to appear in the correct retrieved source and section. Answer evidence coverage checks the extractive response's citations separately. Neither metric proves a model reasoned correctly. No LLM judge is used. Conflicts and adversarial instructions need later generation-behavior assertions; retrieving them cannot establish safe handling.

Commands:

```sh
make validate-evals
make benchmark
# Release comparison only; do not tune using these results:
PYTHONPATH=src python3 -m nexusiq benchmark --split holdout --allow-holdout
```
