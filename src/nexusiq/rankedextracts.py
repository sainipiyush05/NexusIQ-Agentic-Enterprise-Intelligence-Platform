"""Conservative, local selection of exact quotes from authorized retrieved chunks."""
import json
import math
import re

from .config import ROOT
from .rerank import LocalReranker


WORD = re.compile(r"[A-Za-z][A-Za-z0-9-]*")


class RankedExtractsProvider:
    """A measured evidence selector, not an LLM or semantic correctness guarantee."""
    name = 'ranked_extracts'
    candidate_only = True

    def __init__(self, reranker=None, config_path=None):
        config = json.loads((config_path or ROOT/'config/ranked_extracts.json').read_text())
        if (not math.isfinite(float(config['min_reranker_logit']))
                or not math.isfinite(float(config['identifier_secondary_min_logit']))
                or float(config['identifier_secondary_min_logit']) > float(config['min_reranker_logit'])
                or not 0 <= float(config['numeric_sentence_bonus']) <= 2
                or config['max_claims_single'] != 1 or config['max_claims_composite'] != 2
                or config['strategy_version'] != 'ranked-extracts-v6'):
            raise ValueError('Invalid ranked extracts configuration')
        self.reranker = reranker if reranker is not None else LocalReranker()
        self.min_score = float(config['min_reranker_logit'])
        self.identifier_secondary_min = float(config['identifier_secondary_min_logit'])
        self.numeric_bonus = float(config['numeric_sentence_bonus'])
        self.metadata = dict(config, reranker=self.reranker.metadata,
                             contract='cited-quotes-v1', selection='exact-chunk-extract')

    @staticmethod
    def _unknown_named_entity(query, hits):
        known = set(WORD.findall(' '.join(f"{h['title']} {h['section']} {h['text']}" for h in hits).lower()))
        for match in re.finditer(r'\b([a-z][a-z0-9-]*)\s+(?:plan|tier)\b', query, re.I):
            if match.group(1).lower() not in known and match.group(1).lower() not in {'the','a','this','that'}:
                return True
        words = WORD.findall(query)
        interrogatives = {'who','what','where','when','why','how','which','can','does','do','is','are',
                          'i','we','our','me','my','us'}
        return any(word[0].isupper() and word.lower() not in known and word.lower() not in interrogatives
                   for word in words[1:])

    @staticmethod
    def _scope_filter(query, hits):
        words = {word.lower() for word in WORD.findall(query)}
        regions = {h['region'].lower() for h in hits if h.get('region')}
        plans = {h['plan'].lower() for h in hits if h.get('plan')}
        query_regions = words & regions
        query_plans = words & plans
        # Metadata is trusted, while the query only narrows scope.
        return [h for h in hits if (not query_regions or h['region'].lower() in query_regions)
                and (not query_plans or h['plan'].lower() in query_plans)]

    @staticmethod
    def _subject_filter(query, hits):
        if re.search(r'\b(compare|draft|conflict|discrepancy|versus)\b', query, re.I):
            return hits
        subjects = set()
        patterns = {
            'refund': r'\b(refund|money back|first bill)\b',
            'support': r'\b(support|critical|incident|ticket|outage)\b|service is down|get back to us',
            'retention': r'\b(retention|discount|concession)\b',
            'security': r'\b(security|authentication|multi-factor|access reviews?)\b',
        }
        for subject, pattern in patterns.items():
            if re.search(pattern, query, re.I):
                subjects.add(subject)
        if not subjects:
            return hits
        matched = [h for h in hits if any(subject in h['title'].lower() for subject in subjects)]
        return matched or hits

    def generate(self, query, hits, context):
        if not hits or self._unknown_named_entity(query, hits):
            return dict(status='insufficient_evidence', claims=[])
        eligible = self._subject_filter(query, self._scope_filter(query, hits))
        if not eligible:
            return dict(status='insufficient_evidence', claims=[])
        scores = self.reranker.score(query, eligible)
        ranked = sorted(zip(scores, eligible), key=lambda pair: (-pair[0], pair[1]['source_id']))
        if not ranked or ranked[0][0] < self.min_score:
            return dict(status='insufficient_evidence', claims=[])
        composite = bool(re.search(r'\b(compare|and)\b', query, re.I))
        chosen = [ranked[0][1]]
        if composite and len(ranked) > 1:
            second_score, second_hit = ranked[1]
            code_query = bool(re.search(r'\b[A-Z]{2}-[A-Z]{2}\b', query))
            floor = (self.identifier_secondary_min if code_query
                     and second_hit['document_id'] == ranked[0][1]['document_id']
                     else self.min_score)
            if second_score >= floor:
                chosen.append(second_hit)
        if composite and len(chosen) < 2:
            return dict(status='insufficient_evidence', claims=[])
        quotes = []
        numeric_question = bool(re.search(r'\b(period|deadline|time|price|seats?|cost|how many|how long|how often|how fast)\b', query, re.I))
        code_match = re.search(r'\b[A-Z]{2}-[A-Z]{2}\b', query)
        catalog_text = ' '.join(h['text'] for h in chosen if 'product codes' in h['section'].lower())
        plan_match = re.search(rf'\b{re.escape(code_match.group())} is the (\w+) plan\b', catalog_text) if code_match else None
        code_plan = plan_match.group(1).lower() if plan_match else None
        for hit in chosen:
            sentences = [sentence.strip() for sentence in re.split(r'(?<=[.!?])\s+', hit['text']) if sentence.strip()]
            sentence_hits = [dict(hit, text=sentence) for sentence in sentences]
            sentence_scores = self.reranker.score(query, sentence_hits)
            best = max(zip(sentence_scores, sentences),
                       key=lambda pair: pair[0]
                       + (self.numeric_bonus if numeric_question and re.search(r'\b\d+\b', pair[1]) else 0)
                       + (20 if code_plan and 'limits' in hit['section'].lower()
                          and re.search(rf'\b{re.escape(code_plan)}\b', pair[1], re.I) else 0))[1]
            quotes.append(dict(source_id=hit['source_id'], quote=best))
        return dict(status='answered', claims=quotes)
