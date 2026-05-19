from dataclasses import dataclass


@dataclass(frozen=True)
class PromptContext:
    mode: str
    current_question: str
    transcript: str
    screen_context: str | None = None


class PromptBuilder:
    def build(self, context: PromptContext) -> list[dict[str, str]]:
        system = self._system_prompt(context.mode)
        user_parts = [f"Question:\n{context.current_question.strip()}"]
        if context.screen_context:
            user_parts.append(f"Screen context:\n{context.screen_context.strip()}")
        # Include prior transcript only if it contains more than the current question
        history = context.transcript.strip()
        if history and history != context.current_question.strip():
            user_parts.append(f"Transcript context (for background only):\n{history}")
        user_parts.append("Provide a concise, high-signal answer.")
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(part for part in user_parts if part)},
        ]

    def _system_prompt(self, mode: str) -> str:
        prompts = {
            "interview": (
                "You are a discreet interview coach. Give concise answer drafts, STAR framing when useful, "
                "and avoid rambling. Do not fabricate personal experience; provide adaptable phrasing."
            ),
            "coding": (
                "You are a coding interview assistant. Provide hints, complexity analysis, edge cases, "
                "and implementation direction without overwhelming the candidate."
            ),
            "system-design": (
                "You are a system design interview assistant. Focus on requirements, APIs, data model, "
                "scaling bottlenecks, reliability, tradeoffs, and crisp diagrams described in text."
            ),
        }
        return prompts.get(mode, prompts["interview"])

