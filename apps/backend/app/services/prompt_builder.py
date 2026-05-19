from dataclasses import dataclass


@dataclass(frozen=True)
class PromptContext:
    mode: str
    transcript: str
    screen_context: str | None = None


class PromptBuilder:
    def build(self, context: PromptContext) -> list[dict[str, str]]:
        system = self._system_prompt(context.mode)
        user_parts = ["Live interview transcript:", context.transcript.strip()]
        if context.screen_context:
            user_parts.extend(["Screen/OCR context:", context.screen_context.strip()])
        user_parts.append("Respond with concise, high-signal guidance suitable for a live interview.")
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

