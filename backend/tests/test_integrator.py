"""决策整合层测试。"""
import pytest

from app.core.integrator import DecisionIntegrator
from app.core.intent import IntentParams, QUICK_PICKS
from app.dataloader import load_game_data


@pytest.fixture(scope="module")
def integrator():
    return DecisionIntegrator(load_game_data())


def test_integrate_missile_focus_engine(integrator):
    r = integrator.integrate(4, "missile_room", "room", QUICK_PICKS["集火引擎"])
    assert r.pairing_matrix[0].target == "engine_room"
    # 指令：摧毁后转打次级 + 无条件集火主目标
    assert r.commands[0].condition.id == "cond_target_room_destroyed"
    assert r.commands[1].action.params["目标房间"] == "engine_room"
    assert r.ammo_plan is not None
    assert r.power_plan.status in ("ok", "over")
    assert r.efficiency_ranking[0].room == "engine_room"


def test_integrate_conserve_ammo(integrator):
    r = integrator.integrate(4, "missile_room", "room", QUICK_PICKS["省弹打法"])
    # 省弹模式：敌舰满血才开火，掉血关电
    assert r.commands[0].condition.id == "cond_enemy_hull_full"
    assert r.commands[1].action.id == "act_power_down"


def test_integrate_no_ai_below_level4(integrator):
    with pytest.raises(ValueError, match="4 级解锁"):
        integrator.integrate(2, "laser_room", "room", IntentParams())


def test_integrate_room_unavailable(integrator):
    with pytest.raises(ValueError, match="不可用"):
        integrator.integrate(4, "pp_room", "room", IntentParams())


def test_integrate_offensive_crew(integrator):
    r = integrator.integrate(4, "galaxy_alchemist", "crew", QUICK_PICKS["拆盾优先"])
    assert r.crew_assignments[0].task == "board_attack"
    assert r.crew_assignments[0].target_room == "shield_room"
    assert r.commands[0].action.params["目标房间"] == "shield_room"


def test_integrate_repair_crew_default_guard(integrator):
    r = integrator.integrate(4, "repair_bot", "crew", IntentParams())
    assert r.crew_assignments[0].task == "garrison_repair"
    assert r.crew_assignments[0].target_room == "reactor"


def test_integrate_pilot_crew(integrator):
    r = integrator.integrate(4, "pilot_mae", "crew", IntentParams())
    assert r.crew_assignments[0].task == "pilot_engine"
    assert r.crew_assignments[0].target_room == "engine_room"


def test_deterministic_same_input_same_output(integrator):
    params = QUICK_PICKS["集火引擎"]
    r1 = integrator.integrate(4, "missile_room", "room", params)
    r2 = integrator.integrate(4, "missile_room", "room", params)
    assert r1 == r2


def test_intent_priority_overrides_efficiency(integrator):
    r = integrator.integrate(
        4, "laser_room", "room", IntentParams(priority=["medbay"], mode="focus_fire"))
    assert r.pairing_matrix[0].target == "shield_room"  # 激光无限弹优先护盾
