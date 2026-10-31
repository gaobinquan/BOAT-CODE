# BOAT-CODE 设计规格：超时空星舰 AI 编程生成器

日期：2026-10-31
状态：待用户审阅

## 1. 概述

### 1.1 背景

《超时空星舰》（Pixel Starships 国服）中，玩家需要为每个能力房间与船员配置 AI 指令（条件→动作模块）。游戏内 AI 为图形化模块，**无法外部导入**，玩家只能照着设置。社区内玩家缺乏一套系统的编程思路，尤其在以下方面：

- 攻击目标选择不科学（不清楚打哪个房间更有效率）
- 武器弹药伤害缺乏规划（有限弹药武器何时停手）
- 电力分配浪费（常开不用的房间、该关电不关）

### 1.2 目标

做一个**网页工具**，投放到玩家群使用：玩家输入舰船等级、编程对象与意图，工具生成**分步设置清单**（玩家照着在游戏里点模块），并附电量方案、弹药规划与战略说明。

### 1.3 成功标准

1. 同一输入 → 同一输出（规则引擎确定性，可快照测试）
2. 数值计算（电力、弹药、击破轮数）由代码精确完成，不依赖 LLM 计算
3. LLM 完全不可用时（Key 无效/超时/无网络）工具仍可用（降级模式）
4. 数据文档到达后，只改 `data/` 数据文件，不改引擎代码
5. Docker 一条命令部署，群友浏览器即用

## 2. 用户流程（优化后）

原始流程"问等级→问对象→出脚本"优化为五步：

```
① 问舰船等级(1-10)
   → 确定约束：可用房间/船员、AI 指令槽数（指挥室等级）、
     Python 版本(PY2/PY3，即国服"蟒蛇"技术)、反应堆总电力

② 问编程对象（房间或船员）
   → 按等级过滤后展示可选对象，含每个对象的模块清单

③ 问目标偏好/意图（自然语言 + 快捷选项）
   → 快捷选项：拆盾优先 / 压制维修 / 集火引擎 / 保电力室 / 我自己描述
   → LLM 将自然语言解析为结构化参数；LLM 失败则用快捷选项参数

④ 引擎整合判断（本地规则引擎，确定性）
   威胁×效率 → 武器×目标配对 → 弹药规划 → 电力预算优化 → 帧时序校验

⑤ 输出
   分步设置清单 + 配对矩阵 + 电力方案 + 战略总述 + LLM 润色说明
```

## 3. 数据模型（`backend/data/*.yaml`，数据与代码分离）

### 3.1 模块注册表 `modules.yaml`

游戏内 AI 指令 = 条件 + 动作，全部参数化登记。字段：

```yaml
conditions:
  - id: cond_enemy_has_craft
    name: "敌方已部署战机"
    python_ver: [2, 3]        # 可用 Python 版本
    params: []
  - id: cond_room_hp_below
    name: "本房间HP低于"
    params: [{name: "百分比", type: int, range: [0, 100]}]

actions:
  - id: act_set_power
    name: "设置房间电力"
    python_ver: [2, 3]
    params: [{name: "电力值", type: int, range: [0, 8]}]
  - id: act_attack_room
    name: "攻击目标房间"
    params: [{name: "目标房间", type: room_ref}]
```

已核实的常用模块（初始数据，待用户文档对齐国服译名）：

- 条件：无条件(None)、敌方房间HP低于X%、敌舰满血、敌舰满盾、目标房间有敌人、目标房间被摧毁、目标房间满血、敌方房间满血、敌方反应堆HP>0、敌方已部署战机、敌方导弹HP>0、敌方传送室HP>0、我方房间有敌人
- 动作：电力+1/电力−1、设置电力X、设置满电力、攻击条件房间、攻击敌方XX房间、继续当前任务、设置最高船员伤害

### 3.2 房间数据 `rooms.yaml`

```yaml
- id: missile_room
  name: "导弹室"
  category: weapon          # weapon/utility/defense/support
  min_ship_level: 2
  max_power: 3
  weapon: {damage: 4, volley: 1, reload_sec: 5.0, ammo: 12}
  ai_slots: 2
  threat: 3                 # 作为敌方目标时的威胁度，默认值待用户评判
  notes: ""
```

