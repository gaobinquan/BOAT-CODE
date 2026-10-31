"""OpenAI 兼容 LLM 客户端（httpx 同步，超时 10s，失败抛 LLMUnavailable）。

Key 仅存在于请求内存：不落盘、不写日志、不缓存。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import httpx

from ..schemas.models import LLMConfig


class LLMUnavailable(Exception):
    """LLM 不可用（Key 无效/超时/无网络），触发降级。"""


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config

    def chat(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
    ) -> str:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        payload: Dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            resp = httpx.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                timeout=self.config.timeout_sec,
            )
        except httpx.HTTPError as e:
            raise LLMUnavailable(f"LLM 请求失败: {type(e).__name__}") from e
        if resp.status_code != 200:
            raise LLMUnavailable(f"LLM 返回 {resp.status_code}")
        try:
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            raise LLMUnavailable(f"LLM 响应格式异常: {e}") from e
        return content

    def chat_json(self, system: str, user: str) -> Optional[dict]:
        """JSON 模式对话；解析失败返回 None。"""
        try:
            content = self.chat(system, user, json_mode=True)
            return json.loads(content)
        except (LLMUnavailable, json.JSONDecodeError):
            return None
