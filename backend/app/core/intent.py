"""意图参数：快捷选项映射 + LLM 解析结果结构（确定性默认值）。

LLM 将自然语言解析为 IntentParams；失败时用快捷选项/默认参数。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class IntentParams:
    priority: List[str] = field(default_factory=list)   # 敌方目标房间优先级
    mode: str = "auto"          # focus_fire / spread / auto
    conserve_ammo: bool = False
    protect_rooms: List[str] = field(default_factory=list)  # 我方要保护的房间


QUICK_PICKS: Dict[str, IntentParams] = {
    "拆盾优先": IntentParams(priority=["shield_room"], mode="focus_fire"),
    "压制维修": IntentParams(priority=["medbay", "teleport"], mode="focus_fire"),
    "集火引擎": IntentParams(priority=["engine_room"], mode="focus_fire"),
    "保电力室": IntentParams(protect_rooms=["reactor"], mode="auto"),
    "省弹打法": IntentParams(
        priority=["engine_room", "power_room"], mode="focus_fire", conserve_ammo=True
    ),
}

DEFAULT_INTENT = IntentParams()


def resolve_intent(quick_pick: str | None, llm_params: IntentParams | None) -> IntentParams:
    """LLM 解析成功则用 LLM 结果，否则快捷选项，再否则默认。"""
    if llm_params is not None:
        return llm_params
    if quick_pick and quick_pick in QUICK_PICKS:
        return QUICK_PICKS[quick_pick]
    return DEFAULT_INTENT
