# BOAT-CODE 工作交接

> 上次更新：2026-10-31 晚。下次继续时先读这份文件。

## 一句话状态

后端 v0.1.0 完成并推送（main @ 60bb5ba）；**正在等用户提供国服数据做校正**；前端界面与 exe 打包暂停。

## 已完成

- [x] 设计规格（docs/superpowers/specs/2026-10-31-boat-code-design.md）
- [x] 后端 v0.1.0：FastAPI + 6 模拟器 + 决策整合 + LLM 可降级 + 44 测试全过
- [x] README 重写（玩家上手 + 部署者数据校正双导向）
- [x] 数据收集模板（docs/data_collection_template.md，已推送到 GitHub）

## 进行中 / 暂停

| 事项 | 状态 | 说明 |
|---|---|---|
| 数据校正 | **等待用户** | 用户填 docs/data_collection_template.md 的 7 张表（优先第 1-3 表：房间/等级/模块译名），填好后只改 backend/data/*.yaml，不动引擎 |
| 前端界面 | 暂停 | 半成品 backend/frontend/index.html（HTML+CSS 结构完成，JS 未写，占位符 <!--JS_PLACEHOLDER-->，未提交） |
| exe 打包 | 未开始 | 用户想要双击即用的桌面软件（PyInstaller 单 exe + 自动开浏览器），方案已定，等前端之后做 |

## 下次怎么继续

1. 用户发来数据 → 改 backend/data 对应 YAML → `cd backend && python -m pytest -q` → 提交推送
2. 用户说「继续前端」→ 从 index.html 的 JS_PLACEHOLDER 接着写 JS（约定：文件只用单引号，避免反引号和双引号）
3. 用户说「打包 exe」→ 写桌面启动器（uvicorn 线程 + webbrowser.open）+ PyInstaller spec（数据文件用 sys._MEIPASS）
4. 用户说「部署」→ 服务器 Docker：`docker compose up -d`（本机无 Docker，未验证构建）

## 关键路径

```
docs/data_collection_template.md    ← 用户要填的数据表（当前阻塞项）
backend/data/*.yaml                ← 游戏数据（7 个，改这里）
backend/app/core/integrator.py     ← 决策整合（战略生成核心）
backend/app/sim/                   ← 6 个模拟器
backend/app/llm/                   ← LLM 客户端/意图解析/润色（可降级）
backend/frontend/index.html        ← 前端半成品（未提交）
backend/tests/                     ← 44 个测试
```

## 常用命令

```bash
# 启动（Swagger 在 http://localhost:8000/docs）
cd backend && uvicorn app.main:app --port 8000
# 测试
cd backend && python -m pytest -q
# 打包 exe（待做）
pyinstaller --onefile ...
```

## 注意事项

- 数据文件加载时经 Pydantic 校验，写错立即报错（这是特性）
- LLM Key 不落盘不写日志；LLM 挂了自动降级，degraded=true
- 快捷选项 5 个：拆盾优先/集火引擎/压制维修/保电力室/省弹打法
- 前端 HTML 约定只用单引号（曾因反引号/双引号转义踩坑）
- 本机无 Docker，Dockerfile 未验证
