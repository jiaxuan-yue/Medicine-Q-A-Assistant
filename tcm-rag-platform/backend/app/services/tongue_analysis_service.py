"""舌像 AI 分析服务 — 调用视觉大模型进行中医舌诊。"""

from __future__ import annotations

import json

from app.core.logger import get_logger
from app.integrations.llm_client import llm_client

logger = get_logger(__name__)

TONGUE_ANALYSIS_PROMPT = """\
你是一位经验丰富的中医舌诊专家。请仔细观察这张舌像照片，按照中医舌诊理论进行分析。

请以纯 JSON 格式返回分析结果，不要包含任何其他文字或 markdown 代码块。格式如下：

{
    "tongue_color": "舌色（淡红/淡白/红/绛/紫/暗红）",
    "tongue_coating": "舌苔（薄白/白腻/黄腻/黄燥/少苔/无苔/薄黄/白厚等）",
    "tongue_shape": "舌形（正常/胖大/瘦薄/裂纹/齿痕/瘀点/歪斜/颤抖等，可多选，用中文顿号分隔）",
    "constitution_hint": "体质倾向（平和/气虚/阳虚/阴虚/痰湿/湿热/血瘀/气郁/特禀）",
    "raw_description": "一段 100-200 字的自然语言描述，包含舌色、舌苔、舌形和初步辨证建议"
}

注意：
1. tongue_shape 如果是多个，用中文顿号分隔，如 "胖大、齿痕"
2. 如果图片模糊或不是舌像，请在 raw_description 中说明
3. 请基于实际图片判断，不要凭空推断
"""


class TongueAnalysisService:
    async def analyze_tongue(self, image_path: str) -> dict[str, str | None]:
        """Analyze a tongue image and return structured analysis results."""
        try:
            content = await llm_client.analyze_image(
                image_path=str(image_path),
                prompt=TONGUE_ANALYSIS_PROMPT,
                max_tokens=1024,
            )
        except Exception:
            logger.warning("舌像 AI 分析失败，跳过分析步骤", exc_info=True)
            return {}

        return self._parse_analysis(content)

    @staticmethod
    def _parse_analysis(content: str) -> dict[str, str | None]:
        """Extract structured fields from the LLM response."""
        if not content:
            return {}

        text = content.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.removeprefix("```json").removeprefix("```").strip()
            if text.endswith("```"):
                text = text.removesuffix("```").strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("舌像 AI 分析返回非 JSON 内容: %s", text[:200])
            return {"raw_description": text}

        result: dict[str, str | None] = {}
        for key in ("tongue_color", "tongue_coating", "tongue_shape",
                     "constitution_hint", "raw_description"):
            value = data.get(key)
            if value and isinstance(value, str) and value.strip():
                result[key] = value.strip()
        return result


tongue_analysis_service = TongueAnalysisService()
