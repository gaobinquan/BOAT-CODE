# BOAT-CODE 超时空星舰 AI 编程生成器

> 输入舰船等级 + 编程对象 + 战术意图，生成游戏里照着点的 AI 分步设置清单。
> 附配对矩阵、电力方案、弹药规划与效率排名——不再凭感觉打房间。

《超时空星舰》（Pixel Starships 国服）每个房间和船员都要手动配 AI 指令，但游戏里只能照着点、无法导入。
大多数玩家卡在三个问题上：**不知道先打哪个房间**、**有限弹药武器不知道何时停手**、**电力常年浪费**。
这个工具把「威胁 × 效率 × 弹药」用规则引擎算清楚，输出一份玩家直接照着操作的清单。

## 特性

- **确定性引擎**：同一输入永远同一输出，数值（击破轮数/弹药/电力）全部由代码精确计算，不靠 AI 编数
- **离线可用**：不配 LLM 也能用，配了 LLM 支持自然语言意图 + 讲解润色，挂了自动降级
- **数据与代码分离**：游戏数据全部在 YAML 里，国服数据文档到手后只改数据文件，不动引擎
- **一条命令部署**：Docker 起服务，群友浏览器直接用（暂用 Swagger UI，前端开发中）

## 效果预览

输入：5 级舰 · 编程对象「激光室」· 意图「拆盾优先」，得到：

```
【编程清单】
1. 条件「目标房间被摧毁」→ 动作「攻击敌方XX房间」teleport（主目标摧毁后转打次级目标 teleport）
2. 条件「无条件」→ 动作「攻击敌方XX房间」shield_room（集火 shield_room；房间电力保持满电（帧1即满））

【配对矩阵】
- laser_room → 护盾室（solo，无限弹药持续压制）

【电力方案】
- 反应堆 9，常开用 6，状态 ok
- 防空激光：敌方有战机才耗电防空，无战机则关电
- 引擎室：敌方有导弹时才耗电机动，无导弹则白开

【战略】主攻目标：护盾室（效率分 14.77）→ 摧毁后转打 传送室
```

照着【编程清单】在游戏里把条件、动作依次点出来即可。

## 快速开始

### 方式一：Docker（推荐）

```bash
git clone <本仓库地址> && cd BOAT-CODE
docker compose up -d
```

### 方式二：本地 Python（Python 3.10+）

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 三步生成清单

打开 <http://localhost:8000/docs>（Swagger UI）：

1. **先看数据**：`GET /api/v1/rooms?level=5` 看看该等级有哪些房间可选；
2. **发请求**：找到 `POST /api/v1/generate` → Try it out，填：
   - `level`：舰船等级（1-10，**4 级解锁指挥室 AI**）
   - `target`：编程对象，如 `{"type":"room","id":"laser_room"}`（房间）或 `{"type":"crew","id":"galaxy_alchemist"}`（船员）
   - `quick_pick`：选一个快捷选项（见下表），不填则按效率排序自动决策
3. **照着点**：返回结果里的 `commands` 就是分步清单，一条条在游戏里点出来。

## 快捷选项速查

| quick_pick | 干什么用 | 典型场景 |
|---|---|---|
| `拆盾优先` | 先拆护盾，全舰输出效率提升 | 对面盾厚，打不动 |
| `集火引擎` | 集中打引擎，打断机动与逃跑 | 对面残血想跑 / 一直遛你 |
| `压制维修` | 压医务室 + 传送室，断奶断兵 | 对面有奶妈船员 / 登舰流 |
| `保电力室` | 守我方电力室，防断电 | 对面喜欢登舰拆电 |
| `省弹打法` | 有限弹药只在开局（敌舰满血）开火，掉血即关电 | 导弹室弹药不够打整场 |

也可以不选快捷选项，改填 `intent` 自然语言（如「集中火力先拆盾再打引擎」）+ LLM 配置，见下文。

## 生成结果怎么看

| 字段 | 含义 |
|---|---|
| `commands` | **核心**。分步设置清单，`order` 是顺序，`condition`→`action` 照着点，`note` 解释为什么 |
| `pairing_matrix` | 武器 × 目标配对：哪个武器打哪个房间、集火还是单独打 |
| `power_plan` | 电力预算：反应堆总量、常开用量、超支警告与降档建议 |
| `ammo_plan` | 弹药规划：击破需几轮几发、弹量是否够打整场（够=集火，不够=省弹） |
| `efficiency_ranking` | 敌方各房间攻击效率排名（威胁 ÷ 击破成本），战略选择的依据 |
| `strategy` / `explanation` | 一句话战略 + 完整人类可读说明 |
| `warnings` | 帧时序提示（条件开房间帧 1 无电等）与指令槽裁剪记录 |

`degraded: true` 表示 LLM 环节降级了，结果照常可用，只是说明文字用的是内置模板。

## LLM 增强（可选）

不配 LLM 也能用：快捷选项参数是内置的，说明文字有内置模板。
配了 LLM 后可以：

- `intent` 写自然语言（「打引擎，省着点导弹」），由 LLM 解析为结构化战术参数；
- 生成的说明文字由 LLM 润色得更口语化。

配置方式：在请求体里加 `llm_config`（OpenAI 兼容接口）：

```json
{
  "level": 5,
  "target": {"type": "room", "id": "missile_room"},
  "intent": "省着点弹药，优先打引擎",
  "llm_config": {
    "base_url": "https://api.deepseek.com/v1",
    "api_key": "你的key",
    "model": "deepseek-chat",
    "timeout_sec": 10
  }
}
```

