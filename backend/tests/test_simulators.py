"""6 个模拟器单元测试（确定性）。"""
from app.dataloader import load_game_data
from app.sim.ammo_planner import AmmoPlanner
from app.sim.efficiency import EfficiencyEvaluator
from app.sim.frame_scheduler import FrameScheduler, RoomPowerIntent
from app.sim.power_budget import PowerBudget, RoomDemand
from app.sim.power_optimizer import PowerOptimizer
from app.sim.threat import ThreatEvaluator


# ─────────── FrameScheduler：帧时序 ───────────

def test_frame1_max_power_priority():
    """满电房间帧1即满；逐格房间帧1只有1格。"""
    sched = FrameScheduler()
    intents = [
        RoomPowerIntent("shield", 0, "always_max", 2),
        RoomPowerIntent("laser", 1, "incremental", 2),
    ]
    frames = sched.simulate(intents, total_power=4)
    f1 = frames[0].power_by_room
    assert f1["shield"] == 2, "满电帧1即满"
    assert f1["laser"] == 1, "逐格帧1只有1格"


def test_frame_build_order_allocation():
    """电力不足时按建造顺序分配。"""
    sched = FrameScheduler()
    intents = [
        RoomPowerIntent("a", 0, "always_max", 3),
        RoomPowerIntent("b", 1, "always_max", 3),
    ]
    frames = sched.simulate(intents, total_power=4)
    f1 = frames[0].power_by_room
    assert f1["a"] == 3
    assert f1["b"] == 1
    assert any("电力不足" in w for w in frames[0].warnings)


def test_incremental_reaches_target():
    sched = FrameScheduler(max_frames=6)
    intents = [RoomPowerIntent("laser", 0, "incremental", 3)]
    frames = sched.simulate(intents, total_power=5)
    last = frames[-1].power_by_room
    assert last["laser"] == 3


# ─────────── PowerBudget：常开校验与降档 ───────────

def test_budget_ok():
    b = PowerBudget()
    res = b.check(
        [RoomDemand("shield", 2, 4, "always"), RoomDemand("medbay", 1, 2, "always")],
        total_power=7)
    assert res.status == "ok"
    assert res.used == 3


def test_budget_downgrade_low_threat_first():
    """超支时威胁低者先降档。"""
    b = PowerBudget()
    res = b.check(
        [
            RoomDemand("shield", 3, 4, "always"),
            RoomDemand("medbay", 3, 2, "always"),
            RoomDemand("hangar", 3, 2, "always"),
        ],
        total_power=6)
    assert res.status == "ok"
    # 威胁 2 的先降（只降够为止），shield 威胁 4 保留
    assert any("hangar" in d or "medbay" in d for d in res.downgrades)
    assert not any("shield" in d for d in res.downgrades)
    assert res.used == 6  # 9 - 3（只降 1 个房间到不超支）


# ─────────── AmmoPlanner：击破轮数/省弹 ───────────

def test_ammo_volleys_and_cost():
    ap = AmmoPlanner()
    # 导弹 dmg4，目标 HP3 护甲1 维修0.1，装填5s → 有效伤害 4-0.5=3.5，1轮
    r = ap.plan(
        {"damage": 4, "volley": 1, "reload_sec": 5.0, "ammo": 12},
        {"hp": 3, "armor_mod": 1.0, "repair_per_sec": 0.1},
        {"duration_sec": 120, "ammo_assumption": 12},
    )
    assert r.volleys_to_kill == 1
    assert r.ammo_cost == 1
    assert r.mode == "normal"


def test_ammo_conservative_when_insufficient():
    ap = AmmoPlanner()
    # 目标 HP20 → 需 20/3.5 ≈ 6 轮 = 6 发；战斗假设只给 3 发 → 省弹
    r = ap.plan(
        {"damage": 4, "volley": 1, "reload_sec": 5.0, "ammo": 12},
        {"hp": 20, "armor_mod": 1.0, "repair_per_sec": 0.1},
        {"duration_sec": 30, "ammo_assumption": 3},
    )
    assert r.mode == "conservative"


