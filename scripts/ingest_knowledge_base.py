"""
Knowledge base ingestion script for MedInsight Stage 2.

Reads scraped MedlinePlus .txt files and WHO .pdf files, chunks them with
LlamaIndex SentenceSplitter, embeds using BAAI/bge-base-en-v1.5 (local), and
stores vectors in pgvector via PGVectorStore.

Re-running is safe — existing nodes for a document are deleted before
re-inserting, so no duplicates accumulate.

Usage:
    python scripts/ingest_knowledge_base.py                 # both sources
    python scripts/ingest_knowledge_base.py --source who    # WHO PDFs only
    python scripts/ingest_knowledge_base.py --source medlineplus  # MedlinePlus only
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.config import settings
from app.core.logging import get_logger
from app.services.knowledge_base import get_embed_model, get_vector_store

log = get_logger(__name__)

_MEDLINEPLUS_DIR = _ROOT / "data" / "knowledge_base" / "medlineplus"
_CLINICS_DIR = _ROOT / "data" / "knowledge_base" / "clinics"

from app.core.categories import MEDLINEPLUS_CATEGORY_MAP  # noqa: E402


def _write_with_retry(nodes: list, doc_id: str, max_attempts: int = 4, delay: float = 8.0) -> None:
    """
    Write nodes to pgvector with up to *max_attempts* retries.

    Neon's pooler occasionally fails DNS on the first connection attempt
    (cold-start). Retrying with a short sleep reliably recovers.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            vs = get_vector_store()
            try:
                vs.delete(doc_id)
            except Exception:
                pass  # doc not yet in store
            vs.add(nodes)
            return
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts:
                log.warning(
                    "write_retry",
                    attempt=attempt,
                    delay=delay,
                    error=str(exc)[:120],
                )
                time.sleep(delay)
    raise RuntimeError(f"Failed after {max_attempts} attempts") from last_exc
_WHO_DIR = _ROOT / "data" / "knowledge_base" / "who"


def _load_txt_documents() -> list:
    """
    Load all .txt files from the medlineplus directory as LlamaIndex Documents.

    Each file gets a stable doc_id derived from its filename so the upsert
    logic (delete + re-insert) can target the right nodes on re-runs.
    """
    from llama_index.core import Document  # type: ignore[import]

    docs = []
    if not _MEDLINEPLUS_DIR.exists():
        return docs

    for path in sorted(_MEDLINEPLUS_DIR.glob("*.txt")):
        # Only ingest files that belong to a supported category
        if path.stem not in MEDLINEPLUS_CATEGORY_MAP:
            log.debug("medlineplus_file_skipped", file=path.name, reason="not in supported category map")
            continue
        try:
            content = path.read_text(encoding="utf-8")
            # Pull the source URL from the saved file header (line 2)
            source_url = ""
            for line in content.splitlines()[:3]:
                if line.startswith("URL: "):
                    source_url = line[5:].strip()
                    break
            docs.append(
                Document(
                    text=content,
                    doc_id=f"medlineplus_{path.stem}",
                    metadata={
                        "file_name": path.name,
                        "source_file": path.name,
                        "source_url": source_url,
                        "source_type": "medlineplus",
                        "category": MEDLINEPLUS_CATEGORY_MAP.get(path.stem, "others"),
                        "doc_type": "medlineplus",
                    },
                )
            )
        except Exception as exc:
            log.warning("file_read_error", file=str(path), error=str(exc))

    return docs


def _load_clinic_documents() -> list:
    """
    Load all .txt files from the clinics directory as LlamaIndex Documents.

    Each clinic file is named clinics_{category}.txt and contains structured
    doctor/clinic entries. Metadata includes category and doc_type=clinic_info.
    """
    from llama_index.core import Document  # type: ignore[import]

    docs = []
    if not _CLINICS_DIR.exists():
        log.warning("clinics_dir_missing", path=str(_CLINICS_DIR))
        return docs

    for path in sorted(_CLINICS_DIR.glob("*.txt")):
        try:
            content = path.read_text(encoding="utf-8")
            # Derive category from filename: clinics_liver.txt → "liver"
            stem = path.stem  # e.g. "clinics_liver"
            category = stem.replace("clinics_", "") if stem.startswith("clinics_") else "others"
            docs.append(
                Document(
                    text=content,
                    doc_id=f"clinic_{path.stem}",
                    metadata={
                        "file_name": path.name,
                        "source_file": path.name,
                        "source_url": None,
                        "source_type": "clinic_info",
                        "category": category,
                        "doc_type": "clinic_info",
                    },
                )
            )
            log.debug("clinic_file_loaded", file=path.name, category=category)
        except Exception as exc:
            log.warning("file_read_error", file=str(path), error=str(exc))

    return docs


