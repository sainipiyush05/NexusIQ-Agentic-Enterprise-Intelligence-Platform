"""Asynchronous background worker queue for document ingestion and index updates."""
import concurrent.futures
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from .ingestion import IngestionMetadata, IngestionResult, ingest_document
from .retrieval import Chunk, SearchIndex


@dataclass
class IngestionJob:
    job_id: str
    tenant_id: str
    filename: str
    status: str  # "pending", "processing", "completed", "failed"
    created_at: float
    completed_at: Optional[float] = None
    document_id: Optional[str] = None
    chunks_count: int = 0
    checksum: Optional[str] = None
    error: Optional[str] = None
    is_duplicate: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class IngestionWorker:
    def __init__(self, max_workers: int = 2):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="nexusiq-ingest")
        self.jobs: dict[str, IngestionJob] = {}

    def get_job(self, job_id: str) -> Optional[IngestionJob]:
        return self.jobs.get(job_id)

    def list_jobs(self, tenant_id: str) -> list[IngestionJob]:
        return [job for job in self.jobs.values() if job.tenant_id == tenant_id]

    def submit_job(
        self,
        filename: str,
        content_bytes: bytes,
        meta: IngestionMetadata,
        index: Optional[SearchIndex] = None,
        on_complete: Optional[Callable[[IngestionResult], None]] = None,
    ) -> IngestionJob:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job = IngestionJob(
            job_id=job_id,
            tenant_id=meta.tenant_id,
            filename=filename,
            status="pending",
            created_at=time.time(),
        )
        self.jobs[job_id] = job

        def _task():
            job.status = "processing"
            try:
                result = ingest_document(filename, content_bytes, meta)
                job.document_id = result.document_id
                job.chunks_count = result.chunks_count
                job.checksum = result.checksum_sha256
                job.is_duplicate = result.is_duplicate
                job.completed_at = time.time()
                job.status = "completed"

                # Update live search index if provided
                if index is not None and result.chunks:
                    existing = [c for c in index.chunks if c.document_id != result.document_id]
                    updated_chunks = existing + result.chunks
                    index.__init__(updated_chunks)

                if on_complete:
                    on_complete(result)
            except Exception as exc:
                job.status = "failed"
                job.error = str(exc)
                job.completed_at = time.time()

        self.executor.submit(_task)
        return job

    def shutdown(self, wait: bool = True):
        self.executor.shutdown(wait=wait)
