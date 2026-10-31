"""FastAPI 入口：BOAT-CODE 超时空星舰 AI 编程生成器。

前端后续开发，暂用 Swagger UI（/docs）。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router

app = FastAPI(
    title="BOAT-CODE 超时空星舰 AI 编程生成器",
    description="输入舰船等级、编程对象与意图，生成游戏内 AI 分步设置清单。",
    version="0.1.0",
)

# 后续前端开发时放开跨域；当前 Swagger 本地使用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
