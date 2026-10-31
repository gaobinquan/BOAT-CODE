"""LLM 润色：战略总述/说明文字；失败返回 None（降级用内置模板）。"""
from __future__ import annotations

from typing import Optional

from .client import LLMClient, LLMUnavailable

POLISH_PROMPT = """你是《超时空星舰》(Pixel Starships) 的战术解说员。
把下面这段生成的战略说明改写成 2-4 句玩家易懂的中文讲解，
保留全部关键信息（目标、轮数、弹药、电力），不要添加任何新数据，不要用列表。"""


def polish_explanation(client: LLMClient, strategy: str) -> Optional[str]:
    try:
        text = client.chat(POLISH_PROMPT, strategy)
        return text.strip() if text.strip() else None
    except LLMUnavailable:
        return None