### 3.3 船员数据 `crew.yaml`

```yaml
- id: galaxy_alchemist
  name: "银河炼金术士"
  stars: 5
  role: offensive           # offensive/repair/pilot/special
  skills: [fire]
  ai_slots: 2
```

### 3.4 等级约束 `levels.yaml`（1-10 级）

```yaml
- level: 4
  ai_enabled: true          # 4级建指挥室解锁 AI
  ai_slots: 3               # 指挥室提供总指令槽
  python_ver: 2             # 蟒蛇技术升级后为 3
  reactor_output: 10        # 总电力，初值待用户校正
  available_rooms: [laser_room, missile_room, shield_room]
```

### 3.5 威胁度表 `threats.yaml`（预留，待用户评判）

```yaml
engine_room:  {base: 5, note: "打断机动与逃跑"}
shield_room:  {base: 4, note: "拆盾后全舰效率提升"}
weapon_room:  {base: 3, note: ""}
power_room:   {base: 4, note: "瘫痪全舰电力"}
teleport:     {base: 4, note: "压制登舰船员"}
```

### 3.6 敌方房间数据 `enemy_rooms.yaml`（攻击效率评估输入）

按舰船等级的敌方各房间 HP/护甲修正/维修速率。初值用公开资料（PPG 房间 HP 表），**待用户提供国服准确数据校正**。

### 3.7 战斗场景假设 `battle_scenarios.yaml`

按等级的平均战斗时长、我方弹药总量假设，用于弹药规划判断"弹量是否够打完整场"。

### 3.8 生成结果（API 输出）

```json
{
  "target": {"type": "room", "id": "missile_room"},
  "ship_level": 4,
  "pairing_matrix": [
    {"weapon": "missile_room", "target": "engine_room", "mode": "focus_fire", "reason": "..."}
  ],
  "crew_assignments": [
    {"crew": "galaxy_alchemist", "task": "board_burn", "target_room": "power_room", "based_on": "效率分1.8"}
  ],
  "commands": [
    {"order": 1, "condition": {"id": "cond_none"},
     "action": {"id": "act_set_max_power"}, "note": "满电优先，帧1即满"}
  ],
  "power_plan": {"total": 10, "used": 8, "status": "ok", "warnings": []},
  "ammo_plan": {"volleys_to_kill": 3, "ammo_cost": 6, "mode": "normal"},
  "efficiency_ranking": [
    {"room": "engine_room", "score": 2.4, "volleys_to_kill": 3, "reason": "..."}
  ],
  "strategy": "拆盾→集火引擎→关电省弹",
  "explanation": "人类可读完整说明（LLM 润色，失败时用内置模板）"
}
```

## 4. 机制模拟器（6 个，`backend/app/sim/`）

### 4.0 已核实的游戏机制（设计依据）

- AI 按**帧**执行；每帧所有房间按**建造顺序**依次跑各自 AI
- **满电力(set max power)** 优先于**逐格加电(increase by one)**：满电房间帧 1 即满，其余房间帧 1 只有 1 格电；电力不足时按建造顺序分配
- 指令按**顺序**求值：第一条为真的"条件"执行其"动作"，后续跳过
- Python 版本(PY2/PY3)决定可用指令集（国服"蟒蛇"技术）
- 目标选择惯用模式：**集火**（continue current job）、**压制传送室**（敌舰满血→打传送室，条件房间残血→转打）、**轮换找维修船员**（目标满血→换房间）、**互补条件错峰用电**（两武器反向条件交替开电）

### 4.1 帧调度器 `FrameScheduler`

- 模拟逐帧执行：按建造顺序跑各房间指令链
- 输出时序冲突警告（多房间同帧抢电、满电 vs 逐格加电的优先级后果）

### 4.2 电力预算器 `PowerBudget`

- 输入：等级→反应堆总电力；各房间电力需求
- 校验：常开电力之和 ≤ 总电力；超支时按威胁度从低到高自动降档
- 电力三档位（电量优化核心）：
  - **常开**（护盾、维修）
  - **用后关闭/条件开**（防空：敌方有战机→开；无→关）
  - **半效率电**（伤害够用时不满电）
