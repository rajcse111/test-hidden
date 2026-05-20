"""
web.py — Streamlit web UI for the local RAG system.

Features:
  • File uploader (PDF, DOCX, XLSX) — ingests on upload, shows chunk count.
  • Chat interface with streaming answer display.
  • Expandable "Sources" section showing retrieved chunks per answer.
  • Sidebar with store stats and a reset button.

Run with: streamlit run web.py
"""

import sys
import tempfile
from pathlib import Path

import streamlit as st

# Allow running from the local-rag/ directory without installing the package
sys.path.insert(0, str(Path(__file__).parent))

from app.config import get_settings
from app.ingest import ingest_file
from app.rag import answer
from app.vector_store import VectorStore


# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Local RAG Assistant",
    page_icon="📚",
    layout="wide",
)


# ── Singleton store ───────────────────────────────────────────────────────────
@st.cache_resource
def get_store() -> tuple[VectorStore, object]:
    settings = get_settings()
    store = VectorStore(settings.chroma_path_resolved, settings.collection_name)
    return store, settings


store, settings = get_store()


# ── Sidebar — upload & stats ──────────────────────────────────────────────────
with st.sidebar:
    st.header("📂 Documents")
    st.caption(f"{store.count()} chunks from {len(store.list_sources())} file(s)")

    uploaded = st.file_uploader(
        "Upload a document",
        type=["pdf", "docx", "xlsx"],
        help="PDF, Word, or Excel files. Ingestion is idempotent — uploading the same file again is safe.",
    )
    if uploaded is not None:
        suffix = Path(uploaded.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.read())
            tmp_path = Path(tmp.name)

        with st.spinner(f"Ingesting {uploaded.name}…"):
            try:
                counts = ingest_file(tmp_path, store, settings)
                st.success(
                    f"✅ {uploaded.name}: "
                    f"+{counts['added']} new chunk(s), "
                    f"{counts['skipped']} already present."
                )
                # Clear cache so chunk count refreshes
                get_store.clear()
                store, settings = get_store()
            except Exception as exc:
                st.error(f"Ingestion failed: {exc}")
            finally:
                tmp_path.unlink(missing_ok=True)

    st.divider()
    st.subheader("Indexed files")
    sources = store.list_sources()
    if sources:
        for src in sources:
            st.caption(f"• {src}")
    else:
        st.caption("No documents yet.")

    st.divider()
    if st.button("🗑️ Reset vector store", type="secondary"):
        store.reset()
        get_store.clear()
        store, settings = get_store()
        st.warning("Vector store cleared.")

    st.divider()
    st.caption(f"**LLM:** {settings.llm_model}")
    st.caption(f"**Embeddings:** {settings.embed_model}")
    st.caption(f"**Top-k:** {settings.top_k}")


# ── Main chat area ────────────────────────────────────────────────────────────
st.title("📚 Local RAG Assistant")
st.caption("Answers grounded in your documents — powered by Ollama, ChromaDB, and nomic-embed-text.")

# Initialise session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Render history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("citations"):
            with st.expander("📎 Sources", expanded=False):
                for cite in msg["citations"]:
                    st.markdown(
                        f"**{cite['source']}** — page {cite['page']} "
                        f"*(distance: {cite['distance']})*\n\n> {cite['snippet']}…"
                    )

# Chat input
if prompt := st.chat_input("Ask a question about your documents…"):
    if store.count() == 0:
        st.warning("No documents indexed yet. Upload a file in the sidebar first.")
        st.stop()

    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Stream assistant response
    with st.chat_message("assistant"):
        placeholder = st.empty()
        full_response = ""
        citations: list = []
        try:
            token_iter, citations = answer(prompt, store, settings)
            for token in token_iter:
                full_response += token
                placeholder.markdown(full_response + "▌")  # typing cursor
            placeholder.markdown(full_response)

            if citations:
                with st.expander("📎 Sources", expanded=True):
                    for cite in citations:
                        st.markdown(
                            f"**{cite['source']}** — page {cite['page']} "
                            f"*(distance: {cite['distance']})*\n\n> {cite['snippet']}…"
                        )
        except RuntimeError as exc:
            full_response = f"⚠️ {exc}"
            placeholder.error(full_response)

    st.session_state.messages.append({
        "role": "assistant",
        "content": full_response,
        "citations": citations,
    })
