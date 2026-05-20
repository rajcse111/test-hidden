"""
cli.py — Command-line interface for the local RAG system.

Commands:
  ingest <path>  — Load documents from a file or directory into the vector store.
  chat           — Interactive Q&A loop with streamed answers and printed citations.
  reset          — Wipe the entire vector store (irreversible).
  status         — Show collection stats (document count, source files).

Uses typer for CLI structure and rich for readable coloured output.
"""

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(help="Local RAG assistant — ask questions grounded in your documents.")
console = Console()
err_console = Console(stderr=True, style="red")


def _get_store():
    """Initialise VectorStore from current settings."""
    from app.config import get_settings
    from app.vector_store import VectorStore

    settings = get_settings()
    return VectorStore(settings.chroma_path_resolved, settings.collection_name), settings


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="File or directory to ingest."),
) -> None:
    """Ingest documents into the vector store."""
    from app.ingest import ingest_path

    if not path.exists():
        err_console.print(f"Path not found: {path}")
        raise typer.Exit(1)

    store, settings = _get_store()
    console.print(f"\n[bold cyan]Ingesting:[/bold cyan] {path}")
    console.print(f"  Embed model : {settings.embed_model}")
    console.print(f"  Store       : {settings.chroma_path_resolved}\n")

    try:
        ingest_path(path, store, settings)
    except RuntimeError as exc:
        err_console.print(str(exc))
        raise typer.Exit(1)


@app.command()
def chat() -> None:
    """Start an interactive chat session (type 'quit' or Ctrl-C to exit)."""
    from app.rag import answer

    store, settings = _get_store()

    if store.count() == 0:
        console.print(
            Panel(
                "[yellow]No documents indexed yet.[/yellow]\n"
                f"Run: [bold]python cli.py ingest <path>[/bold]",
                title="Empty store",
            )
        )
        raise typer.Exit(0)

    console.print(
        Panel(
            f"[cyan]Documents:[/cyan] {store.count()} chunks from {len(store.list_sources())} file(s)\n"
            f"[cyan]LLM model:[/cyan] {settings.llm_model}\n"
            f"[cyan]Top-k:[/cyan] {settings.top_k}\n\n"
            "Type [bold]quit[/bold] or press [bold]Ctrl-C[/bold] to exit.",
            title="[bold green]RAG Chat[/bold green]",
        )
    )

    while True:
        try:
            question = console.input("\n[bold yellow]You:[/bold yellow] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Bye![/dim]")
            break

        if question.lower() in {"quit", "exit", "q"}:
            console.print("[dim]Bye![/dim]")
            break

        if not question:
            continue

        console.print("\n[bold green]Assistant:[/bold green]")
        try:
            token_iter, citations = answer(question, store, settings)
            full_answer = ""
            for token in token_iter:
                console.print(token, end="")
                full_answer += token
                sys.stdout.flush()
            console.print()  # newline after streaming ends

            if citations:
                console.print("\n[dim]── Sources ──[/dim]")
                for cite in citations:
                    console.print(
                        f"  [cyan]{cite['source']}[/cyan], "
                        f"page [cyan]{cite['page']}[/cyan] "
                        f"[dim](distance: {cite['distance']})[/dim]"
                    )
        except RuntimeError as exc:
            err_console.print(f"\nError: {exc}")


@app.command()
def reset() -> None:
    """Wipe the entire vector store (cannot be undone)."""
    confirm = typer.confirm("This will delete ALL indexed documents. Continue?")
    if not confirm:
        console.print("[dim]Aborted.[/dim]")
        raise typer.Exit(0)

    store, settings = _get_store()
    store.reset()
    console.print(f"[green]Vector store cleared.[/green] Path: {settings.chroma_path_resolved}")


@app.command()
def status() -> None:
    """Show current vector store statistics."""
    store, settings = _get_store()

    table = Table(title="RAG Store Status", show_header=True)
    table.add_column("Key", style="cyan")
    table.add_column("Value")

    table.add_row("Chroma path", str(settings.chroma_path_resolved))
    table.add_row("Collection", settings.collection_name)
    table.add_row("Total chunks", str(store.count()))
    table.add_row("Embed model", settings.embed_model)
    table.add_row("LLM model", settings.llm_model)
    table.add_row("Top-k", str(settings.top_k))

    sources = store.list_sources()
    table.add_row("Indexed files", str(len(sources)))
    for src in sources:
        table.add_row("", f"  • {src}")

    console.print(table)


if __name__ == "__main__":
    app()
