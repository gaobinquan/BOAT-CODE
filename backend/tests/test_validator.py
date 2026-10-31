"""一致性终检测试。"""
import pytest

from app.core.integrator import DecisionIntegrator
from app.core.intent import QUICK_PICKS
from app.core.validator import ValidationError, Validator
from app.dataloader import load_game_data
from app.schemas.models import ActionRef, Command, ConditionRef


@pytest.fixture(scope="module")
def v():
    return Validator(load_game_data())


@pytest.fixture(scope="module")
def integrator():
    return DecisionIntegrator(load_game_data())


def test_valid_generation_passes(integrator, v):
    r = integrator.integrate(4, "missile_room", "room", QUICK_PICKS["集火引擎"])
    outcome = v.check(r, 4)
    assert outcome.warnings, "L4 指令槽超限应产生裁剪警告"


def test_unknown_module_raises(integrator, v):
    r = integrator.integrate(4, "missile_room", "room", QUICK_PICKS["集火引擎"])
    r.commands[0] = Command(
        order=1, condition=ConditionRef(id="cond_fake"),
        action=ActionRef(id="act_power_up"))
    with pytest.raises(ValidationError, match="不存在"):
        v.check(r, 4)


def test_py_version_incompatible_raises(integrator, v):
    """PY2 等级（L4）用了 PY3 专属条件 → 报错。"""
    r = integrator.integrate(4, "missile_room", "room", QUICK_PICKS["集火引擎"])
    r.commands[0] = Command(
        order=1, condition=ConditionRef(id="cond_my_room_has_enemy"),
        action=ActionRef(id="act_power_up"))
    with pytest.raises(ValidationError, match="PY"):
        v.check(r, 4)


def test_param_out_of_range_raises(integrator, v):
    r = integrator.integrate(4, "missile_room", "room", QUICK_PICKS["集火引擎"])
    r.commands[0] = Command(
        order=1, condition=ConditionRef(id="cond_none"),
        action=ActionRef(id="act_set_power", params={"电力值": 99}))
    with pytest.raises(ValidationError, match="超出范围"):
        v.check(r, 4)


def test_contradictory_power_pair_raises(integrator, v):
    r = integrator.integrate(4, "missile_room", "room", QUICK_PICKS["集火引擎"])
    r.room_power_plans[0].commands = [
        Command(order=1, condition=ConditionRef(id="cond_none"),
                action=ActionRef(id="act_power_up")),
        Command(order=2, condition=ConditionRef(id="cond_none"),
                action=ActionRef(id="act_power_down")),
    ]
    with pytest.raises(ValidationError, match="矛盾"):
        v.check(r, 4)
