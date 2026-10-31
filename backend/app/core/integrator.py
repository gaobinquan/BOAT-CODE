"""决策整合与搭配层：判断阶段 → 搭配阶段 → 战略总述（确定性）。

流水线（规格 5.1）：
威胁判断 + 效率判断 + 弹药判断 → 综合目标优先级
→ 武器×目标配对矩阵 + 房间指令链 + 船员×任务配对 + 全舰电力方案
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..dataloader import GameData
from ..schemas.models import (
    ActionRef,
    AmmoPlan,
    Command,
    ConditionRef,
    CrewAssignment,
    EfficiencyRow as ApiEffRow,
    PairingRow,
    PowerPlan,
)
from ..sim.ammo_planner import AmmoPlanner
from ..sim.efficiency import EfficiencyEvaluator
from ..sim.frame_scheduler import FrameScheduler
from ..sim.power_budget import PowerBudget, RoomDemand
from ..sim.power_optimizer import PowerOptimizer, RoomPowerPlan
from ..sim.threat import ThreatEvaluator
from .intent import IntentParams


@dataclass
class IntegrationResult:
    pairing_matrix: List[PairingRow] = field(default_factory=list)
    crew_assignments: List[CrewAssignment] = field(default_factory=list)
    commands: List[Command] = field(default_factory=list)
    room_power_plans: List[RoomPowerPlan] = field(default_factory=list)
    power_plan: Optional[PowerPlan] = None
    ammo_plan: Optional[AmmoPlan] = None
    efficiency_ranking: List[ApiEffRow] = field(default_factory=list)
    strategy: str = ""
    warnings: List[str] = field(default_factory=list)


class DecisionIntegrator:
    def __init__(self, data: GameData):
        self.data = data
        self.threat_ev = ThreatEvaluator()
        self.eff_ev = EfficiencyEvaluator(data)
        self.ammo = AmmoPlanner()
        self.power_opt = PowerOptimizer(data)
        self.budget = PowerBudget()
        self.frame = FrameScheduler()

    # ─────────── 工具 ───────────

    def _level_rooms(self, level: int) -> List[str]:
        return list(self.data.get_level(level).available_rooms)

    def _level_weapons(self, level: int) -> List[str]:
        return [
            rid for rid in self._level_rooms(level)
            if self.data.get_room(rid).category == "weapon"
            and self.data.get_room(rid).weapon is not None
        ]

    def _weapon_dict(self, rid: str) -> dict:
        room = self.data.get_room(rid)
        w = room.weapon
        return {
            "id": rid, "name": room.name,
            "damage": w.damage, "volley": w.volley,
            "reload_sec": w.reload_sec, "ammo": w.ammo,
            "target": w.target,
        }

    # ─────────── 主流程 ───────────

    def integrate(
        self,
        level: int,
        target_id: str,
        target_type: str,
        intent: IntentParams,
    ) -> IntegrationResult:
        lv = self.data.get_level(level)
        if not lv.ai_enabled:
            raise ValueError("该等级未解锁指挥室 AI（4 级解锁），无法生成编程清单")

        warnings: List[str] = []
        result = IntegrationResult()

        if target_type == "room":
            room = self.data.get_room(target_id)
            if room.min_ship_level > level:
                raise ValueError(f"房间「{room.name}」在等级 {level} 不可用（{room.min_ship_level} 级解锁）")

        # 1) 判断阶段：威胁 + 效率 + 弹药
        weapons = [target_id] if (target_type == "room" and self.data.get_room(target_id).category == "weapon")             else self._level_weapons(level)
        if not weapons:
            raise ValueError("该等级无可用武器房间")

        # 代表武器（用于效率排名与弹药规划）
        rep_id = weapons[0]
        rep_w = self._weapon_dict(rep_id)

        threat_rows = self.threat_ev.evaluate(
            self.data.threats, weapons, list(self.data.enemy_rooms[level].keys())
        )
        threat_map = {r.room_id: r.score for r in threat_rows}

        eff_rows = self.eff_ev.evaluate(level, rep_w, threat_map)
        ranking = [
            ApiEffRow(room=r.room_id, score=r.score,
                      volleys_to_kill=r.volleys_to_kill, reason=r.reason)
            for r in eff_rows
        ]
        result.efficiency_ranking = ranking

        # 综合目标优先级：意图优先 + 效率排序兜底
        order = self._merge_priority(intent, eff_rows)
        primary = order[0]
        secondary = order[1] if len(order) > 1 else None

        # 2) 搭配阶段：武器×目标配对 + 集火判定
        pairings, attack_map = self._pair_weapons(level, weapons, order, eff_rows)
        result.pairing_matrix = pairings

        # 3) 弹药规划（代表武器为有限弹药时）
        ammo_mode = "normal"
        if rep_w.get("ammo"):
            stats = self.data.enemy_room_stats(level, primary)
            am = self.ammo.plan(rep_w, {
                "id": primary, "name": self._room_name(primary),
                "hp": stats.hp, "armor_mod": stats.armor_mod,
                "repair_per_sec": stats.repair_per_sec,
            }, {
                "duration_sec": self.data.scenario_of(level).duration_sec,
                "ammo_assumption": self.data.scenario_of(level).ammo_assumption,
            })
            ammo_mode = am.mode
            result.ammo_plan = AmmoPlan(
                volleys_to_kill=am.volleys_to_kill,
                ammo_cost=am.ammo_cost,
                mode=am.mode,
                note=am.note,
            )
        if intent.conserve_ammo:
            ammo_mode = "conservative"

        # 4) 编程对象指令链
        if target_type == "room":
            troom = self.data.get_room(target_id)
            if troom.category == "weapon":
                result.commands = self._weapon_commands(
                    troom, primary, secondary, ammo_mode)
            else:
                plans = self.power_opt.optimize(level, self._level_rooms(level))
                mine = next((p for p in plans if p.room_id == target_id), None)
                result.commands = mine.commands if mine else []
        else:
            result.crew_assignments, result.commands = self._crew_commands(
                target_id, level, order, intent, eff_rows)

        # 5) 全舰电力方案 + 预算校验 + 帧时序
        ammo_modes = {rep_id: ammo_mode}
        result.room_power_plans = self.power_opt.optimize(
            level, self._level_rooms(level),
            attack_weapons=attack_map, ammo_modes=ammo_modes)
        result.power_plan, budget_warns = self._budget(level, result.room_power_plans)
        warnings.extend(budget_warns)

        frame_warns = self._frame_timing(level, result.room_power_plans)
        warnings.extend(frame_warns)

        # 6) 战略总述
        result.strategy = self._strategy_text(
            primary, secondary, result.ammo_plan, intent, eff_rows)
        result.warnings = warnings
        return result

    # ─────────── 目标优先级 ───────────

    def _merge_priority(self, intent: IntentParams, eff_rows) -> List[str]:
        eff_order = [r.room_id for r in eff_rows]
        prio = [rid for rid in intent.priority if rid in eff_order]
        rest = [rid for rid in eff_order if rid not in prio]
        return prio + rest

    # ─────────── 武器配对 ───────────

    def _pair_weapons(
        self, level: int, weapons: List[str], order: List[str], eff_rows
    ) -> tuple[List[PairingRow], Dict[str, str]]:
        pairings: List[PairingRow] = []
        attack_map: Dict[str, str] = {}
        picks: Dict[str, str] = {}

        for wid in weapons:
            w = self._weapon_dict(wid)
            if w.get("target") == "craft":
                continue  # 防空打战机，不进房间配对
            if w.get("ammo"):
                # 高伤有限弹 → 高威胁目标（优先级第 1）
                pick = order[0]
                reason = "高伤有限弹 → 打高威胁目标"
            else:
                # 高射速无限弹 → 护盾/低血量优先
                pick = "shield_room" if "shield_room" in order else order[0]
                reason = "高射速无限弹 → 拆盾/低血量目标"
            picks[wid] = pick
            attack_map[wid] = pick

        # 集火判定：两武器同目标时，合并击破时间缩短 → focus_fire
        target_users: Dict[str, List[str]] = {}
        for wid, tgt in picks.items():
            target_users.setdefault(tgt, []).append(wid)

        used: List[PairingRow] = []
        for tgt, users in target_users.items():
            if len(users) > 1:
                used.append(PairingRow(
                    weapon="+".join(users), target=tgt,
                    mode="focus_fire",
                    reason=f"多武器同目标，合并集火缩短击破时间",
                ))
            else:
                used.append(PairingRow(
                    weapon=users[0], target=tgt, mode="solo",
                    reason=self._solo_reason(users[0])))
        pairings.extend(used)
        return pairings, attack_map

    def _solo_reason(self, wid: str) -> str:
        w = self._weapon_dict(wid)
        return "无限弹药持续压制" if not w.get("ammo") else "有限弹药精准打击"

    # ─────────── 指令链 ───────────

    def _weapon_commands(
        self, room, primary: str, secondary: Optional[str], ammo_mode: str
    ) -> List[Command]:
        cmds: List[Command] = []
        if ammo_mode == "conservative":
            cmds.append(Command(
                order=1,
                condition=ConditionRef(id="cond_enemy_hull_full", name="敌舰满血"),
                action=ActionRef(id="act_attack_enemy_room", name="攻击敌方XX房间",
                                 params={"目标房间": primary}),
                note="省弹模式：战斗初期（敌舰满血）才开火",
            ))
            cmds.append(Command(
                order=2,
                condition=ConditionRef(id="cond_none", name="无条件"),
                action=ActionRef(id="act_power_down", name="电力-1"),
                note="弹药用完/敌舰掉血后关电",
            ))
            return cmds
        # 正常集火模式
        if secondary:
            cmds.append(Command(
                order=1,
                condition=ConditionRef(id="cond_target_room_destroyed", name="目标房间被摧毁"),
                action=ActionRef(id="act_attack_enemy_room", name="攻击敌方XX房间",
                                 params={"目标房间": secondary}),
                note=f"主目标摧毁后转打次级目标 {secondary}",
            ))
        cmds.append(Command(
            order=len(cmds) + 1,
            condition=ConditionRef(id="cond_none", name="无条件"),
            action=ActionRef(id="act_attack_enemy_room", name="攻击敌方XX房间",
                             params={"目标房间": primary}),
            note=f"集火 {primary}；房间电力保持满电（帧1即满）",
        ))
        return cmds

    def _crew_commands(
        self, crew_id: str, level: int, order: List[str],
        intent: IntentParams, eff_rows,
    ) -> tuple[List[CrewAssignment], List[Command]]:
        crew = self.data.crew[crew_id]
        top = order[0]
        top_score = next((r.score for r in eff_rows if r.room_id == top), 0.0)

        if crew.role == "offensive":
            assign = CrewAssignment(
                crew=crew.name, task="board_attack", target_room=top,
                based_on=f"效率分 {top_score:.1f}，第 1 目标")
            cmds = [Command(
                order=1,
                condition=ConditionRef(id="cond_none", name="无条件"),
                action=ActionRef(id="act_attack_enemy_room", name="攻击敌方XX房间",
                                 params={"目标房间": top}),
                note=f"登舰直扑 {self._room_name(top)}",
            )]
        elif crew.role == "repair":
            guard = intent.protect_rooms[0] if intent.protect_rooms else "reactor"
            assign = CrewAssignment(
                crew=crew.name, task="garrison_repair", target_room=guard,
                based_on="守我方高威胁房间" + ("（意图指定）" if intent.protect_rooms else "（默认电力室）"))
            cmds = [Command(
                order=1,
                condition=ConditionRef(id="cond_none", name="无条件"),
                action=ActionRef(id="act_continue_current", name="继续当前任务"),
                note=f"玩家手动派驻 {self._room_name(guard)} 维修",
            )]
        else:  # pilot
            assign = CrewAssignment(
                crew=crew.name, task="pilot_engine", target_room="engine_room",
                based_on="舵手驻引擎，机动与逃跑")
            cmds = [Command(
                order=1,
                condition=ConditionRef(id="cond_none", name="无条件"),
                action=ActionRef(id="act_continue_current", name="继续当前任务"),
                note="玩家手动派驻引擎室",
            )]
        return [assign], cmds

    # ─────────── 电力与帧时序 ───────────

    def _budget(self, level: int, plans: List[RoomPowerPlan]) -> tuple[PowerPlan, List[str]]:
        lv = self.data.get_level(level)
        demands = [
            RoomDemand(p.room_id, p.demand_power, self.data.get_room(p.room_id).threat, p.tier)
            for p in plans if p.demand_power > 0
        ]
        res = self.budget.check(demands, lv.reactor_output)
        plan = PowerPlan(
            total=lv.reactor_output,
            used=res.used,
            status=res.status,
            warnings=res.warnings,
        )
        return plan, res.warnings

    def _frame_timing(self, level: int, plans: List[RoomPowerPlan]) -> List[str]:
        lv = self.data.get_level(level)
        intents = []
        for i, p in enumerate(plans):
            cmds = [{
                "condition": {"id": c.condition.id},
                "action": {"id": c.action.id, "params": c.action.params or {}},
            } for c in p.commands]
            intent = self.frame.parse_intents(p.room_id, i, cmds)
            intent.target_power = max(intent.target_power, 1) if intent.mode != "conditional_off" else 0
            intents.append(intent)
        frames = self.frame.simulate(intents, lv.reactor_output)
        warns: List[str] = []
        seen: set = set()
        for f in frames:
            for w in f.warnings:
                if w not in seen:
                    seen.add(w)
                    warns.append(w)
        return warns

    # ─────────── 战略文本 ───────────

    def _strategy_text(
        self, primary: str, secondary: Optional[str],
        ammo: Optional[AmmoPlan], intent: IntentParams, eff_rows,
    ) -> str:
        top = next((r for r in eff_rows if r.room_id == primary), None)
        parts = [f"主攻目标：{self._room_name(primary)}"]
        if top:
            parts.append(f"（效率分 {top.score}）")
        if secondary:
            parts.append(f"→ 摧毁后转打 {self._room_name(secondary)}")
        if ammo:
            parts.append(f"；弹药：需 {ammo.ammo_cost} 发（{ammo.mode}）")
        if intent.conserve_ammo:
            parts.append("；省弹：只打高威胁目标，敌舰掉血即停火")
        if intent.protect_rooms:
            parts.append(f"；守备：{self._room_name(intent.protect_rooms[0])}")
        return "".join(parts)

    def _room_name(self, rid: str) -> str:
        return self.data.get_room(rid).name if rid in self.data.rooms else rid
