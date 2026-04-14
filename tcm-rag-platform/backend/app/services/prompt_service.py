"""Prompt 构造服务。"""

from __future__ import annotations

SYSTEM_PROMPT = """\
你是一个专业的中医药知识检索助手。你的回答必须**严格基于以下检索到的参考内容**，不得超出其范围进行臆测或推断。

## 安全约束
1. **禁止提供诊断**：你不是医生，不得对用户的症状做出明确诊断或下定论。
2. **始终建议就医**：在回答末尾务必提醒用户"如有不适，请及时就医，线上内容仅供学习参考"。
3. **仅基于检索内容回答**：如果检索内容中没有相关信息，请明确告知用户"当前知识库未检索到足够信息"，而非编造回答。
4. **不推荐具体处方**：不得为个体推荐具体处方或用药剂量，仅可引用古籍原文供参考。
5. **标注来源**：回答中引用古籍内容时，在正文中以行内方式注明出处（如"《伤寒论》记载：……"），但不要单独列出"来源引用"板块。

## 输出格式
请严格按照以下四个板块组织回答，每个板块以标题开头：

1. **症状分析**：基于用户问题和检索内容，概述相关症状或知识点的中医理解。
2. **可能相关的证候/知识点**：列出检索内容中与问题相关的证候、方剂、药物或理论。
3. **建议参考方向**：为用户进一步学习或就医提供方向性建议（不做诊断）。
4. **风险提示**：说明该信息的局限性，提醒用户就医。

**重要**：回答中不要包含"来源引用"或"引用来源"板块，系统会自动在回答下方展示引用来源卡片，无需在正文中重复列出。在正文中引用古籍内容时，直接以行内方式注明出处即可（如"《伤寒论》记载：……"）。
"""


class PromptService:
    def build_prompt(
        self,
        user_query: str,
        context_chunks: list[dict],
        conversation_history: list[dict] | None = None,
        case_profile_summary: str | None = None,
    ) -> list[dict]:
        """Build the messages list ready to send to the LLM.

        Args:
            user_query: The user's original question.
            context_chunks: Retrieved chunks, each with keys: text, doc_title, doc_id
                            (and optionally chunk_id, score, etc.).
            conversation_history: Optional list of prior messages
                                  [{"role": "user"|"assistant", "content": "..."}].

        Returns:
            A list of message dicts: [{"role": ..., "content": ...}]
        """
        # --- build context block ---
        if context_chunks:
            context_lines: list[str] = []
            for idx, chunk in enumerate(context_chunks, start=1):
                title = chunk.get("doc_title", "未知文献")
                text = chunk.get("text", chunk.get("snippet", ""))
                context_lines.append(f"[{idx}] 《{title}》\n{text}")
            context_block = "\n\n".join(context_lines)
        else:
            context_block = "（当前未检索到相关参考内容）"

        # --- assemble messages ---
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

        # inject conversation history (keep recent turns)
        if conversation_history:
            for msg in conversation_history[-6:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        # user turn with embedded context
        profile_block = case_profile_summary or "（当前未提供基础病例信息）"
        user_content = (
            f"## 用户基础病例\n{profile_block}\n\n"
            f"## 检索到的参考内容\n{context_block}\n\n"
            f"## 用户问题\n{user_query}"
        )
        messages.append({"role": "user", "content": user_content})

        return messages

    # Keep backward-compatible legacy signature used by rag_service
    def build_prompt_legacy(self, query: str, query_bundle: dict, contexts: list[dict]) -> str:
        context_block = "\n\n".join(
            [
                f"[{index}] {item['doc_title']}\n{item['snippet']}"
                for index, item in enumerate(contexts, start=1)
            ]
        )
        entities = "、".join(query_bundle["entities"]) if query_bundle["entities"] else "未识别"
        return (
            "你是中医药知识服务助手，只能基于引用内容回答。\n"
            f"用户问题：{query}\n"
            f"识别实体：{entities}\n"
            f"检索上下文：\n{context_block}"
        )


prompt_service = PromptService()
