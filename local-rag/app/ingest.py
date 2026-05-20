"""
ingest.py — Orchestrates load → chunk → embed → store with idempotency.

Idempotency strategy:
  Each chunk is identified by f"{file_sha256[:16]}_{chunk_index}".
  ChromaDB's upsert is idempotent by ID, so re-ingesting an unchanged file
  is a no-op (same IDs, same vectors).  Modified files get new hashes → new
  IDs, but old chunks with the old hash prefix remain unless you call reset().
  For full re-index of a modified file, delete it first via CLI `remove` or
  call reset() to clear everything.

Summary output:
  prints processed/skipped counts so the user knows what happened.
"""

import hashlib
from pathlib import Path

from app.chunker import split_chunks
from app.config import RAGSettings
from app.embeddings import embed_texts
from app.loaders import load_file
from app.vector_store import VectorStore


def _file_sha256(path: Path) -> str:
    """Compute SHA-256 hex digest of a file's binary content."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def ingest_file(path: Path, store: VectorStore, settings: RAGSettings) -> dict[str, int]:
    """Ingest a single file into the vector store.

    Returns:
        {"added": int, "skipped": int} — counts of new vs duplicate chunks.
    """
    file_hash = _file_sha256(path)
    hash_prefix = file_hash[:16]

    raw_chunks = load_file(path)
    if not raw_chunks:
        print(f"  [skip] {path.name} — no extractable text")
        return {"added": 0, "skipped": 0}

    split = split_chunks(raw_chunks, settings.chunk_size, settings.chunk_overlap)
    if not split:
        print(f"  [skip] {path.name} — all chunks too short after splitting")
        return {"added": 0, "skipped": 0}

    # Build stable IDs: hash_prefix + chunk position makes re-ingest idempotent
    ids = [f"{hash_prefix}_{i}" for i in range(len(split))]
    texts = [c["text"] for c in split]
    metadatas = [c["metadata"] for c in split]

    # Check which IDs are already stored to report accurate skip counts.
    # ChromaDB upsert will write all of them anyway (idempotent), but we
    # show the user how many were genuinely new vs already present.
    existing_ids: set[str] = set()
    if store.count() > 0:
        result = store._collection.get(ids=ids, include=[])
        existing_ids = set(result["ids"])

    new_count = sum(1 for id_ in ids if id_ not in existing_ids)
    skip_count = len(ids) - new_count

    # Embed only the new chunks — no point re-embedding what's already there
    new_indices = [i for i, id_ in enumerate(ids) if id_ not in existing_ids]
    if new_indices:
        new_texts = [texts[i] for i in new_indices]
        new_embeddings = embed_texts(new_texts, settings.embed_model, settings.ollama_host)
        new_ids = [ids[i] for i in new_indices]
        new_metas = [metadatas[i] for i in new_indices]
        store.upsert(new_ids, new_embeddings, new_texts, new_metas)

    return {"added": new_count, "skipped": skip_count}


def ingest_path(
    path: Path,
    store: VectorStore,
    settings: RAGSettings,
) -> None:
    """Ingest a file or every supported file in a directory tree.

    Prints a per-file summary and a final totals line.
    """
    supported_extensions = {".pdf", ".docx", ".xlsx", ".xls", ".txt", ".md"}

    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = [f for f in path.rglob("*") if f.suffix.lower() in supported_extensions]
    else:
        raise FileNotFoundError(f"Path does not exist: {path}")

    if not files:
        print(f"No supported documents found in {path}")
        return

    total_added = 0
    total_skipped = 0
    total_files = 0

    for file in sorted(files):
        try:
            counts = ingest_file(file, store, settings)
            total_added += counts["added"]
            total_skipped += counts["skipped"]
            total_files += 1
            status = f"+{counts['added']} new, {counts['skipped']} dup"
            print(f"  [ok] {file.name:<40} {status}")
        except Exception as exc:
            print(f"  [err] {file.name}: {exc}")

    print(f"\nIngestion complete: {total_files} file(s), "
          f"{total_added} chunk(s) added, {total_skipped} chunk(s) already present.")
    print(f"Total chunks in store: {store.count()}")
