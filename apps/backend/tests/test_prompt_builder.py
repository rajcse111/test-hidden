from app.services.prompt_builder import PromptBuilder, PromptContext


def test_prompt_builder_includes_transcript_and_context() -> None:
    messages = PromptBuilder().build(
        PromptContext(mode="coding", transcript="How do I reverse a linked list?", screen_context="Python problem")
    )
    assert messages[0]["role"] == "system"
    assert "coding interview" in messages[0]["content"]
    assert "reverse a linked list" in messages[1]["content"]
    assert "Python problem" in messages[1]["content"]

