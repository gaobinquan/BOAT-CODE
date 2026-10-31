"""Pydantic 模型：数据文件校验 + API 请求/响应。

数据文件（data/*.yaml）在加载时全部经过本模块校验，
数据错误在启动/请求时立即报错，不进入引擎。
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ─────────────────────────── 数据文件模型 ───────────────────────────

class ParamDef(BaseModel):
    name: str
    type: Literal["int", "float", "bool", "string", "room_ref"]
    range: Optional[list[float]] = None  # [min, max]，含端点


class ConditionDef(BaseModel):
    id: str
    name: str
    python_ver: list[int] = Field(default_factory=lambda: [2, 3])
    params: list[ParamDef] = Field(default_factory=list)


class ActionDef(BaseModel):
    id: str
    name: str
    python_ver: list[int] = Field(default_factory=lambda: [2, 3])
    params: list[ParamDef] = Field(default_factory=list)


class ModulesFile(BaseModel):
    conditions: list[ConditionDef]
    actions: list[ActionDef]

    @model_validator(mode="after")
    def _unique_ids(self):
        seen_c, seen_a = set(), set()
        for c in self.conditions:
            assert c.id not in seen_c, f"condition id 重复: {c.id}"
            seen_c.add(c.id)
        for a in self.actions:
            assert a.id not in seen_a, f"action id 重复: {a.id}"
            seen_a.add(a.id)
        return self


class WeaponStats(BaseModel):
    damage: float
    volley: int = 1
    reload_sec: float
    ammo: Optional[int] = None  # None = 无限弹药
    target: Literal["room", "craft"] = "room"


class RoomDef(BaseModel):
    id: str
    name: str
    category: Literal["weapon", "utility", "defense", "support"]
    min_ship_level: int = Field(ge=1, le=10)
    max_power: int = Field(ge=0)
    weapon: Optional[WeaponStats] = None
    ai_slots: int = Field(default=1, ge=0)
    threat: int = Field(default=3, ge=0, le=10)
    notes: str = ""


class RoomsFile(BaseModel):
    rooms: list[RoomDef]

    @model_validator(mode="after")
    def _unique_ids(self):
        seen = set()
        for r in self.rooms:
            assert r.id not in seen, f"room id 重复: {r.id}"
            seen.add(r.id)
        return self


class CrewDef(BaseModel):
    id: str
    name: str
    stars: int = Field(ge=1, le=5)
    role: Literal["offensive", "repair", "pilot", "special"]
    skills: list[str] = Field(default_factory=list)
    ai_slots: int = Field(default=2, ge=1)


class CrewFile(BaseModel):
    crew: list[CrewDef]

    @model_validator(mode="after")
    def _unique_ids(self):
        seen = set()
        for c in self.crew:
            assert c.id not in seen, f"crew id 重复: {c.id}"
            seen.add(c.id)
        return self


class LevelDef(BaseModel):
    level: int = Field(ge=1, le=10)
    ai_enabled: bool = False
    ai_slots: int = Field(default=0, ge=0)
    python_ver: Literal[2, 3] = 2
    reactor_output: int = Field(ge=0)
    available_rooms: list[str] = Field(default_factory=list)


class LevelsFile(BaseModel):
    levels: list[LevelDef]

    @model_validator(mode="after")
    def _all_levels(self):
        lv = sorted(l.level for l in self.levels)
        assert lv == list(range(1, 11)), f"levels.yaml 必须包含 1-10 级，实际: {lv}"
        return self


class ThreatDef(BaseModel):
    base: int = Field(ge=0, le=10)
    note: str = ""


class ThreatsFile(BaseModel):
    threats: dict[str, ThreatDef]


class EnemyRoomStats(BaseModel):
    hp: int = Field(ge=1)
    armor_mod: float = Field(default=1.0, gt=0)
    repair_per_sec: float = Field(default=0.1, ge=0)


class EnemyRoomsFile(BaseModel):
    # key 为等级段 "1-3" / "4-6" / "7-8" / "9-10"，dataloader 展开到单级
    level_ranges: dict[str, dict[str, EnemyRoomStats]]


class ScenarioDef(BaseModel):
    duration_sec: int = Field(ge=1)
    ammo_assumption: int = Field(ge=0)


class BattleScenariosFile(BaseModel):
    # key 为等级段，dataloader 展开到单级
    scenarios: dict[str, ScenarioDef]


# ─────────────────────────── API 模型 ───────────────────────────

class TargetRef(BaseModel):
    type: Literal["room", "crew"]
    id: str


class LLMConfig(BaseModel):
    base_url: str = Field(default="https://api.openai.com/v1")
    api_key: str
    model: str = Field(default="gpt-4o-mini")
    timeout_sec: float = Field(default=10.0, ge=1, le=60)


class GenerateRequest(BaseModel):
    level: int = Field(ge=1, le=10)
    target: TargetRef
    intent: Optional[str] = None  # 自然语言意图；为空则走默认战略
    quick_pick: Optional[str] = None  # 快捷选项 id：拆盾/压维修/集火引擎/保电力
    llm_config: Optional[LLMConfig] = None


class ConditionRef(BaseModel):
    id: str
    params: dict = Field(default_factory=dict)
    name: str = ""


class ActionRef(BaseModel):
    id: str
    params: dict = Field(default_factory=dict)
    name: str = ""


class Command(BaseModel):
    order: int
    condition: ConditionRef
    action: ActionRef
    note: str = ""


class PairingRow(BaseModel):
    weapon: str
    target: str
    mode: Literal["focus_fire", "alternate", "solo"]
    reason: str


class CrewAssignment(BaseModel):
    crew: str
    task: str
    target_room: Optional[str] = None
    based_on: str


class PowerPlan(BaseModel):
    total: int
    used: int
    status: Literal["ok", "over"]
    warnings: list[str] = Field(default_factory=list)


class AmmoPlan(BaseModel):
    volleys_to_kill: float
    ammo_cost: int
    mode: Literal["normal", "conservative"]
    note: str = ""


class EfficiencyRow(BaseModel):
    room: str
    score: float
    volleys_to_kill: float
    reason: str


class GenerateResponse(BaseModel):
    target: TargetRef
    ship_level: int
    pairing_matrix: list[PairingRow] = Field(default_factory=list)
    crew_assignments: list[CrewAssignment] = Field(default_factory=list)
    commands: list[Command] = Field(default_factory=list)
    power_plan: PowerPlan
    ammo_plan: Optional[AmmoPlan] = None
    efficiency_ranking: list[EfficiencyRow] = Field(default_factory=list)
    strategy: str
    explanation: str
    degraded: bool = False  # LLM 降级标记
    warnings: list[str] = Field(default_factory=list)
