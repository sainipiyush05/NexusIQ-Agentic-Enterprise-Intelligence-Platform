"""Offline NLI check for an atomic claim against a cited, authorized quote.

The NLI score is a diagnostic signal, not a proof of factual correctness.  A
neutral or low-confidence pair stays uncertain and should be sent for review.
"""
import json
import math
import statistics
import time
from pathlib import Path

from .config import ROOT

CONFIG = ROOT / 'config/citation_verification.json'
DEV_CASES = ROOT / 'evals/citations/dev.jsonl'


def load_config(path=CONFIG):
    config = json.loads(Path(path).read_text())
    if not isinstance(config.get('model_id'), str) or not config['model_id'].strip():
        raise ValueError('Citation model_id is required')
    revision = config.get('revision')
    if not isinstance(revision, str) or len(revision) != 40 or any(c not in '0123456789abcdef' for c in revision):
        raise ValueError('Citation model revision must be a pinned SHA')
    for key in ('support_threshold', 'contradiction_threshold'):
        if not isinstance(config.get(key), (int, float)) or not 0 < config[key] < 1:
            raise ValueError(f'Invalid {key}')
    if type(config.get('max_pair_tokens')) is not int or not 16 <= config['max_pair_tokens'] <= 512:
        raise ValueError('Invalid max_pair_tokens')
    return config


def cache_model(config=None):
    import os
    from huggingface_hub import snapshot_download
    config = config or load_config()
    os.environ.setdefault('HF_HOME', str(ROOT / '.cache/huggingface'))
    os.environ.setdefault('HF_HUB_DISABLE_XET', '1')
    return snapshot_download(config['model_id'], revision=config['revision'],
                             cache_dir=str(ROOT / '.cache/models'),
                             allow_patterns=['*.json', '*.safetensors', '*.txt', '*.model'])


class LocalNLIScorer:
    """Load only a pinned, cached model. Premise precedes hypothesis."""
    def __init__(self, config=None):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.config = config or load_config()
        common = dict(revision=self.config['revision'], cache_dir=str(ROOT / '.cache/models'),
                      trust_remote_code=False, local_files_only=True)
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(self.config['model_id'], **common)
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.config['model_id'], use_safetensors=True, **common).to('cpu').eval()
        except OSError as exc:
            raise RuntimeError('Citation model is not cached; run cache-citation-model') from exc
        labels = {int(k): v.lower() for k, v in self.model.config.id2label.items()}
        if labels != {0: 'contradiction', 1: 'entailment', 2: 'neutral'}:
            raise ValueError('Unexpected NLI label mapping')
        self.torch = torch

    def scores(self, premise, hypothesis):
        encoded = self.tokenizer(premise, hypothesis, return_tensors='pt', truncation=False)
        if encoded['input_ids'].shape[-1] > self.config['max_pair_tokens']:
            return None
        with self.torch.inference_mode():
            logits = self.model(**encoded).logits[0]
            probabilities = self.torch.softmax(logits, dim=-1).tolist()
        return dict(zip(('contradiction', 'entailment', 'neutral'), probabilities))


class CitationVerifier:
    def __init__(self, scorer, config=None):
        self.scorer = scorer
        self.config = config or load_config()

    def verify(self, claim, source_id, quote, sources):
        """Return a verdict after checking that the quote belongs to source_id.

        ``sources`` must contain only sources authorized for this request.
        Claims should be atomic; compound claims need splitting before this call.
        """
        if not all(isinstance(value, str) and value.strip() for value in (claim, source_id, quote)):
            raise ValueError('Claim, source_id and quote must be nonempty strings')
        if len(claim) > 1000 or len(quote) > 4000:
            raise ValueError('Citation input exceeds length bounds')
        if not isinstance(sources, dict) or source_id not in sources:
            return dict(verdict='unsupported', reason='unknown_or_unauthorized_source', scores=None)
        source_text = sources[source_id]
        if not isinstance(source_text, str) or quote not in source_text:
            return dict(verdict='unsupported', reason='quote_not_in_source', scores=None)
        scores = self.scorer.scores(quote, claim)
        if scores is None:
            return dict(verdict='uncertain', reason='pair_exceeds_token_limit', scores=None)
        if set(scores) != {'contradiction', 'entailment', 'neutral'} or any(
                not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0 or value > 1
                for value in scores.values()):
            raise ValueError('Invalid NLI scores')
        if scores['entailment'] >= self.config['support_threshold'] and scores['entailment'] > scores['contradiction']:
            verdict, reason = 'supported', 'entailment_signal'
        elif scores['contradiction'] >= self.config['contradiction_threshold'] and scores['contradiction'] > scores['entailment']:
            verdict, reason = 'unsupported', 'contradiction_signal'
        else:
            verdict, reason = 'uncertain', 'insufficient_nli_confidence'
        return dict(verdict=verdict, reason=reason, scores=scores)


def load_dev_cases(path=DEV_CASES):
    cases = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    ids = set()
    for case in cases:
        if set(case) != {'id', 'claim', 'source_id', 'quote', 'source_text', 'label'}:
            raise ValueError('Invalid citation case schema')
        if any(not isinstance(case[key], str) or not case[key].strip()
               for key in ('id', 'claim', 'source_id', 'quote', 'source_text')):
            raise ValueError('Citation case contains an empty field')
        if case['id'] in ids or case['label'] not in {'supported', 'unsupported'}:
            raise ValueError('Duplicate citation case or invalid label')
        ids.add(case['id'])
    if not cases:
        raise ValueError('Citation development set is empty')
    return cases


def evaluate_dev(verifier=None, cases=None):
    cases = cases or load_dev_cases()
    verifier = verifier or CitationVerifier(LocalNLIScorer())
    rows = []
    for case in cases:
        start = time.perf_counter()
        result = verifier.verify(case['claim'], case['source_id'], case['quote'],
                                 {case['source_id']: case['source_text']})
        rows.append(dict(id=case['id'], label=case['label'], **result,
                         latency_ms=round((time.perf_counter()-start)*1000, 2)))
    tp = sum(row['label'] == 'unsupported' and row['verdict'] == 'unsupported' for row in rows)
    fp = sum(row['label'] == 'supported' and row['verdict'] == 'unsupported' for row in rows)
    fn = sum(row['label'] == 'unsupported' and row['verdict'] != 'unsupported' for row in rows)
    return dict(model=verifier.config['model_id'], revision=verifier.config['revision'],
                cases=rows, summary=dict(total=len(rows), unsupported_cases=tp+fn,
                    flagged_unsupported=tp+fp, true_positive=tp, false_positive=fp, false_negative=fn,
                    unsupported_precision=tp/(tp+fp) if tp+fp else None,
                    unsupported_recall=tp/(tp+fn) if tp+fn else None,
                    supported_predicted=sum(row['verdict']=='supported' for row in rows),
                    uncertain=sum(row['verdict']=='uncertain' for row in rows),
                    median_latency_ms=round(statistics.median(row['latency_ms'] for row in rows), 2)),
                limitations='Small author-created development set; NLI is not proof, and neutral/uncertain cases need review. No held-out or live-traffic quality claim.')