def test_infinite_ammo_normal():
    ap = AmmoPlanner()
    r = ap.plan(
        {"damage": 1, "volley": 1, "reload_sec": 3.5, "ammo": None},
        {"hp": 3, "armor_mod": 1.0, "repair_per_sec": 0.1},
        {"duration_sec": 120, "ammo_assumption": 12},
    )
    assert r.mode == "normal"
    assert r.ammo_cost == 0


# ─────────── ThreatEvaluator：威胁排序与适配修正 ───────────

def test_threat_ranking_with_modifier():
    ev = ThreatEvaluator()
    threat_table = {"engine_room": 5, "shield_room": 4, "weapon_room": 3}
    rows = ev.evaluate(threat_table, my_weapons=["missile"], enemy_room_ids=list(threat_table))
    assert rows[0].room_id == "engine_room"   # 5 × 导弹1.2 = 6
    assert rows[0].score > rows[1].score


def test_pp_modifier_on_shield():
    ev = ThreatEvaluator()
    threat_table = {"engine_room": 5, "shield_room": 4}
    rows = ev.evaluate(threat_table, my_weapons=["pp"], enemy_room_ids=list(threat_table))
    assert rows[0].room_id == "shield_room"   # 4 × 1.5 = 6 > 5
    assert rows[0].score == 6.0


# ─────────── EfficiencyEvaluator：效率分 ───────────

def test_efficiency_ranking_sorted():
    data = load_game_data()
    ev = EfficiencyEvaluator(data)
    weapon = {"id": "missile_room", "name": "导弹室", "damage": 4, "volley": 1,
              "reload_sec": 5.0, "ammo": 12}
    threat_map = {"engine_room": 6.0, "shield_room": 4.8, "weapon_room": 3.6,
                  "power_room": 4.4, "teleport": 4.8, "medbay": 2.4, "hangar": 2.4}
    rows = ev.evaluate(4, weapon, threat_map)
    scores = [r.score for r in rows]
    assert scores == sorted(scores, reverse=True)
    assert rows[0].room_id == "engine_room"


def test_efficiency_deterministic():
    data = load_game_data()
    ev = EfficiencyEvaluator(data)
    weapon = {"id": "missile_room", "name": "导弹室", "damage": 4, "volley": 1,
              "reload_sec": 5.0, "ammo": 12}
    threat_map = {"engine_room": 6.0, "shield_room": 4.8}
    r1 = ev.evaluate(4, weapon, threat_map)
    r2 = ev.evaluate(4, weapon, threat_map)
    assert r1 == r2


# ─────────── PowerOptimizer：策略模板 ───────────

def test_optimizer_aa_conditional():
    data = load_game_data()
    opt = PowerOptimizer(data)
    plans = opt.optimize(4, ["aa_laser", "shield_room"])
    aa = next(p for p in plans if p.room_id == "aa_laser")
    shield = next(p for p in plans if p.room_id == "shield_room")
    assert aa.tier == "conditional"
    assert aa.commands[0].condition.id == "cond_enemy_has_craft"
    assert shield.tier == "always"
    assert shield.commands[0].action.id == "act_set_max_power"


def test_optimizer_security_gate_py_diff():
    data = load_game_data()
    opt = PowerOptimizer(data)
    # PY2（L6）：看敌方传送室
    p2 = opt.optimize(6, ["security_gate"])
    gate2 = next(p for p in p2 if p.room_id == "security_gate")
    assert gate2.commands[0].condition.id == "cond_enemy_teleport_hp"
    # PY3（L7）：看本房间有无敌人
    p3 = opt.optimize(7, ["security_gate"])
    gate3 = next(p for p in p3 if p.room_id == "security_gate")
    assert gate3.commands[0].condition.id == "cond_my_room_has_enemy"
