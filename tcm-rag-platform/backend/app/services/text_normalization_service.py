"""中医文本规范化工具：繁简转换、剂量注释等。"""

from __future__ import annotations

import re


_PHRASE_S2T = {
    "黄帝内经": "黃帝內經",
    "神农本草经": "神農本草經",
    "吴普本草": "吳普本草",
    "新修本草": "新修本草",
    "本草纲目": "本草綱目",
    "伤寒论": "傷寒論",
    "金匮要略": "金匱要略",
    "温病条辨": "溫病條辨",
    "当归": "當歸",
    "黄芪": "黃耆",
    "党参": "黨參",
    "白术": "白朮",
    "苍术": "蒼朮",
    "陈皮": "陳皮",
    "黄连": "黃連",
    "黄柏": "黃柏",
    "远志": "遠志",
    "续断": "續斷",
    "泽泻": "澤瀉",
    "荆芥": "荊芥",
    "龙骨": "龍骨",
    "牡蛎": "牡蠣",
    "灵芝": "靈芝",
    "车前子": "車前子",
    "鸡内金": "雞內金",
    "头痛": "頭痛",
    "发热": "發熱",
    "便秘": "便祕",
    "泄泻": "泄瀉",
    "眩晕": "眩暈",
    "水肿": "水腫",
    "呕吐": "嘔吐",
    "胸闷": "胸悶",
    "盗汗": "盜汗",
    "耳鸣": "耳鳴",
    "关节痛": "關節痛",
    "食欲不振": "食慾不振",
    "面色萎黄": "面色萎黃",
    "月经不调": "月經不調",
    "痛经": "痛經",
    "口疮": "口瘡",
    "烦躁": "煩躁",
    "脑萎缩": "腦萎縮",
    "凉茶": "涼茶",
}

_CHAR_S2T = {
    "当": "當",
    "归": "歸",
    "黄": "黃",
    "术": "朮",
    "陈": "陳",
    "党": "黨",
    "连": "連",
    "远": "遠",
    "续": "續",
    "断": "斷",
    "泽": "澤",
    "荆": "荊",
    "龙": "龍",
    "蛎": "蠣",
    "灵": "靈",
    "车": "車",
    "鸡": "雞",
    "头": "頭",
    "发": "發",
    "泻": "瀉",
    "晕": "暈",
    "肿": "腫",
    "呕": "嘔",
    "闷": "悶",
    "盗": "盜",
    "鸣": "鳴",
    "关": "關",
    "节": "節",
    "欲": "慾",
    "经": "經",
    "调": "調",
    "疮": "瘡",
    "烦": "煩",
    "凉": "涼",
    "书": "書",
}

_PHRASE_T2S = {value: key for key, value in _PHRASE_S2T.items()}
_CHAR_T2S = {value: key for key, value in _CHAR_S2T.items()}

_CHINESE_NUMERALS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "半": 0.5,
}

_UNIT_TO_GRAMS = {
    "两": 30.0,
    "兩": 30.0,
    "钱": 3.0,
    "錢": 3.0,
    "分": 0.3,
}

_DOSAGE_RE = re.compile(
    r"(?<![0-9A-Za-z约約克g（(])(?P<num>半|[一二三四五六七八九十百两兩\d]+)\s*(?P<unit>[两兩钱錢分])(?!\s*[（(]?(?:约|約)?\s*\d+(?:\.\d+)?\s*(?:克|g))"
)


def _apply_phrase_map(text: str, phrase_map: dict[str, str]) -> str:
    normalized = text
    for source, target in sorted(phrase_map.items(), key=lambda item: len(item[0]), reverse=True):
        normalized = normalized.replace(source, target)
    return normalized


def _apply_char_map(text: str, char_map: dict[str, str]) -> str:
    return "".join(char_map.get(char, char) for char in text)


def to_traditional_medical(text: str) -> str:
    normalized = _apply_phrase_map(text, _PHRASE_S2T)
    return _apply_char_map(normalized, _CHAR_S2T)


def to_simplified_medical(text: str) -> str:
    normalized = _apply_phrase_map(text, _PHRASE_T2S)
    return _apply_char_map(normalized, _CHAR_T2S)


def expand_script_variants(text: str) -> list[str]:
    variants: list[str] = []
    for candidate in (text, to_simplified_medical(text), to_traditional_medical(text)):
        if candidate and candidate not in variants:
            variants.append(candidate)
    return variants


def _parse_number(raw: str) -> float | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        return float(raw)
    if raw == "半":
        return 0.5
    if raw in _CHINESE_NUMERALS:
        return float(_CHINESE_NUMERALS[raw])
    if raw == "十":
        return 10.0
    if raw.startswith("十") and len(raw) == 2 and raw[1] in _CHINESE_NUMERALS:
        return 10.0 + float(_CHINESE_NUMERALS[raw[1]])
    if raw.endswith("十") and len(raw) == 2 and raw[0] in _CHINESE_NUMERALS:
        return float(_CHINESE_NUMERALS[raw[0]]) * 10.0
    if len(raw) == 3 and raw[1] == "十" and raw[0] in _CHINESE_NUMERALS and raw[2] in _CHINESE_NUMERALS:
        return float(_CHINESE_NUMERALS[raw[0]]) * 10.0 + float(_CHINESE_NUMERALS[raw[2]])
    return None


def _format_grams(value: float) -> str:
    rounded = round(value, 1)
    if float(rounded).is_integer():
        return str(int(rounded))
    return f"{rounded:.1f}"


def annotate_ancient_dosage(text: str) -> str:
    """Annotate traditional dosage units with approximate gram values."""
    if not text:
        return text

    def _replace(match: re.Match[str]) -> str:
        num_text = match.group("num")
        unit = match.group("unit")
        amount = _parse_number(num_text)
        unit_factor = _UNIT_TO_GRAMS.get(unit)
        if amount is None or unit_factor is None:
            return match.group(0)
        grams = amount * unit_factor
        return f"{match.group(0)}（约{_format_grams(grams)}克）"

    return _DOSAGE_RE.sub(_replace, text)