def _load_pdf_documents() -> list:
    """
    Load all .pdf files from the WHO directory using LlamaIndex PDFReader.

    Skips gracefully if llama-index-readers-file is not installed or if
    the directory is empty — WHO PDFs are optional at this stage.
    """
    docs = []
    if not _WHO_DIR.exists():
        return docs

    try:
        from llama_index.readers.file import PDFReader  # type: ignore[import]
    except ImportError:
        log.warning(
            "pdf_reader_unavailable",
            reason="llama-index-readers-file not installed — skipping WHO PDFs",
        )
        return docs

    reader = PDFReader()
    for path in sorted(_WHO_DIR.glob("*.pdf")):
        try:
            pages = reader.load_data(file=path)
            for i, page in enumerate(pages):
                page.doc_id = f"who_{path.stem}_page_{i}"
                page.metadata.update(
                    {
                        "file_name": path.name,
                        "source_file": path.name,
                        "source_type": "who",
                        "source_url": None,
                    }
                )
            docs.extend(pages)
        except Exception as exc:
            log.warning("file_read_error", file=str(path), error=str(exc))

    return docs


def ingest(source: str = "all") -> None:
    """
    Main ingestion function — chunk, embed, and store knowledge base docs.

    Args:
        source: Which source(s) to ingest.
                "all"         — MedlinePlus .txt files + WHO .pdf files + Clinic .txt files (default)
                "medlineplus" — only data/knowledge_base/medlineplus/
                "who"         — only data/knowledge_base/who/
                "clinics"     — only data/knowledge_base/clinics/

    For each document:
    1. Split into chunks using SentenceSplitter (settings control chunk size)
    2. Embed all chunks in a batch via BAAI/bge-base-en-v1.5 (local)
    3. Delete any existing nodes for this doc_id (idempotency)
    4. Add the new nodes to the vector store
    """
    from llama_index.core.node_parser import SentenceSplitter  # type: ignore[import]

    if source in ("all", "medlineplus"):
        txt_docs = _load_txt_documents()
    else:
        txt_docs = []

    if source in ("all", "who"):
        pdf_docs = _load_pdf_documents()
    else:
        pdf_docs = []

    if source in ("all", "clinics"):
        clinic_docs = _load_clinic_documents()
    else:
        clinic_docs = []

    all_docs = txt_docs + pdf_docs + clinic_docs

    log.info("ingestion_started", source=source, file_count=len(all_docs))

    if not all_docs:
        log.warning(
            "no_documents_found",
            source=source,
            medlineplus_dir=str(_MEDLINEPLUS_DIR),
            who_dir=str(_WHO_DIR),
        )
        return

    splitter = SentenceSplitter(
        chunk_size=settings.embedding_chunk_size,
        chunk_overlap=settings.embedding_chunk_overlap,
    )

    # Build embedding model once (heavy model load) but create a fresh
    # vector_store connection per document — avoids Neon idle timeouts.
    embed_model = get_embed_model()

    total_chunks = 0
    failed: list[str] = []

    for doc in all_docs:
        fname = doc.metadata.get("file_name", "unknown")
        try:
            nodes = splitter.get_nodes_from_documents([doc])

            # Embed all chunks for this document in one batch
            texts = [node.get_content() for node in nodes]
            embeddings = embed_model.get_text_embedding_batch(
                texts, show_progress=False
            )
            for node, emb in zip(nodes, embeddings):
                node.embedding = emb

            # Fresh connection per document with automatic retry for transient
            # Neon DNS failures.
            _write_with_retry(nodes, doc.doc_id)
            total_chunks += len(nodes)

            log.info(
                "document_ingested",
                filename=fname,
                chunk_count=len(nodes),
            )

        except Exception as exc:
            log.error("embedding_failed", filename=fname, error=str(exc))
            failed.append(fname)
            continue  # skip this file, keep processing the rest

    if failed:
        log.warning("some_documents_failed", failed_files=failed, count=len(failed))

    log.info(
        "ingestion_complete",
        total_documents=len(all_docs),
        total_chunks=total_chunks,
        failed=len(failed),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest knowledge base documents into pgvector."
    )
    parser.add_argument(
        "--source",
        choices=["all", "medlineplus", "who", "clinics"],
        default="all",
        help="Which source to ingest (default: all).",
    )
    args = parser.parse_args()
    ingest(source=args.source)
