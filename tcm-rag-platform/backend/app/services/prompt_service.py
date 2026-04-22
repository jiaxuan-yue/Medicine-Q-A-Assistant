"""Prompt 构造服务。"""

from __future__ import annotations

SYSTEM_PROMPT = """\
你是一位精通岭南食疗的 AI 调理师，擅长在古籍证据范围内为用户生成药食同源的代茶饮与煲汤建议。

## 核心原则
1. 你的回答必须严格基于 `retrieved_ancient_chunks` 中的古籍原文，不得脱离证据胡编乱造。
2. 你只能推荐药食同源、适合日常调养的材料，不得推荐有明显毒性、强烈攻伐性或需要专业处方管理的药物。
3. 你不是临床诊断医生，不得做疾病诊断、替代处方或承诺疗效。
4. 若证据不足以支持代茶饮或煲汤推荐，必须明确说明“当前古籍证据不足，无法稳妥推荐”，而不是编造。
5. 若古籍出现“两、钱、分”等古代剂量，请同时给出现代克数近似值，换算口径固定为：1两=30g，1钱=3g，1分=0.3g。

## 隐式判断要求
1. 先在内部判断用户真正想要的是哪一类回答：简短知识问答、轻度建议、还是个性化食疗推荐。
2. 这个判断过程不要直接展示给用户，不要输出你的推理链，只输出最终答案。
3. 默认优先短答，避免每次都展开成长篇大论；只有用户明确要求推荐方案，或确实需要结合多维上下文做判断时，才展开更多结构。
4. 如果用户只是寒暄、打招呼、感谢或确认在线状态，可以自然简短回应，不需要检索、不需要引用，也不要展开医学建议。

## 证据使用要求
1. 代茶饮和煲汤每一条建议都必须关联书名，如《本草纲目》。
2. 每一条建议都必须展示对应的古籍原文片段，并使用 `Raw：...` 格式展示。
3. 必须优先结合地点、天气湿度/气温、当前节气、用户体质来解释推荐理由；如果实时天气缺失，要明确说明“当前未接入实时天气，仅按节气与体质保守推荐”。

## 输出格式
请根据问题类型动态选择输出：
1. 若是简短知识问答，优先直接给结论 + 1-2 条关键依据 + 1 条风险提醒，不要强行输出“代茶饮/煲汤”板块。
2. 若是轻度建议型问题，可以用 2-4 个短段落回答，避免重复复述上下文。
3. 只有在用户明确要求代茶饮、煲汤、泡茶、凉茶、食疗推荐时，才输出完整的“简要判断 / 代茶饮 / 煲汤 / 风险提示”结构。

## 额外要求
1. 若当前天气或体质与古籍证据不完全匹配，宁可降低推荐强度，也不要强行组方。
2. 若你引用的原文仅说明单味材料功效，可以据此给出保守型食疗搭配，但必须明确说明“属于古籍线索延展，不等同原方照搬”。
3. 正文中不要单独列“引用来源”板块，但每条建议内部要自然写出《书名》与 `Raw`。
"""


