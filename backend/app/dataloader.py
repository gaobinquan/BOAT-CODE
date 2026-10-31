"""数据加载层：YAML → Pydantic 校验 → 缓存。

数据错误在启动/首次请求时立即报错（fail fast）。
等级段（"1-3" 等）在此展开为单级映射，供模拟器直接使用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

import yaml

from .schemas.models import (
    BattleScenariosFile,
    ConditionDef,
    ActionDef,
    CrewDef,
    CrewFile,
    EnemyRoomsFile,
    EnemyRoomStats,
    LevelDef,
    LevelsFile,
    ModulesFile,
    RoomDef,
    RoomsFile,
    ScenarioDef,
    ThreatsFile,
)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_yaml(name: str) -> dict:
    path = DATA_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"数据文件不存在: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        raise ValueError(f"数据文件为空: {path}")
    return data


def _parse_range_key(key: str) -> tuple[int, int]:
    """'1-3' → (1, 3)"""
    lo, hi = key.split("-")
    return int(lo), int(hi)


def _expand_ranges(ranges: Dict[str, dict], levels: int = 10) -> Dict[int, dict]:
    """等级段表展开为 {level: {...}}。"""
    out: Dict[int, dict] = {}
    for key, value in ranges.items():
        lo, hi = _parse_range_key(key)
        for lv in range(lo, hi + 1):
            out[lv] = value
    missing = [lv for lv in range(1, levels + 1) if lv not in out]
    if missing:
        raise ValueError(f"等级段未覆盖: {missing}")
    return out


@dataclass(frozen=True)
class GameData:
    """全部游戏数据的内存视图。"""

    conditions: Dict[str, ConditionDef]
    actions: Dict[str, ActionDef]
    rooms: Dict[str, RoomDef]
    crew: Dict[str, CrewDef]
    levels: Dict[int, LevelDef]
    threats: Dict[str, int]                       # room_id → 威胁度
    enemy_rooms: Dict[int, Dict[str, EnemyRoomStats]]  # level → room_id → 数据
    scenarios: Dict[int, ScenarioDef]             # level → 场景假设

    def get_level(self, level: int) -> LevelDef:
        lv = self.levels.get(level)
        if lv is None:
            raise ValueError(f"无效等级: {level}")
        return lv

    def get_room(self, room_id: str) -> RoomDef:
        room = self.rooms.get(room_id)
        if room is None:
            raise ValueError(f"无效房间: {room_id}")
        return room

    def threat_of(self, room_id: str) -> int:
        return self.threats.get(room_id, 3)

    def enemy_room_stats(self, level: int, room_id: str) -> Optional[EnemyRoomStats]:
        return self.enemy_rooms.get(level, {}).get(room_id)

    def scenario_of(self, level: int) -> ScenarioDef:
        sc = self.scenarios.get(level)
        if sc is None:
            raise ValueError(f"等级 {level} 无战斗场景数据")
        return sc


@lru_cache(maxsize=1)
def load_game_data() -> GameData:
    """加载并校验全部数据文件（进程内缓存一次）。"""
    modules = ModulesFile.model_validate(_load_yaml("modules.yaml"))
    rooms = RoomsFile.model_validate(_load_yaml("rooms.yaml"))
    crew = CrewFile.model_validate(_load_yaml("crew.yaml"))
    levels = LevelsFile.model_validate(_load_yaml("levels.yaml"))
    threats = ThreatsFile.model_validate(_load_yaml("threats.yaml"))
    enemy = EnemyRoomsFile.model_validate(_load_yaml("enemy_rooms.yaml"))
    scenarios = BattleScenariosFile.model_validate(_load_yaml("battle_scenarios.yaml"))

    # 等级内可用房间必须存在于 rooms.yaml
    room_ids = {r.id for r in rooms.rooms}
    for lv in levels.levels:
        unknown = [r for r in lv.available_rooms if r not in room_ids]
        if unknown:
            raise ValueError(f"levels.yaml 等级 {lv.level} 引用了未知房间: {unknown}")

    # 威胁表房间必须存在
    for t in threats.threats:
        if t not in room_ids and t not in {"weapon_room", "power_room"}:
            raise ValueError(f"threats.yaml 引用了未知房间: {t}")

    # 等级段展开
    enemy_by_level = _expand_ranges(enemy.level_ranges)
    scenarios_by_level = _expand_ranges(scenarios.scenarios)

    # 每个等级段内引用同一份 dict，防御性复制避免意外共享
    enemy_by_level = {k: dict(v) for k, v in enemy_by_level.items()}

    return GameData(
        conditions={c.id: c for c in modules.conditions},
        actions={a.id: a for a in modules.actions},
        rooms={r.id: r for r in rooms.rooms},
        crew={c.id: c for c in crew.crew},
        levels={lv.level: lv for lv in levels.levels},
        threats={k: v.base for k, v in threats.threats.items()},
        enemy_rooms=enemy_by_level,
        scenarios=scenarios_by_level,
    )
