"""
documents.py — REST API endpoints for RAG document management.

Endpoints:
  POST /api/documents/upload  — multipart file upload, ingests immediately
  GET  /api/documents         — list ingested source filenames + chunk count
  POST /api/documents/reset   — clear the entire vector store

All endpoints degrade gracefully when RAG is not initialised (return 503).
"""

import sys
import tempfile
from pathlib import Path

from app.core.config import Settings
from app.services.rag_retriever import (
    get_document_count,
    is_available,
    list_document_sources,
    make_rag_settings,
)
from fastapi import APIRouter, HTTPException, Request, UploadFile
from loguru import logger
from pydantic import BaseModel

router = APIRouter()

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".md"}


def _get_store_and_settings(request: Request):
    """Extract rag_store + Settings from app state; raise 503 if unavailable."""
    store = getattr(request.app.state, "rag_store", None)
    settings: Settings = request.app.state.runtime.settings
    if store is None or not is_available():
        raise HTTPException(
            status_code=503,
            detail="RAG is not available. Check that local-rag/ dependencies are installed "
                   "and RAG_ENABLED=true in .env.",
        )
    return store, settings


class DocumentListResponse(BaseModel):
    total_chunks: int
    sources: list[str]


@router.post("/upload")
async def upload_document(request: Request, file: UploadFile) -> dict:
    """Ingest an uploaded file into the vector store.

    Accepts PDF, DOCX, XLSX, TXT, or MD.  Uses a temp file so the original
    filename is preserved in metadata (source field).
    """
    store, settings = _get_store_and_settings(request)

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )

    # Save upload to a temp file that carries the original filename
    tmp_dir = Path(tempfile.mkdtemp())
    tmp_path = tmp_dir / (file.filename or f"upload{suffix}")
    try:
        content = await file.read()
        tmp_path.write_bytes(content)

        # Import local-rag ingest function (path was set in rag_retriever.py)
        # We do a local import here to avoid hard dependency at module level
        rag_local_path = str(Path(__file__).parents[3] / "local-rag")
        if rag_local_path not in sys.path:
            sys.path.insert(0, rag_local_path)

        from app.ingest import ingest_file  # local-rag/app/ingest.py

        rag_settings = make_rag_settings(settings)
        counts = ingest_file(tmp_path, store, rag_settings)

        logger.info(
            "document uploaded | file={} added={} skipped={}",
            file.filename, counts["added"], counts["skipped"]
        )
        return {
            "filename": file.filename,
            "chunks_added": counts["added"],
            "chunks_skipped": counts["skipped"],
            "total_chunks": get_document_count(store),
        }
    except Exception as exc:
        logger.exception("document upload failed | file={}", file.filename)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        tmp_path.unlink(missing_ok=True)
        try:
            tmp_dir.rmdir()
        except OSError:
            pass


@router.get("", response_model=DocumentListResponse)
async def list_documents(request: Request) -> DocumentListResponse:
    """Return current document stats: total chunk count and source filenames."""
    store, _ = _get_store_and_settings(request)
    return DocumentListResponse(
        total_chunks=get_document_count(store),
        sources=list_document_sources(store),
    )


@router.post("/reset")
async def reset_documents(request: Request) -> dict:
    """Delete all indexed chunks from the vector store."""
    store, _ = _get_store_and_settings(request)
    store.reset()
    logger.info("RAG vector store reset via API")
    return {"status": "reset", "total_chunks": 0}
