"""/generate 全流程：快照确定性 + API 集成 + LLM 降级。"""
import json

import pytest
from fastapi.testclient import TestClient

from app.core.orchestrator import Orchestrator
from app.llm.client import LLMUnavailable
from app.schemas.models import GenerateRequest, TargetRef


@pytest.fixture(scope="module")
def orch():
    return Orchestrator()


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


def _req(**kw):
    base = dict(level=4, target=TargetRef(type="room", id="missile_room"), quick_pick="集火引擎")
    base.update(kw)
    return GenerateRequest(**base)


def test_snapshot_deterministic(orch):
    """同一输入 → 同一输出（快照锁定）。"""
    r1 = orch.generate(_req())
    r2 = orch.generate(_req())
    assert r1.model_dump_json() == r2.model_dump_json()
    # 快照关键字段
    snap = json.loads(r1.model_dump_json())
    assert snap["ship_level"] == 4
    assert snap["pairing_matrix"][0]["target"] == "engine_room"
    assert snap["ammo_plan"]["mode"] == "normal"
    assert snap["power_plan"]["status"] == "ok"


def test_generate_without_llm_no_degraded(orch):
    r = orch.generate(_req())
    assert r.degraded is False
    assert "【编程清单】" in r.explanation  # 内置模板


def test_generate_with_intent_llm_mock(orch, monkeypatch):
    """LLM 意图解析成功路径（mock 返回 JSON）。"""
    calls = []

    def fake_chat_json(self, system, user):
        calls.append(user)
        return {"priority": ["engine_room"], "mode": "focus_fire",
                "conserve_ammo": False, "protect_rooms": []}

    # 直接 mock client 层
    from app.llm import client as llm_client
    monkeypatch.setattr(llm_client.LLMClient, "chat_json", fake_chat_json)
    monkeypatch.setattr("app.core.orchestrator.polish_explanation", lambda c, s: "润色后的讲解")

    r = orch.generate(_req(intent="集中火力打引擎", llm_config={
        "base_url": "http://mock", "api_key": "test", "model": "mock"}))
    assert r.degraded is False
    assert "润色后的讲解" == r.explanation
    assert calls, "意图解析应被调用"


def test_generate_llm_failure_degrades(orch, monkeypatch):
    """LLM 全挂 → 降级仍返回结果。"""
    def boom(self, *a, **k):
        raise LLMUnavailable("mock down")
    from app.llm import client as llm_client
    monkeypatch.setattr(llm_client.LLMClient, "chat", boom)
    monkeypatch.setattr(llm_client.LLMClient, "chat_json", boom)

    r = orch.generate(_req(intent="随便打打", llm_config={
        "base_url": "http://mock", "api_key": "test", "model": "mock"}))
    assert r.degraded is True
    assert r.commands, "降级后仍应输出编程清单"


def test_generate_level2_no_ai(orch):
    with pytest.raises(ValueError, match="4 级解锁"):
        orch.generate(_req(level=2, target=TargetRef(type="room", id="laser_room")))


# ─────────── API 集成 ───────────

def test_api_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_api_ship_levels(client):
    r = client.get("/api/v1/ship-levels")
    assert r.status_code == 200
    levels = r.json()
    assert len(levels) == 10
    assert levels[3]["ai_enabled"] is True


def test_api_rooms(client):
    r = client.get("/api/v1/rooms?level=4")
    assert r.status_code == 200
    ids = [x["id"] for x in r.json()]
    assert "missile_room" in ids
    assert "pp_room" not in ids  # 7 级才解锁


def test_api_crew(client):
    r = client.get("/api/v1/crew")
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_api_modules(client):
    r = client.get("/api/v1/modules")
    assert r.status_code == 200
    assert any(c["id"] == "cond_enemy_has_craft" for c in r.json()["conditions"])


def test_api_generate_ok(client):
    payload = {
        "level": 4,
        "target": {"type": "room", "id": "missile_room"},
        "quick_pick": "集火引擎",
    }
    r = client.post("/api/v1/generate", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ship_level"] == 4
    assert body["pairing_matrix"][0]["target"] == "engine_room"
    assert body["commands"]


def test_api_generate_422_no_ai(client):
    payload = {"level": 2, "target": {"type": "room", "id": "laser_room"}}
    r = client.post("/api/v1/generate", json=payload)
    assert r.status_code == 422
    assert "4 级解锁" in r.json()["detail"]


def test_api_generate_422_bad_level(client):
    payload = {"level": 99, "target": {"type": "room", "id": "laser_room"}}
    r = client.post("/api/v1/generate", json=payload)
    assert r.status_code == 422