- 已核实的策略模板（初始数据）：
  - 防空激光：`敌方已部署战机→电力+1；无→电力−1`（比"敌方机库有血"更精确）
  - 安保门：`敌方传送室HP>0→电力+1`（PY2）/ `我方房间有敌人→电力+1`（PY3）
  - 护盾破坏者(PP/PD)：`敌舰满血→电力+1`（开场破盾，用敌舰满血而非"敌方有盾"，避免敌方护盾回充导致反复开关丢充能）
  - 引擎：`敌方导弹HP>0→电力+1`（敌方无导弹则白开）
  - 互补武器：A 武器 `敌舰满血→开`，B 武器 `无→开`，交替省电

### 4.3 弹药伤害规划器 `AmmoPlanner`

- 武器 DPS = 伤害×齐射 ÷ 装填时间；对照目标房间 HP 算击破轮数
- 有限弹药（导弹室）：弹量 vs 战斗时长假设 → 够打则集火，不够则省弹模式（只打高威胁目标）
- 生成攻击指令参数：打谁、何时停手转目标（条件：目标房间被摧毁→换目标）

### 4.4 威胁评估器 `ThreatEvaluator`

- 静态威胁度表 → 战略价值排序
- 我方武器适配修正（如激光拆盾快 → 对护盾权重上调）

### 4.5 攻击效率评估器 `EfficiencyEvaluator`

```
攻击效率分 = 威胁度 ÷ 击破成本(轮数×时间×弹药) × 修正系数
```

- 击破轮数 = 目标 HP ÷ 每轮有效伤害（护甲修正 × (1−维修抵消率)）
- 连锁收益修正：拆盾后全舰效率提升、打电力室瘫痪敌舰
- 输出排序表 + 推荐战略（拆盾优先/集火高威胁/直接打电力室）

### 4.6 电量优化器 `PowerOptimizer`

- 按房间类别套用策略模板库，为每条电力指令附"为什么"理由
- 理由文字由 LLM 润色；LLM 不可用时用内置模板文字

## 5. 决策整合与搭配层 `DecisionIntegrator`

### 5.1 整合流水线

```
[判断阶段]                     [搭配阶段]
威胁度判断 ─┐               ┌─ 武器×目标配对矩阵
效率判断 ───┼→综合目标优先级→├─ 房间指令链(攻击+电力+停止条件)
弹药判断 ───┘               ├─ 船员×任务配对
电力判断 ─────────────────→├─ 全舰电力方案
                            └─ 战略总述
```

### 5.2 搭配规则

- 武器×目标：高射速无限弹→护盾/低血量；高伤有限弹→高威胁目标；范围伤害→船员密集区；防空→战机。冲突时集火判定（击破时间缩短超阈值则合并集火，否则错开）
- 攻击指令×电力档位：如"导弹室满电→打引擎→引擎摧毁→关电"
- 船员×任务：进攻型登舰打效率排序第 1 房间；维修型守我方高威胁房间；舵手驻引擎
- 全舰电力：汇总→预算校验→超支按威胁度低者先降档

### 5.3 一致性终检

指令槽数 ≤ 上限、电力 ≤ 反应堆输出、模块存在且 Python 版本兼容、参数范围合法、无矛盾指令对（同房间同时开关电）——全部通过才输出。

## 6. 系统架构

### 6.1 分层

```
┌ 前端（后续做，暂用 Swagger UI）───────────────┐
│ 表单：等级→对象→意图→LLM配置(base_url/key/模型) │
└──────────────────┬───────────────────────────┘
┌──────────────────▼───────────────────────────┐
│ API 层 FastAPI：/health /ship-levels /rooms   │
│ /crew /generate /llm/test                     │
└──────┬───────────────────────┬───────────────┘
┌──────▼─────────┐    ┌────────▼───────────────┐
│ 意图解析器 LLM  │───▶│ 规则引擎 Orchestrator   │
│ (可降级)       │    │ →DecisionIntegrator    │
└────────────────┘    └────────┬───────────────┘
     ┌────────┬────────┬───────┼────────┬────────┐
     ▼        ▼        ▼       ▼        ▼        ▼
  威胁评估  效率评估  弹药规划  电力预算  电量优化  帧调度
     └────────┴────────┴───────┼────────┴────────┘
                        ┌──────▼──────┐
                        │ 验证器       │
                        └──────┬──────┘
                        ┌──────▼──────┐
                        │ LLM 润色    │（失败降级）
                        └──────┬──────┘
                               ▼ 输出 JSON
```

