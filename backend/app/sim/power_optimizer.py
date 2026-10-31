"""电量优化器：按房间套用已核实的策略模板库（纯函数）。

模板来自设计规格 4.2 已核实机制；PY2/PY3 条件差异在此适配。
每条电力指令附"为什么"理由；理由文字后续由 LLM 润色。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..dataloader import GameData
from ..schemas.models import Command, ConditionRef, ActionRef


@dataclass
class RoomPowerPlan:
    room_id: str
    commands: List[Command] = field(default_factory=list)
    rationale: str = ""
    tier: str = "always"        # always / conditional / half
    demand_power: int = 0       # 期望常开电力（预算用）


# 条件开模板：房间 id → (PY2 条件, PY3 条件, 理由)
CONDITIONAL_TEMPLATES: Dict[str, Dict[str, str]] = {
    "aa_laser": {
        "cond2": "cond_enemy_has_craft",
        "cond3": "cond_enemy_has_craft",
        "reason": "敌方有战机才耗电防空，无战机则关电",
    },
    "security_gate": {
        "cond2": "cond_enemy_teleport_hp",
        "cond3": "cond_my_room_has_enemy",
        "reason": "PY2 看敌方传送室血量，PY3 直接看本房间有无敌人",
    },
    "pp_room": {
        "cond2": "cond_enemy_hull_full",
        "cond3": "cond_enemy_hull_full",
        "reason": "开场敌舰满血时破盾；用敌舰满血而非满盾，避免敌方护盾回充导致反复开关丢充能",
    },
    "engine_room": {
        "cond2": "cond_enemy_missile_hp",
        "cond3": "cond_enemy_missile_hp",
        "reason": "敌方有导弹时才耗电机动，无导弹则白开",
    },
}


class PowerOptimizer:
    """为全舰房间生成电力指令链（含理由）。"""

    def __init__(self, data: GameData):
        self.data = data

    def optimize(
        self,
        level: int,
        my_rooms: List[str],                 # 我方实际拥有房间 id
        attack_weapons: Optional[Dict[str, str]] = None,  # 武器id → 目标房间id
        ammo_modes: Optional[Dict[str, str]] = None,      # 武器id → normal/conservative
    ) -> List[RoomPowerPlan]:
        lv = self.data.get_level(level)
        py = lv.python_ver
        attack_weapons = attack_weapons or {}
        ammo_modes = ammo_modes or {}

        plans: List[RoomPowerPlan] = []
        for rid in my_rooms:
            room = self.data.get_room(rid)
            plan = RoomPowerPlan(room_id=rid)

            if rid == "reactor":
                plan.rationale = "电力室自身常开，为全舰供电"
                plan.tier = "always"
                plan.demand_power = 0
                # 电力室不需要 AI 电力指令
                plans.append(plan)
                continue

            if rid in ("shield_room", "medbay"):
                plan.rationale = "护盾/维修属于常开三档位，保持满电" if rid == "shield_room" else "医务室常开，保证维修"
                plan.tier = "always"
                plan.demand_power = room.max_power
                plan.commands = self._always_on(room)
                plans.append(plan)
                continue

            tpl = CONDITIONAL_TEMPLATES.get(rid)
            if tpl:
                cond_id = tpl["cond3"] if py == 3 else tpl["cond2"]
                plan.rationale = tpl["reason"]
                plan.tier = "conditional"
                plan.demand_power = 1
                plan.commands = self._conditional_on(room, cond_id, tpl["reason"])
                plans.append(plan)
                continue

            if rid in attack_weapons and room.weapon:
                mode = ammo_modes.get(rid, "normal")
                plan.tier = "always" if mode == "normal" else "conditional"
                plan.demand_power = room.max_power if mode == "normal" else 1
                if mode == "normal":
                    plan.rationale = f"攻击武器集火，满电优先（帧1即满）"
                    plan.commands = self._always_on(room)
                else:
                    plan.rationale = "有限弹药省弹模式：条件开火，打高威胁目标才耗电"
                    plan.commands = self._conditional_on(
                        room, "cond_enemy_hull_full",
                        "省弹模式：敌舰满血（战斗初期）才开火")
                plans.append(plan)
                continue

            # 其他房间默认无电力指令
            plan.rationale = "无特殊电力策略，保持默认"
            plan.tier = "conditional"
            plan.demand_power = 0
            plans.append(plan)

        return plans

    def _always_on(self, room) -> List[Command]:
        return [
            Command(
                order=1,
                condition=ConditionRef(id="cond_none", name="无条件"),
                action=ActionRef(
                    id="act_set_max_power", name="设置满电力",
                    params={"max_power": room.max_power},
                ),
                note=f"满电优先，帧1即满（最多 {room.max_power} 格）",
            )
        ]

    def _conditional_on(self, room, cond_id: str, note: str) -> List[Command]:
        cond_name = self.data.conditions[cond_id].name if cond_id in self.data.conditions else cond_id
        return [
            Command(
                order=1,
                condition=ConditionRef(id=cond_id, name=cond_name),
                action=ActionRef(id="act_power_up", name="电力+1"),
                note=note,
            ),
            Command(
                order=2,
                condition=ConditionRef(id="cond_none", name="无条件"),
                action=ActionRef(id="act_power_down", name="电力-1"),
                note="条件不满足则关电，互补错峰省电",
            ),
        ]