class PromptService:
    def build_prompt(
        self,
        user_query: str,
        context_chunks: list[dict],
        conversation_history: list[dict] | None = None,
        case_profile_summary: str | None = None,
        answer_style: str = "standard",
        generation_context: dict | None = None,
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
        system_prompt = self._compose_system_prompt(generation_context)

        if answer_style == "chat":
            messages: list[dict] = [{"role": "system", "content": system_prompt}]
            if conversation_history:
                for msg in conversation_history[-4:]:
                    messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "## 对话模式\n"
                        "这是一次寒暄或简短对话，不需要检索古籍，不需要引用，不要展开成长篇医学说明。\n\n"
                        "## 回答要求\n"
                        "1. 直接自然回应即可。\n"
                        "2. 总篇幅尽量控制在 1-2 句。\n"
                        "3. 如果合适，可以轻轻引导用户继续描述具体症状或需求。\n\n"
                        f"## 用户问题\n{user_query}"
                    ),
                }
            )
            return messages

        if answer_style == "consult":
            messages = [{"role": "system", "content": system_prompt}]
            if conversation_history:
                for msg in conversation_history[-6:]:
                    messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "## 轻问诊模式\n"
                        "这是一次简单问答或生活化问诊，不需要检索古籍，不需要引用出处。\n\n"
                        "## 回答要求\n"
                        "1. 基于用户问题、基础病例和本轮补充信息，给出简短、自然、可执行的回答。\n"
                        "2. 总篇幅尽量控制在 2-4 句。\n"
                        "3. 若信息仍有限，要明确说明判断有限，并给 1-2 个最关键观察点。\n"
                        "4. 不要输出引用依据，不要假装查到了古籍原文。\n\n"
                        f"## 用户基础病例\n{case_profile_summary or '（当前未提供基础病例信息）'}\n\n"
                        f"## 本轮补充\n{(generation_context or {}).get('clarification_context') or '未额外补充'}\n\n"
                        f"## 环境上下文\n{(generation_context or {}).get('environmental_context') or '时间：未知 | 位置：未提供 | 天气：未获取'}\n\n"
                        f"## 用户问题\n{user_query}"
                    ),
                }
            )
            return messages

        # --- build context block ---
        retrieved_ancient_chunks = (generation_context or {}).get("retrieved_ancient_chunks") or []
        if retrieved_ancient_chunks:
            context_lines: list[str] = []
            for idx, chunk in enumerate(retrieved_ancient_chunks, start=1):
                title = chunk.get("book_title", "未知古籍")
                raw = chunk.get("raw", "")
                chunk_id = chunk.get("chunk_id", "")
                metadata = chunk.get("metadata", {}) or {}
                context_lines.append(
                    f"[{idx}] 《{title}》\n"
                    f"chunk_metadata: chunk_id={chunk_id or '-'}; metadata={metadata}\n"
                    f"Raw：{raw}"
                )
            context_block = "\n\n".join(context_lines)
        elif context_chunks:
            context_lines = []
            for idx, chunk in enumerate(context_chunks, start=1):
                title = chunk.get("doc_title", "未知古籍")
                text = chunk.get("text", chunk.get("snippet", ""))
                context_lines.append(
                    f"[{idx}] 《{title}》\n"
                    f"chunk_metadata: chunk_id={chunk.get('chunk_id', '-')}; metadata={chunk.get('metadata', {}) or {}}\n"
                    f"Raw：{text}"
                )
            context_block = "\n\n".join(context_lines)
        else:
            context_block = "（当前未检索到相关参考内容）"

        # --- assemble messages ---
        messages: list[dict] = [{"role": "system", "content": system_prompt}]

        # inject conversation history (keep recent turns)
        if conversation_history:
            for msg in conversation_history[-6:]:
                messages.append({"role": msg["role"], "content": msg["content"]})

        # user turn with embedded context
        profile_block = case_profile_summary or "（当前未提供基础病例信息）"
        weather_mcp_data = (generation_context or {}).get("weather_mcp_data") or {}
        current_solar_term = (generation_context or {}).get("current_solar_term") or "未提供"
        user_constitution = (generation_context or {}).get("user_constitution") or "未提供"
        environmental_context = (generation_context or {}).get("environmental_context") or "时间：未知 | 位置：未提供 | 天气：未获取"
        clarification_context = (generation_context or {}).get("clarification_context") or "未额外补充"
        temp_text = weather_mcp_data.get("temperature_c")
        humidity_text = weather_mcp_data.get("humidity_pct")
        weather_block = (
            f"地点：{weather_mcp_data.get('location', '未提供')}\n"
            f"气温：{temp_text if temp_text is not None else '未提供'}"
            f"{'℃' if temp_text is not None else ''}\n"
            f"湿度：{humidity_text if humidity_text is not None else '未提供'}"
            f"{'%' if humidity_text is not None else ''}\n"
            f"天气说明：{weather_mcp_data.get('condition', '未提供')}\n"
            f"数据来源：{weather_mcp_data.get('source', 'unknown')}"
        )
        style_instruction = ""
        if answer_style == "concise":
            style_instruction = (
                "\n\n## 回答风格要求\n"
                "请先在内部判断用户意图，但不要展示推理过程。"
                "当前问题默认按短答处理：直接给结论，补 1-2 条最关键依据，再给 1 条必要提醒。"
                "不要强行输出“简要判断/代茶饮/煲汤/风险提示”四段式。"
                "避免复述检索上下文，总篇幅尽量控制在 120-220 字。"
            )
        elif answer_style == "adaptive":
            style_instruction = (
                "\n\n## 回答风格要求\n"
                "请先在内部判断用户真正需要的是解释、判断还是建议，但不要展示推理链。"
                "默认使用 2-4 个短段落或极少量短条目作答。"
                "如果用户没有明确要方案，不要输出完整的代茶饮和煲汤板块。"
                "若必须给建议，也只给最关键的 1 个方向，避免过度展开。"
            )
        elif answer_style == "dietary":
            style_instruction = (
                "\n\n## 回答风格要求\n"
                "这是明确的食疗推荐请求，请输出“简要判断 / 代茶饮 / 煲汤 / 风险提示”结构。"
                "但整体要精炼：代茶饮最多 1-2 条，煲汤最多 1-2 条，避免冗长铺垫。"
                "每条建议都要带《书名》与 `Raw`，不要额外堆砌无关说明。"
            )

        user_content = (
            f"## Environmental Context\n{environmental_context}\n\n"
            f"## weather_mcp_data\n{weather_block}\n\n"
            f"## current_solar_term\n{current_solar_term}\n\n"
            f"## user_constitution\n{user_constitution}\n\n"
            f"## clarification_context\n{clarification_context}\n\n"
            f"## 用户基础病例\n{profile_block}\n\n"
            f"## retrieved_ancient_chunks\n{context_block}\n\n"
            f"## answer_style\n{answer_style}\n\n"
            f"## 用户问题\n{user_query}"
            f"{style_instruction}"
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

    def _compose_system_prompt(self, generation_context: dict | None) -> str:
        generation_context = generation_context or {}
        sections = [SYSTEM_PROMPT]

        long_term_profile = generation_context.get("long_term_profile") or {}
        short_term_memories = generation_context.get("short_term_syndrome_memories") or []
        short_term_guardrail = generation_context.get("short_term_guardrail") or ""

        sections.append(
            "## 用户长期体质画像\n"
            "长期画像代表相对稳定的体质与禁忌底盘；若本轮补充与长期画像冲突，优先相信本轮补充。"
        )
        sections.append(self._build_long_term_profile_block(long_term_profile))

        sections.append(
            "## 会话短期证候记忆\n"
            "这里只表示最近几轮的症候变化，必须同时参考状态标签：`当前未过期` 表示仍可作为近期判断依据，"
            "`已恢复` 不能当成当前症状，`已过期` 只能作为弱提示。"
        )
        sections.append(self._build_short_term_memory_block(short_term_memories))

        if short_term_guardrail:
            sections.append(f"## 短期护栏\n{short_term_guardrail}")

        return "\n\n".join(section for section in sections if section)

    @staticmethod
    def _build_long_term_profile_block(profile: dict) -> str:
        if not profile:
            return "（暂无长期体质画像，建议首次做体质测评）"

        top_scores = profile.get("top_scores") or []
        score_text = "、".join(f"{name}{score}分" for name, score in top_scores if score > 0) or "暂无明确评分"
        primary = profile.get("primary_constitution") or "未明确"
        secondary = "、".join(profile.get("secondary_constitutions") or []) or "无"
        allergies = "、".join(profile.get("allergy_history") or []) or "未记录"
        chronic = "、".join(profile.get("chronic_symptoms") or []) or "未记录"
        restrictions = "、".join(profile.get("dietary_restrictions") or []) or "未记录"
        assessed_at = profile.get("last_assessed_at") or "未记录"
        refresh_hint = profile.get("refresh_hint") or "建议结合反馈持续微调"
        tongue_summary = "；".join(
            part
            for part in [
                profile.get("tongue_color"),
                profile.get("tongue_coating"),
                profile.get("tongue_shape"),
                profile.get("tongue_constitution_hint"),
            ]
            if part
        ) or "未记录"
        return "\n".join(
            [
                f"- 主体质：{primary}",
                f"- 兼具体质：{secondary}",
                f"- 九种体质得分Top：{score_text}",
                f"- 过敏史：{allergies}",
                f"- 长期慢性症状：{chronic}",
                f"- 饮食禁忌：{restrictions}",
                f"- 舌诊记录：{tongue_summary}",
                f"- 最近测评：{assessed_at}",
                f"- 维护提示：{refresh_hint}",
            ]
        )

    @staticmethod
    def _build_short_term_memory_block(memories: list[dict]) -> str:
        if not memories:
            return "（暂无短期证候记忆）"
        lines = []
        for item in memories[:4]:
            summary = item.get("summary") or "近期不适"
            status = item.get("status_label") or item.get("status") or "状态未知"
            freshness = item.get("freshness_hint") or "时间未知"
            lines.append(f"- [{status} | {freshness}] {summary}")
        return "\n".join(lines)


prompt_service = PromptService()
