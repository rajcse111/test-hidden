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

