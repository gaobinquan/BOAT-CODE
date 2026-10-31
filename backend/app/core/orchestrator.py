"""编排器：加载数据 → 意图解析(LLM可降级) → 整合搭配 → 终检 → LLM润色(可降级) → 输出。

全流程确定性：同一输入 → 同一输出（LLM 降级后更确定）。
"""
from __future__ import annotations

from typing import List

from ..dataloader import GameData, load_game_data
from ..llm.client import LLMClient
from ..llm.intent import IntentParser
from ..llm.polish import polish_explanation
from ..schemas.models import Command, GenerateRequest, GenerateResponse
from .integrator import DecisionIntegrator, IntegrationResult
from .intent import IntentParams, resolve_intent
from .validator import Validator


class Orchestrator:
    def __init__(self, data: GameData | None = None):
        self.data = data or load_game_data()
        self.integrator = DecisionIntegrator(self.data)
        self.validator = Validator(self.data)

    def generate(self, req: GenerateRequest) -> GenerateResponse:
        degraded = False

        # 1) 意图解析（LLM 失败降级为快捷选项/默认）
        params: IntentParams = resolve_intent(req.quick_pick, None)
        if req.intent and req.llm_config:
            client = LLMClient(req.llm_config)
            llm_params = IntentParser(self.data).parse(client, req.intent, req.level)
            if llm_params is not None:
                params = llm_params
            else:
                degraded = True

        # 2) 整合 + 搭配
        result: IntegrationResult = self.integrator.integrate(
            req.level, req.target.id, req.target.type, params)

        # 3) 一致性终检
        outcome = self.validator.check(result, req.level)
        result = outcome.result

        # 4) LLM 润色（失败降级为内置模板）
        explanation = self._template_explanation(result)
        if req.llm_config:
            polished = polish_explanation(LLMClient(req.llm_config), explanation)
            if polished:
                explanation = polished
            else:
                degraded = True

        warnings = list(result.warnings) + list(outcome.warnings)
        return GenerateResponse(
            target=req.target,
            ship_level=req.level,
            pairing_matrix=result.pairing_matrix,
            crew_assignments=result.crew_assignments,
            commands=result.commands,
            power_plan=result.power_plan,
            ammo_plan=result.ammo_plan,
            efficiency_ranking=result.efficiency_ranking,
            strategy=result.strategy,
            explanation=explanation,
            degraded=degraded,
            warnings=warnings,
        )

    # ─────────── 内置说明模板（LLM 降级用） ───────────

    def _template_explanation(self, result: IntegrationResult) -> str:
        lines: List[str] = ["【编程清单】"]
        for cmd in result.commands:
            cond = self.data.conditions[cmd.condition.id].name
            act = cmd.action.id
            act_name = self.data.actions[act].name
            params = " ".join(str(v) for v in cmd.action.params.values()) if cmd.action.params else ""
            lines.append(f"{cmd.order}. 条件「{cond}」→ 动作「{act_name}」{params}（{cmd.note}）")

        lines.append("")
        lines.append("【配对矩阵】")
        for p in result.pairing_matrix:
            lines.append(f"- {p.weapon} → {self._room_name(p.target)}（{p.mode}，{p.reason}）")

        lines.append("")
        lines.append("【电力方案】")
        if result.power_plan:
            lines.append(f"- 反应堆 {result.power_plan.total}，常开用 {result.power_plan.used}，状态 {result.power_plan.status}")
        for plan in result.room_power_plans:
            if plan.rationale:
                lines.append(f"- {self._room_name(plan.room_id)}：{plan.rationale}")

        lines.append("")
        lines.append(f"【战略】{result.strategy}")
        return "\n".join(lines)

    def _room_name(self, rid: str) -> str:
        return self.data.get_room(rid).name if rid in self.data.rooms else rid