### 6.2 目录结构

```
BOAT-CODE/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 入口
│   │   ├── api/               # 路由（薄层，参数校验）
│   │   ├── core/              # Orchestrator + DecisionIntegrator
│   │   ├── sim/               # 6 个模拟器，独立可测
│   │   ├── llm/               # OpenAI 兼容客户端/意图解析/润色
│   │   ├── schemas/           # Pydantic 模型（含数据文件校验）
│   │   └── dataloader.py      # YAML 加载+缓存
│   ├── data/                  # modules/rooms/crew/levels/threats/enemy_rooms/battle_scenarios.yaml
│   └── tests/                 # 单元/集成/快照
├── frontend/                  # 后续
├── docker-compose.yml
└── README.md
```

### 6.3 请求数据流

1. `GET /rooms?level=4` → 等级过滤后的可选对象
2. `POST /generate {level, target, intent?, llm_config}`：
   - 加载数据 → 意图解析(LLM，失败降级) → 编排 6 模拟器 → 整合搭配 → 验证 → LLM 润色(失败降级) → 输出
3. LLM 配置仅存浏览器 localStorage，服务端不落盘、不写日志

## 7. API 设计

| 端点 | 方法 | 说明 |
|---|---|---|
| `/api/v1/health` | GET | 健康检查 |
| `/api/v1/ship-levels` | GET | 1-10 级约束列表 |
| `/api/v1/rooms?level=` | GET | 该等级可用房间 |
| `/api/v1/crew?level=` | GET | 该等级可用船员 |
| `/api/v1/modules?target=` | GET | 对象可用模块清单 |
| `/api/v1/generate` | POST | 主端点（见 3.8 输出） |
| `/api/v1/llm/test` | POST | 连通性测试（base_url/key/模型） |

## 8. 错误处理与安全

| 场景 | 行为 |
|---|---|
| LLM 不可用/Key 无效/超时(10s) | 降级：跳过意图解析与润色，结果照常返回 + 提示 |
| 电力超支 | 200 + warnings + 修正建议 |
| 模块/参数无效、Python 版本不兼容 | 422 + 中文错误信息 |
| 刷接口 | 每 IP 限流 20 次/分钟，429 |
| Key 安全 | 不写日志、不落盘、不缓存 |

## 9. 测试策略

- 确定性：规则引擎纯函数，同输入同输出，快照测试锁定
- 模拟器单测：电力帧分配、弹药 DPS/击破轮数、威胁排序、效率分、帧时序
- 数据校验：YAML 加载时 Pydantic 校验，数据错误启动即报错
- 集成：`/generate` 全流程（LLM mock）；真实 LLM 走 `/llm/test`

## 10. 部署

- Docker：单容器 FastAPI + Uvicorn，`docker compose up -d` 一条命令
- 无状态服务，数据全在代码库内 YAML（更新数据 = 改 YAML + 重启）

## 11. 待办与依赖

| 依赖 | 状态 |
|---|---|
| 用户提供：人物/房间编程模块文档（国服译名） | 待给 → 填充 modules/rooms/crew |
| 用户提供：威胁度评判 或 房间数据 | 待给 → 填充 threats/enemy_rooms |
| 用户提供：等级 1-10 的电力/槽数/可用房间准确值 | 待给 → 校正 levels.yaml |
| 公开资料：PPG 房间 HP/DPS 表、pixyship.wiki | 已用，初值来源 |

## 12. 术语对照

| 国服 | 机制 |
|---|---|
| 蟒蛇技术 | Python 版本升级（PY2→PY3），扩展指令集 |
| 指挥室 | 4 级解锁 AI，等级决定指令槽 |
| 传送室 | 船员登舰通道（压制目标） |
| 满电力 | set max power（帧 1 即满，优先级最高） |
| 逐格加电 | increase power by one |
