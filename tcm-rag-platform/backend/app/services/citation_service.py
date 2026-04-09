"""引用生成服务。"""

from __future__ import annotations


class CitationService:
    def build_citations(
        self,
        chunks_used: list[dict],
        answer_text: str = "",
        limit: int = 5,
    ) -> list[dict]:
        """Map retrieved chunks to citation objects.

        If *answer_text* is provided, only chunks whose content appears
        (even partially) in the answer are included.  Otherwise all
        chunks up to *limit* are returned.

        Each citation dict:
            doc_id, doc_title, excerpt, chunk_id, location
        """
        citations: list[dict] = []
        for item in chunks_used:
            text = item.get("text", item.get("snippet", ""))
            chunk_id = item.get("chunk_id", "")
            doc_title = item.get("doc_title", "")
            doc_id = item.get("doc_id", "")
            location = item.get("location", item.get("source", ""))

            # If answer text available, check whether this chunk was
            # actually referenced (use a short excerpt match).
            if answer_text:
                # Consider referenced if any 8-char substring of chunk
                # text appears in the answer, or if doc_title is mentioned.
                referenced = (
                    doc_title in answer_text
                    or any(
                        text[i : i + 8] in answer_text
                        for i in range(0, max(1, len(text) - 7), 8)
                    )
                )
                if not referenced:
                    continue

            excerpt = text[:120] + ("..." if len(text) > 120 else "")

            citations.append(
                {
                    "doc_id": doc_id,
                    "doc_title": doc_title,
                    "excerpt": excerpt,
                    "chunk_id": chunk_id,
                    "location": location,
                    # backward-compat key used by existing schemas
                    "text": text[:200],
                }
            )

            if len(citations) >= limit:
                break

        # If strict matching yielded nothing, fall back to top chunks
        if not citations and chunks_used:
            for item in chunks_used[:limit]:
                text = item.get("text", item.get("snippet", ""))
                citations.append(
                    {
                        "doc_id": item.get("doc_id", ""),
                        "doc_title": item.get("doc_title", ""),
                        "excerpt": text[:120],
                        "chunk_id": item.get("chunk_id", ""),
                        "location": item.get("location", item.get("source", "")),
                        "text": text[:200],
                    }
                )

        return citations


citation_service = CitationService()
