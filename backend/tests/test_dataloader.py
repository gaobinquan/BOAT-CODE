"""数据层测试：加载成功 + 校验失败。"""
import pytest

from app.dataloader import load_game_data


def test_load_success():
    g = load_game_data()
    assert len(g.rooms) == 12
    assert len(g.levels) == 10
    assert len(g.crew) == 3
    assert g.levels[4].ai_enabled is True
    assert g.levels[3].ai_enabled is False
    # 等级段展开
    assert g.enemy_rooms[4]["engine_room"].hp == 3
    assert g.enemy_rooms[10]["engine_room"].hp == 5
    assert g.scenarios[4].duration_sec == 120


def test_condition_and_action_lookup():
    g = load_game_data()
    assert "cond_enemy_has_craft" in g.conditions
    assert "act_set_max_power" in g.actions
    # 蟒蛇版本约束
    assert g.conditions["cond_my_room_has_enemy"].python_ver == [3]
    assert g.conditions["cond_enemy_teleport_hp"].python_ver == [2, 3]


def test_levels_all_present():
    g = load_game_data()
    assert sorted(g.levels.keys()) == list(range(1, 11))
    # 4 级解锁 AI，PY2；7 级起 PY3（初值）
    assert g.levels[4].python_ver == 2
    assert g.levels[7].python_ver == 3
