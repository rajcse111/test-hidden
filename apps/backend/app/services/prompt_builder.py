from dataclasses import dataclass, field


@dataclass(frozen=True)
class PromptContext:
    mode: str
    current_question: str
    transcript: str
    screen_context: str | None = None
    rag_context: str | None = None   # labeled document excerpts from RAG retrieval
    rag_searched: bool = False        # True when RAG was attempted (hit or miss)


# Appended when RAG retrieval returned relevant chunks.
# Instructs the LLM to prefer the excerpts but allows supplementing from
# general knowledge — avoids the LLM refusing to answer when chunks are partial.
_RAG_HIT_ADDENDUM = """

You have been provided with relevant document excerpts below. When answering:
1. Ground your answer primarily in these excerpts and cite them as [filename, page].
2. If the excerpts are incomplete, supplement with your general knowledge and clearly distinguish what comes from the documents versus your own knowledge.

Document excerpts:
{rag_context}"""

# Appended when RAG is enabled and was searched but no relevant chunks were found.
# Makes explicit that the LLM should answer freely from general knowledge.
_RAG_MISS_ADDENDUM = """

No relevant documents were found in the knowledge base for this question. Answer from your general knowledge."""


class PromptBuilder:
    def build(self, context: PromptContext) -> list[dict[str, str]]:
        system = self._system_prompt(context.mode, context.rag_context, context.rag_searched)
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

    def _system_prompt(self, mode: str, rag_context: str | None = None, rag_searched: bool = False) -> str:
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
            "senior-fullstack": (
                "You are a Senior Full Stack Engineer and Architect with 14+ years of professional "
                "enterprise experience. Your expertise spans Java (Core Java, Collections, Concurrency, "
                "JVM internals, Spring Boot, Microservices), Angular (enterprise-scale applications, "
                "performance optimization), SQL (database design, indexing, query optimisation, "
                "performance tuning), DevOps (CI/CD, Docker, Kubernetes, cloud platforms, monitoring), "
                "System Design, Distributed Systems, Design Patterns, and Security Best Practices.\n\n"
                "When you receive any technical topic, keyword, or question — even brief inputs like "
                "'Kafka partition', 'Spring transaction', or 'Angular change detection' — interpret it "
                "as a technical interview question and answer from the perspective of a highly experienced "
                "senior engineer with real production exposure.\n\n"
                "Structure every response as follows:\n"
                "1. **30-second answer** — Concise, quotable interview answer.\n"
                "2. **Deep explanation** — Core concepts, internals, how it works.\n"
                "3. **Real-world scenario** — Concrete production use case or experience.\n"
                "4. **Architecture & trade-offs** — Scalability, reliability, performance, alternatives.\n"
                "5. **Common pitfalls** — What breaks in production and how to avoid it.\n"
                "6. **Follow-up questions** — 2–3 questions an interviewer would ask next.\n\n"
                "Calibrate all answers to reflect production-grade enterprise experience:\n"
                "- For coding questions: production-quality examples, complexity analysis, design decisions, alternatives.\n"
                "- For system design: requirements, API design, data model, scalability, reliability, observability, security, deployment.\n"
                "- For Angular: enterprise patterns, change detection strategies, lazy loading, state management, bundle optimisation.\n"
                "- For SQL: indexing strategies, execution plans, normalisation vs denormalisation, locking, transactions, tuning.\n"
                "- For DevOps: pipeline design, containerisation best practices, orchestration, IaC, and monitoring.\n"
                "Always assume the candidate has solved these problems in production at scale."
            ),
        }
        base = prompts.get(mode, prompts["interview"])
        if rag_context:
            base += _RAG_HIT_ADDENDUM.format(rag_context=rag_context)
        elif rag_searched:
            base += _RAG_MISS_ADDENDUM
        return base

