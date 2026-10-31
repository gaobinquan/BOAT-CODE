"""威胁评估器：静态威胁度表 + 我方武器适配修正（纯函数）。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ThreatRow:
    room_id: str
    score: float
    base: int
    reason: str


class ThreatEvaluator:
    """威胁度排序；按我方武器特点修正权重。"""

    # 武器适配修正：我方武器类别 → {敌方房间 → 系数}
    WEAPON_MODIFIERS: Dict[str, Dict[str, float]] = {
        # 激光高射速 → 拆低血量房间/护盾快
        "laser": {"shield_room": 1.2},
        # 护盾破坏者 → 对护盾加成
        "pp": {"shield_room": 1.5},
        # 导弹高单发 → 高威胁目标更值
        "missile": {"engine_room": 1.2, "power_room": 1.1},
        # 防空打战机，不参与房间威胁
        "aa": {},
    }

    def evaluate(
        self,
        threat_table: Dict[str, int],
        my_weapons: List[str],       # 我方武器 room_id 列表
        enemy_room_ids: List[str],
    ) -> List[ThreatRow]:
        rows: List[ThreatRow] = []
        for rid in enemy_room_ids:
            base = threat_table.get(rid, 3)
            score = float(base)
            reasons = [f"基础威胁 {base}"]
            for w in my_weapons:
                mods = self.WEAPON_MODIFIERS.get(w, {})
                if rid in mods:
                    score *= mods[rid]
                    reasons.append(f"{w} 适配 ×{mods[rid]}")
            rows.append(ThreatRow(rid, round(score, 2), base, "，".join(reasons)))
        rows.sort(key=lambda r: (-r.score, r.room_id))
        return rows