Key 安全：仅存在于单次请求内存，服务端**不落盘、不写日志、不缓存**。
（正式前端上线后 Key 存玩家浏览器 localStorage，也不经过服务端持久化。）

LLM 挂了怎么办：Key 无效/超时(10s)/断网时自动跳过 LLM 环节，按快捷选项参数 + 内置模板照常返回结果，
响应里 `degraded: true` 提示。

## API 参考

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/v1/health` | GET | 健康检查 |
| `/api/v1/ship-levels` | GET | 1-10 级约束（电力/指令槽/蟒蛇版本/可用房间） |
| `/api/v1/rooms?level=` | GET | 该等级可用房间及模块清单 |
| `/api/v1/crew?level=` | GET | 可用船员 |
| `/api/v1/modules` | GET | AI 条件/动作模块注册表 |
| `/api/v1/generate` | POST | 主端点：生成编程清单 |
| `/api/v1/llm/test` | POST | LLM 连通性测试 |

curl 示例：

```bash
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"level":5,"target":{"type":"room","id":"laser_room"},"quick_pick":"拆盾优先"}'
```

响应（节选，完整结构见 Swagger Schema）：

```json
{
  "ship_level": 5,
  "pairing_matrix": [{"weapon": "laser_room", "target": "shield_room", "mode": "solo"}],
  "commands": [
    {"order": 1, "condition": {"name": "目标房间被摧毁"},
     "action": {"name": "攻击敌方XX房间", "params": {"目标房间": "teleport"}}},
    {"order": 2, "condition": {"name": "无条件"},
     "action": {"name": "攻击敌方XX房间", "params": {"目标房间": "shield_room"}}}
  ],
  "power_plan": {"total": 9, "used": 6, "status": "ok"},
  "efficiency_ranking": [{"room": "teleport", "score": 21.62, "volleys_to_kill": 5.0}],
  "strategy": "主攻目标：护盾室（效率分 14.77）→ 摧毁后转打 传送室",
  "degraded": false
}
```

错误约定：模块/参数无效、蟒蛇版本不兼容、等级未解锁 AI → `422` + 中文错误；
刷接口 → 每 IP 20 次/分钟限流，`429`；电力超支不报错，返回 `warnings` + 降档建议。

## 数据校正（维护者）

全部游戏数据在 `backend/data/*.yaml`，加载时经 Pydantic 校验，写错启动/首次请求即报错。

| 文件 | 管什么 | 待校正内容 |
|---|---|---|
| `modules.yaml` | AI 条件/动作模块注册表 | 国服译名、模块可用蟒蛇版本 |
| `rooms.yaml` | 房间（类别/电力/武器数值/威胁度） | 国服译名、武器伤害与装填 |
| `crew.yaml` | 船员（星级/定位/技能） | 人物文档 |
| `levels.yaml` | 1-10 级约束 | 各等级准确电力、指令槽数、可用房间 |
| `threats.yaml` | 威胁度表 | 用户评判的威胁值 |
| `enemy_rooms.yaml` | 敌方房间 HP/护甲/维修速率 | 国服准确数值 |
| `battle_scenarios.yaml` | 战斗时长与弹药假设 | 实测数据 |

改完重启服务即可生效（数据文件与引擎代码完全解耦）。

## 项目结构

```
backend/
├── app/
│   ├── main.py          # FastAPI 入口（Swagger UI）
│   ├── api/routes.py    # 路由 + 限流
│   ├── core/            # Orchestrator 编排 + DecisionIntegrator 决策整合 + 一致性终检
│   ├── sim/             # 6 个模拟器：帧调度/电力预算/弹药/威胁/效率/电量优化
│   ├── llm/             # OpenAI 兼容客户端/意图解析/润色（全部可降级）
│   ├── schemas/         # Pydantic 模型（数据文件与 API 双校验）
│   └── dataloader.py    # YAML 加载 + 校验 + 缓存
├── data/                # 7 个 YAML 数据文件
└── tests/               # 44 个测试：单测/确定性快照/API 集成/LLM 降级
```

设计依据（帧时序、满电 vs 逐格、集火模式等已核实机制）见
`docs/superpowers/specs/2026-10-31-boat-code-design.md`。

## 测试

```bash
cd backend && python -m pytest -q
```

覆盖：模拟器纯函数单测、数据文件校验、`/generate` 全流程快照（同输入同输出）、
LLM mock 与降级路径、API 集成（含 422/429 约定）。

## FAQ

**Q：等级 1-3 为什么生成不了？**
A：4 级建指挥室才解锁 AI。1-3 级返回 422 中文提示。

**Q：数据好像不准？**
A：初值来自公开资料（PPG / pixyship.wiki），国服数据在校正中。提供准确数据只需改 `backend/data/*.yaml`。

**Q：没有 Docker 怎么跑？**
A：方式二本地 Python 一样跑，FastAPI 无需数据库，纯无状态服务。

**Q：我的 LLM 服务不是 OpenAI 格式？**
A：任何兼容 `/chat/completions` 的接口都可以（DeepSeek、通义、本地 Ollama 等），填对应 base_url 即可。

**Q：429 是什么？**
A：每 IP 20 次/分钟限流，稍等一分钟再试。

## 路线图

- [x] 后端 v0.1.0：规则引擎 + 6 模拟器 + LLM 可降级 + Docker
- [ ] 国服数据校正（待玩家提供准确文档）
- [ ] Web 前端：等级→对象→意图三步表单，替换 Swagger UI
- [ ] 生成结果一键复制/图片分享（方便发群）
