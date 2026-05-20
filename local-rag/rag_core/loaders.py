"""
loaders.py — File-to-text extraction for PDF, DOCX, Excel, and plain text.

Each loader returns a list of dicts:
    {"text": str, "metadata": {"source": filename, "page": int | str}}

Empty chunks are skipped so downstream splitters never see blank documents.
"""

from pathlib import Path
from typing import TypedDict


class Chunk(TypedDict):
    text: str
    metadata: dict[str, str | int]


def load_pdf(path: Path) -> list[Chunk]:
    """Extract text page-by-page from a PDF using pdfplumber.

    pdfplumber handles most native PDFs well.  Scanned PDFs will return
    empty pages — see README troubleshooting for OCR guidance.
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("Run: pip install pdfplumber")

    chunks: list[Chunk] = []
    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                chunks.append({"text": text, "metadata": {"source": path.name, "page": page_num}})
    return chunks


def load_docx(path: Path) -> list[Chunk]:
    """Extract paragraphs from a DOCX file using python-docx.

    All paragraphs are joined into a single logical page (DOCX has no native
    page concept accessible without rendering).  Tables are excluded here;
    add table iteration if your docs are table-heavy.
    """
    try:
        from docx import Document
    except ImportError:
        raise ImportError("Run: pip install python-docx")

    doc = Document(str(path))
    paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    if not paragraphs:
        return []
    full_text = "\n\n".join(paragraphs)
    return [{"text": full_text, "metadata": {"source": path.name, "page": 1}}]


def load_excel(path: Path) -> list[Chunk]:
    """Convert each Excel row to a self-describing sentence.

    Row format: "Sheet <name> | ColA: val | ColB: val | ..."
    This embeds meaningfully because the column name provides semantic context
    that a raw comma-separated row would lose.
    """
    try:
        import pandas as pd
    except ImportError:
        raise ImportError("Run: pip install pandas openpyxl")

    chunks: list[Chunk] = []
    xl = pd.ExcelFile(path, engine="openpyxl")
    for sheet_name in xl.sheet_names:
        df = xl.parse(sheet_name)
        df = df.dropna(how="all")
        for row_idx, row in df.iterrows():
            parts = [f"Sheet {sheet_name}"]
            for col in df.columns:
                val = row[col]
                if pd.notna(val) and str(val).strip():
                    parts.append(f"{col}: {val}")
            if len(parts) > 1:  # at least one non-empty column
                sentence = " | ".join(parts)
                chunks.append({
                    "text": sentence,
                    "metadata": {"source": path.name, "page": f"{sheet_name}:row{row_idx}"},
                })
    return chunks


def load_text(path: Path) -> list[Chunk]:
    """Load a plain-text or markdown file as a single chunk."""
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return []
    return [{"text": text, "metadata": {"source": path.name, "page": 1}}]


_LOADERS = {
    ".pdf": load_pdf,
    ".docx": load_docx,
    ".xlsx": load_excel,
    ".xls": load_excel,
    ".txt": load_text,
    ".md": load_text,
}


def load_file(path: Path) -> list[Chunk]:
    """Dispatch to the right loader based on file extension.

    Raises ValueError for unsupported types rather than silently ignoring them
    so the caller can surface a clear error to the user.
    """
    suffix = path.suffix.lower()
    loader = _LOADERS.get(suffix)
    if loader is None:
        raise ValueError(
            f"Unsupported file type '{suffix}' for {path.name}. "
            f"Supported: {', '.join(_LOADERS)}"
        )
    return loader(path)
