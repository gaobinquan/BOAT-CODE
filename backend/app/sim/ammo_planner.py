"""弹药伤害规划器：击破轮数/弹药消耗/省弹判断（纯函数）。

- 每轮有效伤害 = (伤害×齐射 − 装填期间维修量) × 护甲修正
- 击破轮数 = ceil(目标HP ÷ 每轮有效伤害)
- 有限弹药武器：弹量 vs 战斗时长假设 → 集火/省弹模式
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AmmoResult:
    weapon: str
    target: str
    dps: float
    effective_damage_per_volley: float
    volleys_to_kill: float
    kill_time_sec: float
    ammo_cost: int
    mode: str                      # normal / conservative
    note: str = ""
    warnings: List[str] = field(default_factory=list)


class AmmoPlanner:
    """对 (武器, 目标) 计算击破成本并判断省弹与否。"""

    def plan(
        self,
        weapon: dict,              # {damage, volley, reload_sec, ammo|None, target}
        target: dict,              # {hp, armor_mod, repair_per_sec}
        scenario: dict,            # {duration_sec, ammo_assumption}
    ) -> AmmoResult:
        damage = weapon["damage"]
        volley = weapon.get("volley", 1)
        reload = weapon["reload_sec"]
        ammo: Optional[int] = weapon.get("ammo")
        hp = target["hp"]
        armor = target.get("armor_mod", 1.0)
        repair = target.get("repair_per_sec", 0.0)

        dps = damage * volley / reload
        # 维修抵消：装填期间目标能修回 repair × reload
        eff = max(damage * volley - repair * reload, 0.01) * armor
        volleys = math.ceil(hp / eff) if eff > 0 else float("inf")
        kill_time = volleys * reload
        ammo_cost = math.ceil(volleys * volley) if ammo is not None else 0

        warnings: List[str] = []
        mode = "normal"
        note = ""
        if ammo is not None:
            total_volleys_in_battle = math.floor(scenario["duration_sec"] / reload)
            available_ammo = min(ammo, scenario["ammo_assumption"])
            if ammo_cost > available_ammo or volleys > total_volleys_in_battle:
                mode = "conservative"
                note = (
                    f"弹药不足/时间不够：需 {ammo_cost} 发（{volleys} 轮×{volley}发），"
                    f"战斗假设 {scenario['duration_sec']}s 内可打 {total_volleys_in_battle} 轮"
                )
                warnings.append(note)
            else:
                note = f"弹药够打：{ammo_cost} 发 ≤ 可用 {available_ammo}"
        else:
            note = "无限弹药，无省弹约束"

        return AmmoResult(
            weapon=weapon.get("name", weapon.get("id", "")),
            target=target.get("name", target.get("id", "")),
            dps=round(dps, 2),
            effective_damage_per_volley=round(eff, 2),
            volleys_to_kill=volleys,
            kill_time_sec=round(kill_time, 1),
            ammo_cost=ammo_cost,
            mode=mode,
            note=note,
            warnings=warnings,
        )
