"""文本切块服务 — TCM-aware text splitting."""

from __future__ import annotations

import math
import re

from app.services.text_normalization_service import to_simplified_medical

# ── TCM section header patterns ──────────────────────────────

# Matches common TCM book headers: 篇名, 目录, 简介, numbered chapters, etc.
_SECTION_HEADER_RE = re.compile(
    r"^(?:"
    r"(?:第[一二三四五六七八九十百千\d]+[篇章节卷])"       # 第一篇, 第3章
    r"|(?:篇名|目录|简介|概述|总论|附录|引言|序言|前言)"    # named sections
    r"|(?:卷[一二三四五六七八九十百千\d]+)"                  # 卷一, 卷3
    r"|(?:[一二三四五六七八九十]+[、.])"                     # 一、, 二.
    r"|(?:\d+[、.\s])"                                       # 1、, 2.
    r")"
    r"[^\n]*",
    re.MULTILINE,
)

# Sub-section markers within TCM texts
_SUB_SECTION_RE = re.compile(
    r"^(?:"
    r"【[^】]+】"                                             # 【主治】, 【功效】
    r"|(?:病因病机|辨证论治|临床表现|治法|方药|加减|按语)"
    r"|(?:组成|用法|功用|主治|方解|配伍|注意事项)"
    r")"
    r"[：:]*",
    re.MULTILINE,
)


class ChunkingService:
    """TCM-aware text chunking.

    Respects classical Chinese text structure by detecting section headers
    and splitting on character boundaries (not word boundaries).
    """

    def chunk_text(
        self,
        text: str,
        *,
        chunk_size: int = 512,
        overlap: int = 50,
    ) -> list[dict]:
        """Split *text* into chunks with metadata.

        Args:
            text: Full document text.
            chunk_size: Max characters per chunk (default 512).
            overlap: Overlap characters between chunks (default 50).

        Returns:
            List of dicts with keys: chunk_index, chunk_text, token_count,
            metadata_json (containing section, position, length).
        """
        normalized = re.sub(r"\n{3,}", "\n\n", text).strip()
        if not normalized:
            return []

        # ── 1. Detect section boundaries ────────────────────
        sections = self._split_into_sections(normalized)

        # ── 2. Chunk each section ───────────────────────────
        chunks: list[dict] = []
        chunk_index = 0

        for section_title, section_text in sections:
            paragraphs = [p.strip() for p in section_text.split("\n\n") if p.strip()]
            buffer = ""

            for paragraph in paragraphs:
                candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph

                if len(candidate) <= chunk_size:
                    buffer = candidate
                    continue

                # Flush current buffer
                if buffer:
                    chunks.append(self._build_chunk(
                        chunk_index, buffer,
                        section=section_title,
                        position=chunk_index,
                    ))
                    chunk_index += 1
                    # Overlap: carry tail of buffer into next
                    tail = buffer[-overlap:] if overlap < len(buffer) else buffer
                    carry_text = f"{tail}{paragraph}".strip()
                    split_pieces = self._split_oversized_text(
                        carry_text,
                        chunk_size=chunk_size,
                        overlap=overlap,
                    )
                    if len(split_pieces) == 1:
                        buffer = split_pieces[0]
                    else:
                        for piece in split_pieces:
                            chunks.append(self._build_chunk(
                                chunk_index, piece,
                                section=section_title,
                                position=chunk_index,
                            ))
                            chunk_index += 1
                        buffer = ""
                else:
                    # Paragraph itself exceeds chunk_size → character-level split
                    for piece in self._split_oversized_text(
                        paragraph,
                        chunk_size=chunk_size,
                        overlap=overlap,
                    ):
                        chunks.append(self._build_chunk(
                            chunk_index, piece,
                            section=section_title,
                            position=chunk_index,
                        ))
                        chunk_index += 1
                    buffer = ""

            # Flush remaining buffer for this section
            if buffer:
                chunks.append(self._build_chunk(
                    chunk_index, buffer,
                    section=section_title,
                    position=chunk_index,
                ))
                chunk_index += 1

        return chunks

    # ── Section detection ───────────────────────────────────

    def _split_into_sections(self, text: str) -> list[tuple[str, str]]:
        """Split text into (section_title, section_body) pairs.

        If no section headers are found, returns a single section with
        an empty title.
        """
        headers = list(_SECTION_HEADER_RE.finditer(text))

        if not headers:
            return [("", text)]

        sections: list[tuple[str, str]] = []

        # Content before first header
        pre = text[: headers[0].start()].strip()
        if pre:
            sections.append(("", pre))

        for i, match in enumerate(headers):
            title = match.group(0).strip()
            start = match.end()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
            body = text[start:end].strip()
            if body:
                sections.append((title, body))

        return sections if sections else [("", text)]

    @staticmethod
    def _split_oversized_text(
        text: str,
        *,
        chunk_size: int,
        overlap: int,
    ) -> list[str]:
        cleaned = text.strip()
        if not cleaned:
            return []
        if len(cleaned) <= chunk_size:
            return [cleaned]

        step = max(1, chunk_size - overlap)
        pieces: list[str] = []
        for start in range(0, len(cleaned), step):
            piece = cleaned[start: start + chunk_size].strip()
            if piece:
                pieces.append(piece)
        return pieces

    # ── Chunk builder ───────────────────────────────────────

    @staticmethod
    def _build_chunk(
        chunk_index: int,
        text: str,
        *,
        section: str = "",
        position: int = 0,
    ) -> dict:
        cleaned = text.strip()
        # Token estimate: for Chinese text, ~1 token per 1.5 chars
        token_count = math.ceil(len(cleaned) / 1.5)
        return {
            "chunk_index": chunk_index,
            "chunk_text": cleaned,
            "normalized_text": to_simplified_medical(cleaned),
            "token_count": token_count,
            "metadata_json": {
                "section": section,
                "position": position,
                "length": len(cleaned),
            },
        }


chunking_service = ChunkingService()
