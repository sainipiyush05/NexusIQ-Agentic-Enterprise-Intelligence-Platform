import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from .config import DATA

STOP = set("a an the is are of for in to and what how does within can their it on with at my please tell me".split())

def tokens(text):
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP]

@dataclass(frozen=True)
class Chunk:
    source_id: str
    document_id: str
    title: str
    section: str
    text: str
    path: str
    tenant_id: str
    roles: tuple
    region: str
    plan: str

def chunk_document(metadata, text, max_words=120, overlap=15):
    if max_words < 1 or not 0 <= overlap < max_words:
        raise ValueError("Require max_words > overlap >= 0")
    section, lines, chunks = "Introduction", [], []
    def emit():
        words = " ".join(lines).split()
        for start in range(0, len(words), max_words-overlap):
            body = " ".join(words[start:start+max_words])
            sid = hashlib.sha256(f"{metadata['document_id']}:{section}:{start}:{body}".encode()).hexdigest()[:20]
            chunks.append(Chunk(sid, metadata['document_id'], metadata['title'], section, body, metadata['path'], metadata['tenant_id'], tuple(metadata['roles']), metadata['region'], metadata['plan']))
            if start + max_words >= len(words):
                break
    for line in text.splitlines():
        if line.startswith("#"):
            emit()
            lines = []
            section = line.lstrip("# ").strip()
        elif line.strip():
            lines.append(line.strip())
    emit()
    return chunks

class SearchIndex:
    def __init__(self, chunks):
        self.chunks = chunks
        self.terms = [Counter(tokens(c.title + " " + c.section + " " + c.text)) for c in chunks]
        self.avg_length = sum(sum(t.values()) for t in self.terms)/max(1, len(chunks))
        self.df = Counter(term for counts in self.terms for term in counts)
        self.by_id = {c.source_id: c for c in chunks}

    @classmethod
    def load(cls, directory=DATA):
        manifest = json.loads((directory / "manifest.json").read_text())
        chunks = []
        for doc in manifest['documents']:
            text = (directory / doc['path']).read_text()
            if hashlib.sha256(text.encode()).hexdigest() != doc['sha256']:
                raise ValueError(f"Document checksum mismatch: {doc['document_id']}")
            chunks.extend(chunk_document(doc, text))
        return cls(chunks)

    def search(self, query, top_k=5, tenant_id="atlascloud", role="analyst", filters=None):
        if not 1 <= top_k <= 20:
            raise ValueError("top_k must be between 1 and 20")
        filters = filters or {}
        if set(filters)-{"region", "plan"}:
            raise ValueError("Only region and plan filters are supported")
        qterms = set(tokens(query))
        results = []
        for chunk, counts in zip(self.chunks, self.terms):
            if chunk.tenant_id != tenant_id or role not in chunk.roles:
                continue
            if any(getattr(chunk, key) != value for key, value in filters.items()):
                continue
            score, length = 0.0, sum(counts.values())
            for term in qterms:
                freq = counts[term]
                if freq:
                    idf = math.log(1+(len(self.chunks)-self.df[term]+0.5)/(self.df[term]+0.5))
                    score += idf*freq*2.5/(freq+1.5*(0.25+0.75*length/max(1, self.avg_length)))
            if score > 0:
                results.append(dict(**asdict(chunk), score=round(score, 6)))
        return sorted(results, key=lambda x: (-x['score'], x['source_id']))[:top_k]

    def answer(self, query, top_k=5, tenant_id="atlascloud", role="analyst", filters=None):
        # Extract explicit domain metadata; never infer identity from query text.
        effective_filters = dict(filters or {})
        for field, options in (("region", ("APAC", "EMEA", "AMER")), ("plan", ("Starter", "Growth", "Enterprise"))):
            matched = [value for value in options if re.search(r"\b"+re.escape(value)+r"\b", query, re.I)]
            if len(matched) == 1 and field not in effective_filters:
                effective_filters[field] = matched[0]
        hits = self.search(query, top_k, tenant_id, role, effective_filters)
        # Conservative routing only for supported synthetic policy subjects.
        # This guard is not a trained intent classifier or production abstention detector.
        q = set(tokens(query))
        subjects = {"refund", "refunds", "support", "critical", "retention", "discount", "discounts", "security", "authentication", "incident", "incidents", "access"}
        unsupported = {"antarctica", "spaceship", "quantum", "medical", "stock"}
        answerable = bool(hits) and bool(q & subjects) and not bool(q & unsupported)
        return dict(query=query, mode="lexical_extract", answer="\n\n".join(f"[{i+1}] {h['text']}" for i,h in enumerate(hits)) if answerable else "Insufficient evidence in the current policy corpus.", abstained=not answerable, citations=hits if answerable else [], retrieved_count=len(hits), limitations="Extractive local baseline; no semantic embeddings or LLM generation.")
