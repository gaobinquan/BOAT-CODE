"""攻击效率评估器（纯函数）。

攻击效率分 = 威胁度 ÷ 击破成本(轮数×装填时间×弹药系数) × 修正系数
连锁收益修正：拆盾全舰效率↑、打电力室瘫痪敌舰、打引擎防逃跑
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..dataloader import GameData
from .ammo_planner import AmmoPlanner


@dataclass
class EfficiencyRow:
    room_id: str
    score: float
    threat: int
    volleys_to_kill: float
    kill_time_sec: float
    ammo_cost: int
    reason: str
    warnings: List[str] = field(default_factory=list)


# 连锁收益修正
CHAIN_MODIFIERS: Dict[str, Dict[str, float]] = {
    "shield_room": {"factor": 1.2, "reason": "拆盾后全舰效率提升"},
    "power_room": {"factor": 1.2, "reason": "瘫痪全舰电力"},
    "engine_room": {"factor": 1.1, "reason": "打断机动与逃跑"},
}


class EfficiencyEvaluator:
    """对敌方各房间计算攻击效率分并排序。"""

    def __init__(self, data: GameData):
        self.data = data
        self.ammo = AmmoPlanner()

    def evaluate(
        self,
        level: int,
        weapon: dict,               # 我方武器统计 {id, name, damage, volley, reload_sec, ammo}
        threat_scores: Dict[str, float],   # room_id → 威胁分（来自 ThreatEvaluator）
        target_candidates: Optional[List[str]] = None,
    ) -> List[EfficiencyRow]:
        rows: List[EfficiencyRow] = []
        scenario = self.data.scenario_of(level)
        candidates = target_candidates or list(self.data.enemy_rooms[level].keys())
        for rid in candidates:
            stats = self.data.enemy_room_stats(level, rid)
            if stats is None:
                continue
            target = {
                "id": rid, "name": self._room_name(rid),
                "hp": stats.hp, "armor_mod": stats.armor_mod,
                "repair_per_sec": stats.repair_per_sec,
            }
            am = self.ammo.plan(weapon, target, {
                "duration_sec": scenario.duration_sec,
                "ammo_assumption": scenario.ammo_assumption,
            })
            threat = threat_scores.get(rid, self.data.threat_of(rid))
            # 成本 = 轮数 × 装填时间（秒）；+1 防除零
            cost = am.volleys_to_kill * weapon["reload_sec"] + 1.0
            ammo_factor = 1.0
            if weapon.get("ammo"):
                ammo_factor = 1.0 + am.ammo_cost / max(weapon["ammo"], 1) * 0.3
            score = threat / cost * 100 / ammo_factor

            reasons = [f"威胁{threat}", f"击破需{am.volleys_to_kill}轮"]
            if rid in CHAIN_MODIFIERS:
                ch = CHAIN_MODIFIERS[rid]
                score *= ch["factor"]
                reasons.append(ch["reason"])
            rows.append(EfficiencyRow(
                room_id=rid,
                score=round(score, 2),
                threat=threat,
                volleys_to_kill=am.volleys_to_kill,
                kill_time_sec=am.kill_time_sec,
                ammo_cost=am.ammo_cost,
                reason="，".join(reasons),
                warnings=am.warnings,
            ))
        rows.sort(key=lambda r: (-r.score, r.room_id))
        return rows

    def _room_name(self, rid: str) -> str:
        if rid in self.data.rooms:
            return self.data.rooms[rid].name
        return rid
