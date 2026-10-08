"""Local embedding adapter; optional dependencies are loaded only on use."""
import json
import math
import os
import threading
from importlib.metadata import version
from .config import ROOT


def normalize_vector(vector):
    values = [float(x) for x in vector]
    if not values or not all(math.isfinite(x) for x in values):
        raise ValueError("Embedding must be nonempty and finite")
    norm = math.sqrt(sum(x*x for x in values))
    if norm == 0:
        raise ValueError("Embedding must have a nonzero norm")
    return [x/norm for x in values]


class LocalEmbedder:
    def __init__(self, config_path=None):
        config = json.loads((config_path or ROOT/'config/embeddings.json').read_text())
        if config['provider'] != 'sentence_transformers':
            raise ValueError('Unsupported embedding provider')
        if len(config['revision']) != 40 or any(c not in '0123456789abcdef' for c in config['revision']):
            raise ValueError('Model revision must be a pinned commit SHA')
        if config['document_prefix_version'] != 'title-section-text-v1':
            raise ValueError('Unsupported document prefix version')
        os.environ.setdefault('HF_HOME', str(ROOT/'.cache/huggingface'))
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError('Install local embedding dependencies: uv sync --extra embeddings') from exc
        self.model = SentenceTransformer(config['model_id'], revision=config['revision'], device=config['device'], cache_folder=str(ROOT/'.cache/models'), trust_remote_code=False, model_kwargs={'use_safetensors': True})
        self.batch_size = config['batch_size']
        self.lock = threading.Lock()
        self.metadata = dict(provider=config['provider'], model_id=config['model_id'], revision=config['revision'], dimension=self.model.get_embedding_dimension(), max_sequence_tokens=self.model.max_seq_length, normalized=True, device=config['device'], prefix_version=config['document_prefix_version'], sentence_transformers_version=version('sentence-transformers'), transformers_version=version('transformers'), torch_version=version('torch'))

    def encode(self, texts):
        if not texts:
            return []
        with self.lock:
            # Fail rather than silently truncate a chunk at the model context limit.
            lengths = self.model.tokenizer(texts, truncation=False, padding=False, return_length=True)['length']
            if any(length > self.model.max_seq_length for length in lengths):
                raise ValueError('Embedding text exceeds model token budget; reduce chunk size')
            vectors = self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True)
        return [normalize_vector(vector) for vector in vectors.tolist()]
