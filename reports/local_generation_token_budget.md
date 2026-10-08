# Local generation input-budget check

Measured 105 development prompts with the pinned generator tokenizer and the actual chat template, system prompt, output schema and five dense-retrieved sources. Input lengths range from 556 to 749 tokens (mean 650.04). Configured input ceiling: 4096. No held-out prompts scored.

The provider checks tensor input sequence length before calling generation; it does not silently truncate. Input and maximum output budgets are checked against the model's configured context capacity during loading. A separate output-token ceiling and cooperative decoding deadline apply.
