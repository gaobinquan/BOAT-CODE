"""API 路由（薄层：参数校验 + 限流；业务在 Orchestrator）。"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, Request

from ..core.orchestrator import Orchestrator
from ..core.validator import ValidationError
from ..dataloader import load_game_data
from ..llm.client import LLMClient, LLMUnavailable
from ..schemas.models import GenerateRequest, LLMConfig

router = APIRouter(prefix="/api/v1")

# ─────────── 限流：每 IP 20 次/分钟 ───────────
RATE_LIMIT = 20
RATE_WINDOW = 60.0
_hits: defaultdict = defaultdict(deque)


def rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    q = _hits[ip]
    while q and now - q[0] > RATE_WINDOW:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试（每 IP 20 次/分钟）")
    q.append(now)


def get_orchestrator() -> Orchestrator:
    return Orchestrator(load_game_data())


# ─────────── 只读端点 ───────────

@router.get("/health", dependencies=[Depends(rate_limit)])
def health():
    return {"status": "ok"}


@router.get("/ship-levels", dependencies=[Depends(rate_limit)])
def ship_levels():
    data = load_game_data()
    return [
        {
            "level": lv.level,
            "ai_enabled": lv.ai_enabled,
            "ai_slots": lv.ai_slots,
            "python_ver": lv.python_ver,
            "reactor_output": lv.reactor_output,
            "available_rooms": lv.available_rooms,
        }
        for lv in sorted(data.levels.values(), key=lambda l: l.level)
    ]


@router.get("/rooms", dependencies=[Depends(rate_limit)])
def rooms(level: int):
    data = load_game_data()
    if level not in data.levels:
        raise HTTPException(status_code=422, detail=f"无效等级: {level}")
    lv = data.get_level(level)
    return [
        {
            "id": r.id, "name": r.name, "category": r.category,
            "max_power": r.max_power, "ai_slots": r.ai_slots,
            "weapon": r.weapon.model_dump() if r.weapon else None,
            "threat": r.threat,
        }
        for r in (data.get_room(rid) for rid in lv.available_rooms)
    ]


@router.get("/crew", dependencies=[Depends(rate_limit)])
def crew(level: int | None = None):
    data = load_game_data()
    if level is not None and level not in data.levels:
        raise HTTPException(status_code=422, detail=f"无效等级: {level}")
    return [
        {"id": c.id, "name": c.name, "stars": c.stars,
         "role": c.role, "skills": c.skills, "ai_slots": c.ai_slots}
        for c in data.crew.values()
    ]


@router.get("/modules", dependencies=[Depends(rate_limit)])
def modules():
    data = load_game_data()
    return {
        "conditions": [
            {"id": c.id, "name": c.name, "python_ver": c.python_ver,
             "params": [p.model_dump() for p in c.params]}
            for c in data.conditions.values()
        ],
        "actions": [
            {"id": a.id, "name": a.name, "python_ver": a.python_ver,
             "params": [p.model_dump() for p in a.params]}
            for a in data.actions.values()
        ],
    }


# ─────────── 主端点 ───────────

@router.post("/generate", dependencies=[Depends(rate_limit)])
def generate(req: GenerateRequest, orch: Orchestrator = Depends(get_orchestrator)):
    try:
        return orch.generate(req)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ─────────── LLM 连通性测试 ───────────

@router.post("/llm/test", dependencies=[Depends(rate_limit)])
def llm_test(config: LLMConfig):
    try:
        reply = LLMClient(config).chat(
            "你是连通性测试。", "请只回复 OK 两个字。")
        return {"ok": True, "reply": reply}
    except LLMUnavailable as e:
        return {"ok": False, "error": str(e)}
