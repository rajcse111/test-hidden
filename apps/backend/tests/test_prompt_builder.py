from app.services.prompt_builder import PromptBuilder, PromptContext


def test_prompt_builder_includes_current_question_and_context() -> None:
    messages = PromptBuilder().build(
        PromptContext(
            mode="coding",
            current_question="How do I reverse a linked list?",
            transcript="How do I reverse a linked list?",
            screen_context="Python problem",
        )
    )
    assert messages[0]["role"] == "system"
    assert "coding interview" in messages[0]["content"]
    assert "reverse a linked list" in messages[1]["content"]
    assert "Python problem" in messages[1]["content"]


def test_prompt_builder_current_question_leads_user_message() -> None:
    """Current question must appear before history so each prompt has a unique prefix."""
    messages = PromptBuilder().build(
        PromptContext(
            mode="interview",
            current_question="Tell me about yourself",
            transcript="What is polymorphism?\nTell me about yourself",
        )
    )
    user_content = messages[1]["content"]
    assert user_content.index("Tell me about yourself") < user_content.index("What is polymorphism?")


def test_prompt_builder_omits_history_when_only_current_question() -> None:
    """No redundant history section when the transcript equals the current question."""
    messages = PromptBuilder().build(
        PromptContext(
            mode="interview",
            current_question="What is your greatest strength?",
            transcript="What is your greatest strength?",
        )
    )
    user_content = messages[1]["content"]
    assert "Transcript context" not in user_content


# ---------------------------------------------------------------------------
# RAG context states
# ---------------------------------------------------------------------------

def test_rag_hit_includes_addendum() -> None:
    """RAG hit: system prompt includes the hit addendum with document excerpts."""
    messages = PromptBuilder().build(
        PromptContext(
            mode="interview",
            current_question="Tell me about the project?",
            transcript="Tell me about the project?",
            rag_context="[1] Source: handbook.pdf, Page: 3\nProject overview content.",
            rag_searched=True,
        )
    )
    system = messages[0]["content"]
    assert "handbook.pdf" in system
    assert "Project overview content" in system
    assert "Ground your answer" in system


def test_rag_hit_allows_general_knowledge_supplement() -> None:
    """RAG hit addendum must NOT instruct the LLM to refuse general knowledge."""
    messages = PromptBuilder().build(
        PromptContext(
            mode="interview",
            current_question="What is SOLID?",
            transcript="What is SOLID?",
            rag_context="[1] Source: notes.pdf, Page: 1\nSOLID principles overview.",
            rag_searched=True,
        )
    )
    system = messages[0]["content"]
    # Old instruction was "do not answer from general knowledge" — must be gone
    assert "do not answer from general knowledge" not in system.lower()
    # New instruction should allow supplementing
    assert "supplement" in system.lower() or "general knowledge" in system.lower()


def test_rag_miss_includes_fallback_note() -> None:
    """RAG miss: system prompt explicitly tells the LLM to answer from general knowledge."""
    messages = PromptBuilder().build(
        PromptContext(
            mode="coding",
            current_question="How does quicksort work?",
            transcript="How does quicksort work?",
            rag_context=None,
            rag_searched=True,
        )
    )
    system = messages[0]["content"]
    assert "No relevant documents" in system
    assert "general knowledge" in system.lower()


def test_rag_disabled_plain_prompt() -> None:
    """RAG disabled (rag_searched=False): no RAG addendum of any kind."""
    messages = PromptBuilder().build(
        PromptContext(
            mode="coding",
            current_question="Explain binary search.",
            transcript="Explain binary search.",
            rag_context=None,
            rag_searched=False,
        )
    )
    system = messages[0]["content"]
    assert "Document excerpts" not in system
    assert "No relevant documents" not in system
    assert "general knowledge" not in system.lower()


# ---------------------------------------------------------------------------
# senior-fullstack mode
# ---------------------------------------------------------------------------

def test_senior_fullstack_system_prompt_contains_key_markers() -> None:
    """senior-fullstack mode must contain structural and persona markers."""
    messages = PromptBuilder().build(
        PromptContext(
            mode="senior-fullstack",
            current_question="Kafka partition",
            transcript="Kafka partition",
        )
    )
    system = messages[0]["content"]
    assert "14+ years" in system
    assert "30-second answer" in system
    assert "trade-offs" in system.lower() or "trade-offs" in system
    assert "Common pitfalls" in system
    assert "Follow-up questions" in system


def test_unknown_mode_falls_back_to_interview() -> None:
    """Unrecognised mode strings must silently fall back to the interview prompt."""
    messages = PromptBuilder().build(
        PromptContext(
            mode="nonexistent-mode",
            current_question="What is encapsulation?",
            transcript="What is encapsulation?",
        )
    )
    system = messages[0]["content"]
    assert "interview coach" in system

