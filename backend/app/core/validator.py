"""一致性终检（规格 5.3）：指令槽数 / 电力 / 模块与版本 / 参数 / 矛盾指令对。

硬错误 → ValidationError（API 422）；软问题（超槽）→ 裁剪 + warnings。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from ..dataloader import GameData
from ..schemas.models import Command
from .integrator import IntegrationResult


class ValidationError(Exception):
    """终检未通过：中文错误信息，映射 422。"""


@dataclass
class ValidationOutcome:
    result: IntegrationResult
    warnings: List[str] = field(default_factory=list)
    trimmed: List[str] = field(default_factory=list)  # 被裁剪的指令描述


class Validator:
    def __init__(self, data: GameData):
        self.data = data

    def check(self, result: IntegrationResult, level: int) -> ValidationOutcome:
        lv = self.data.get_level(level)
        py = lv.python_ver
        warnings: List[str] = []
        trimmed: List[str] = []

        # 汇总全舰指令：编程对象指令 + 全舰房间电力指令
        all_commands: List[Tuple[str, Command]] = []
        for c in result.commands:
            all_commands.append(("target", c))
        for plan in result.room_power_plans:
            for c in plan.commands:
                all_commands.append((plan.room_id, c))

        # 1) 模块存在 + Python 版本兼容 + 参数范围合法
        for origin, cmd in all_commands:
            cond = self.data.conditions.get(cmd.condition.id)
            if cond is None:
                raise ValidationError(f"条件模块不存在: {cmd.condition.id}")
            if py not in cond.python_ver:
                raise ValidationError(
                    f"条件「{cond.name}」需要蟒蛇 PY{cond.python_ver}，"
                    f"当前等级 {level} 为 PY{py}")
            act = self.data.actions.get(cmd.action.id)
            if act is None:
                raise ValidationError(f"动作模块不存在: {cmd.action.id}")
            if py not in act.python_ver:
                raise ValidationError(
                    f"动作「{act.name}」需要蟒蛇 PY{act.python_ver}，"
                    f"当前等级 {level} 为 PY{py}")
            for pdef in act.params:
                if pdef.name in cmd.action.params:
                    val = cmd.action.params[pdef.name]
                    if pdef.type == "int" and not isinstance(val, int):
                        raise ValidationError(
                            f"参数 {pdef.name} 应为整数: {val}")
                    if pdef.type == "int" and pdef.range and not (pdef.range[0] <= val <= pdef.range[1]):
                        raise ValidationError(
                            f"参数 {pdef.name}={val} 超出范围 {pdef.range}")
                    if pdef.type == "room_ref":
                        if val not in self.data.rooms and val not in {"weapon_room", "power_room"}:
                            raise ValidationError(f"参数引用了未知房间: {val}")

        # 2) 无矛盾指令对：同房间两条无条件电力指令方向相反
        room_acts: dict = {}
        for origin, cmd in all_commands:
            if cmd.condition.id != "cond_none":
                continue
            if cmd.action.id in ("act_power_up", "act_power_down"):
                room_acts.setdefault(origin, set()).add(cmd.action.id)
        for origin, acts in room_acts.items():
            if {"act_power_up", "act_power_down"} <= acts:
                raise ValidationError(
                    f"房间 {origin} 存在矛盾指令对：无条件同时加电与减电")

        # 3) 电力 ≤ 反应堆输出
        if result.power_plan and result.power_plan.status == "over":
            raise ValidationError(
                f"电力方案超支：常开 {result.power_plan.used} > 反应堆 {result.power_plan.total}")

        # 4) 指令槽数 ≤ 上限（软限制：超限按威胁度裁剪，编程对象优先保留）
        total_slots = len(all_commands)
        if total_slots > lv.ai_slots:
            overflow = total_slots - lv.ai_slots
            # 可裁剪：全舰房间电力指令中威胁度低者（排除编程对象与武器攻击指令）
            sacrificial = [
                (plan.room_id, c) for plan in result.room_power_plans
                for c in plan.commands
                if plan.room_id not in {"shield_room", "medbay"}
            ]
            sacrificial.sort(
                key=lambda rc: self.data.get_room(rc[0]).threat)
            for room_id, cmd in sacrificial[:overflow]:
                plan = next(p for p in result.room_power_plans if p.room_id == room_id)
                plan.commands = [c for c in plan.commands if c is not cmd]
                trimmed.append(f"{room_id}:{cmd.action.id}")
            warnings.append(
                f"指令槽 {lv.ai_slots} 超限，已裁剪 {len(sacrificial[:overflow])} 条低威胁电力指令"
            )

        return ValidationOutcome(result=result, warnings=warnings, trimmed=trimmed)
