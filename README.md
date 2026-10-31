# BOAT-CODE 超时空星舰 AI 编程生成器

《超时空星舰》（Pixel Starships 国服）玩家的 AI 编程助手：输入舰船等级、编程对象与意图，
生成游戏内 AI 分步设置清单（条件→动作模块），附配对矩阵、电力方案、弹药规划与战略说明。

设计规格：`docs/superpowers/specs/2026-10-31-boat-code-design.md`

## 快速开始

### Docker 一条命令（推荐）

```bash
docker compose up -d
# 打开 http://localhost:8000/docs （Swagger UI，前端开发前暂用它）
```

### 本地开发

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

跑测试：

```bash
cd backend
python -m pytest -q
```

## API

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/v1/health` | GET | 健康检查 |
| `/api/v1/ship-levels` | GET | 1-10 级约束 |
| `/api/v1/rooms?level=` | GET | 该等级可用房间 |
| `/api/v1/crew?level=` | GET | 可用船员 |
| `/api/v1/modules` | GET | AI 模块注册表 |
| `/api/v1/generate` | POST | 主端点（生成编程清单） |
| `/api/v1/llm/test` | POST | LLM 连通性测试 |

示例：

```bash
curl -X POST http://localhost:8000/api/v1/generate \\
  -H "Content-Type: application/json" \\
  -d '{"level":5,"target":{"type":"room","id":"laser_room"},"quick_pick":"拆盾优先"}'
```

快捷选项（quick_pick）：拆盾优先 / 压制维修 / 集火引擎 / 保电力室 / 省弹打法。
也可给 `intent` 自然语言 + `llm_config`（base_url/api_key/model，仅存请求内，不落盘不写日志）；
LLM 不可用时自动降级为快捷选项参数与内置说明模板，工具照常可用。

## 数据

全部游戏数据在 `backend/data/*.yaml`（**初值来自公开资料 PPG/pixyship.wiki，待国服数据校正**）。
校正数据只需改 YAML + 重启，不改引擎代码。

## 目录

```
backend/
├── app/
│   ├── main.py          # FastAPI 入口
│   ├── api/routes.py    # 路由 + 限流（20 次/分钟/IP）
│   ├── core/            # Orchestrator + DecisionIntegrator + 验证器 + 意图参数
│   ├── sim/             # 6 模拟器（帧调度/电力预算/弹药/威胁/效率/电量优化）
│   ├── llm/             # OpenAI 兼容客户端/意图解析/润色（可降级）
│   ├── schemas/         # Pydantic 模型
│   └── dataloader.py    # YAML 加载 + 校验 + 缓存
├── data/                # 7 个 YAML 数据文件
└── tests/               # 44 个测试（单测/快照/集成）
```
