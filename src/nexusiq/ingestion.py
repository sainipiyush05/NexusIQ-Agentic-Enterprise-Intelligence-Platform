"""Document ingestion pipeline: MIME/size checks, normalization, checksumming, and chunking."""
import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional, Sequence

from .config import DATA, ROOT
from .retrieval import Chunk, chunk_document

MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MB limit
ALLOWED_EXTENSIONS = frozenset({".md", ".txt", ".markdown", ".html", ".htm"})
DOCUMENTS_DIR = DATA / "documents"


class IngestionError(ValueError):
    pass


class FileTooLargeError(IngestionError):
    pass


class InvalidFileTypeError(IngestionError):
    pass


@dataclass(frozen=True)
class IngestionMetadata:
    title: str
    tenant_id: str
    document_id: Optional[str] = None
    department: str = "General"
    region: str = "Global"
    plan: str = "All"
    roles: tuple[str, ...] = ("analyst", "viewer")
    effective_date: str = "2026-07-01"
    version: str = "1.0"


@dataclass(frozen=True)
class IngestionResult:
    document_id: str
    tenant_id: str
    title: str
    checksum_sha256: str
    chunks_count: int
    chunks: list[Chunk]
    path: str
    is_duplicate: bool


def normalize_text(raw_text: str, is_html: bool = False) -> str:
    """Normalize text encoding and whitespace, stripping HTML tags while preserving headings."""
    text = unicodedata.normalize("NFC", raw_text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    if is_html:
        # Simple heading tag preservation
        text = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"\n# \1\n", text, flags=re.I | re.S)
        text = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\1\n", text, flags=re.I | re.S)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)

    # Clean multiple trailing spaces and limit excessive blank lines
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return cleaned


def validate_file(filename: str, content_bytes: bytes) -> tuple[str, str]:
    """Validate size, extension, and decodability."""
    if len(content_bytes) > MAX_FILE_BYTES:
        raise FileTooLargeError(f"File size ({len(content_bytes)} bytes) exceeds limit ({MAX_FILE_BYTES} bytes)")
    if len(content_bytes) == 0:
        raise IngestionError("Uploaded file cannot be empty")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidFileTypeError(
            f"Unsupported file extension '{ext}'. Allowed: {sorted(ALLOWED_EXTENSIONS)}"
        )

    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content_bytes.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise IngestionError("File content could not be decoded as text") from exc

    return text, ext


def ingest_document(
    filename: str,
    content_bytes: bytes,
    meta: IngestionMetadata,
    storage_root: Optional[Path] = None,
) -> IngestionResult:
    """Process an uploaded document: validate, normalize, store, and chunk."""
    text, ext = validate_file(filename, content_bytes)
    normalized = normalize_text(text, is_html=ext in {".html", ".htm"})
    if not normalized.strip():
        raise IngestionError("Document contained no extractable text after normalization")

    checksum = hashlib.sha256(content_bytes).hexdigest()
    doc_id = meta.document_id or f"doc_{checksum[:12]}"
    # Sanitize doc_id
    doc_id = re.sub(r"[^a-zA-Z0-9_-]", "_", doc_id)

    root = storage_root or DOCUMENTS_DIR
    tenant_dir = root / meta.tenant_id
    tenant_dir.mkdir(parents=True, exist_ok=True)
    stored_path = tenant_dir / f"{doc_id}.md"

    # Check manifest for deduplication
    manifest_path = tenant_dir / "manifest.json"
    manifest: dict[str, dict] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            manifest = {}

    is_duplicate = False
    if doc_id in manifest and manifest[doc_id].get("sha256") == checksum:
        is_duplicate = True

    # Persist the file
    stored_path.write_text(normalized)

    # Create chunks
    chunk_meta = {
        "document_id": doc_id,
        "title": meta.title,
        "path": str(stored_path.relative_to(root.parent)),
        "tenant_id": meta.tenant_id,
        "roles": meta.roles,
        "region": meta.region,
        "plan": meta.plan,
    }
    chunks = chunk_document(chunk_meta, normalized)

    # Update manifest
    manifest[doc_id] = {
        "document_id": doc_id,
        "title": meta.title,
        "filename": filename,
        "sha256": checksum,
        "department": meta.department,
        "region": meta.region,
        "plan": meta.plan,
        "roles": list(meta.roles),
        "chunks_count": len(chunks),
        "path": str(stored_path.relative_to(root.parent)),
        "effective_date": meta.effective_date,
        "version": meta.version,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))

    return IngestionResult(
        document_id=doc_id,
        tenant_id=meta.tenant_id,
        title=meta.title,
        checksum_sha256=checksum,
        chunks_count=len(chunks),
        chunks=chunks,
        path=str(stored_path),
        is_duplicate=is_duplicate,
    )


def list_tenant_documents(tenant_id: str, storage_root: Optional[Path] = None) -> list[dict]:
    """Retrieve catalog of ingested documents for a tenant."""
    root = storage_root or DOCUMENTS_DIR
    manifest_path = root / tenant_id / "manifest.json"
    if not manifest_path.exists():
        return []
    try:
        manifest = json.loads(manifest_path.read_text())
        return list(manifest.values())
    except Exception:
        return []
