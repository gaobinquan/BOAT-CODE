"""意图解析（LLM）：自然语言 → IntentParams；失败返回 None（降级）。"""
from __future__ import annotations

import json
from typing import List, Optional

from ..core.intent import IntentParams
from ..dataloader import GameData
from .client import LLMClient, LLMUnavailable

SYSTEM_PROMPT = """你是《超时空星舰》(Pixel Starships) 的 AI 指令顾问。
把玩家的自然语言意图解析为结构化 JSON，只能输出 JSON：
{"priority": ["目标房间id列表"], "mode": "focus_fire|spread|auto", "conserve_ammo": true|false, "protect_rooms": ["我方房间id"]}
可用的敌方目标房间 id（按威胁度排序）已给出；仅可使用给定 id，不要编造。
priority 最多 3 个；conserve_ammo 仅在玩家提到省弹/弹药不够时为 true；
protect_rooms 仅在玩家提到保护某个房间时填写。"""


class IntentParser:
    def __init__(self, data: GameData):
        self.data = data

    def parse(self, client: LLMClient, text: str, level: int) -> Optional[IntentParams]:
        enemy_ids = sorted(self.data.enemy_rooms.get(level, {}).keys())
        my_ids = self.data.get_level(level).available_rooms
        user = (
            f"舰船等级: {level}\n"
            f"敌方目标房间 id: {enemy_ids}\n"
            f"我方房间 id: {my_ids}\n"
            f"玩家意图: {text}"
        )
        try:
            raw = client.chat_json(SYSTEM_PROMPT, user)
        except LLMUnavailable:
            return None
        if not isinstance(raw, dict):
            return None

        priority = [r for r in raw.get("priority", []) if r in enemy_ids]
        protect = [r for r in raw.get("protect_rooms", []) if r in my_ids]
        mode = raw.get("mode", "auto")
        if mode not in ("focus_fire", "spread", "auto"):
            mode = "auto"
        return IntentParams(
            priority=priority,
            mode=mode,
            conserve_ammo=bool(raw.get("conserve_ammo", False)),
            protect_rooms=protect,
        )
