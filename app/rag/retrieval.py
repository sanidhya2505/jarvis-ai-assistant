"""
Retrieval-Augmented Generation: the "file-first" question answering engine.

Implements spec section 2's critical rule directly:
  - If the answer exists in the uploaded files -> use file info first and
    cite the source file (+ page number where available).
  - If it does not exist in the files -> clearly say so, and do NOT quietly
    fall back to the model's general knowledge unless the caller explicitly
    allows it (`allow_general_knowledge=True`, wired to the
    "enable_web_search"/explicit-ask paths in the command router).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.rag.vector_store import semantic_search
from app.ai.llm_client import chat, LLMUnavailableError

# Below this similarity threshold (i.e. distance above it) we treat the
# match as too weak to count as "found in your files".
_RELEVANCE_DISTANCE_THRESHOLD = 0.8


@dataclass
class RAGAnswer:
    answer: str
    found_in_files: bool
    sources: list[dict] = field(default_factory=list)
    used_general_knowledge: bool = False


def answer_from_knowledge_base(
    question: str, top_k: int = 5, allow_general_knowledge: bool = False
) -> RAGAnswer:
    hits = semantic_search(question, top_k=top_k)
    relevant = [h for h in hits if h.get("distance") is None or h["distance"] <= _RELEVANCE_DISTANCE_THRESHOLD]

    if not relevant:
        if allow_general_knowledge:
            try:
                text = chat(
                    system_prompt=(
                        "You are JARVIS, a personal assistant. The user's uploaded files did "
                        "not contain relevant information for this question. Answer from your "
                        "general knowledge, and explicitly say you're doing so."
                    ),
                    user_prompt=question,
                )
                return RAGAnswer(answer=text, found_in_files=False, used_general_knowledge=True)
            except LLMUnavailableError as exc:
                return RAGAnswer(answer=str(exc), found_in_files=False)
        return RAGAnswer(
            answer="I couldn't find that information in your uploaded files.",
            found_in_files=False,
        )

    context_blocks = []
    for h in relevant:
        meta = h["metadata"]
        page = meta.get("page_number")
        page_str = f", page {page}" if page and page != -1 else ""
        context_blocks.append(f"[Source: {meta.get('filename')}{page_str}]\n{h['text']}")
    context = "\n\n---\n\n".join(context_blocks)

    try:
        text = chat(
            system_prompt=(
                "You are JARVIS, a personal assistant. Answer the user's question using ONLY "
                "the provided file excerpts as your source of truth. Cite the source filename "
                "(and page number if given) inline, e.g. 'According to your Project_Docs.pdf...'. "
                "If the excerpts don't actually answer the question, say so plainly instead of "
                "guessing."
            ),
            user_prompt=f"Question: {question}\n\nFile excerpts:\n{context}",
        )
    except LLMUnavailableError:
        # No LLM configured — still useful: return the raw best-matching excerpt.
        top = relevant[0]
        text = (
            f"(No AI provider configured — showing the most relevant excerpt instead.)\n\n"
            f"From {top['metadata'].get('filename')}: {top['text'][:600]}"
        )

    return RAGAnswer(
        answer=text,
        found_in_files=True,
        sources=[{"filename": h["metadata"].get("filename"), "page": h["metadata"].get("page_number")} for h in relevant],
    )
