# AGENTS

## 概述

- 轻量、协程异步的 WebSocket 远程调用服务：浏览器注入 js 客户端注册动作处理器，Python 侧通过 `GET /send` 调用并取回浏览器执行结果，面向 JS 逆向、混淆加密演示场景。
- 单进程双服务：HTTP（`/send`）与 WS（`/register`、`/invoke`）同进程启动，连接注册表是进程内内存状态。
- 协议由端到端测试锁定（成功往返、动作失败透传、组内无客户端、缺参四条路径）；实战背景见 README 中的 blog 链接。

## 技术栈

- Python `>=3.10`，本仓库经 `.python-version` 钉 `3.14`（证据：`pyproject.toml`、`.python-version`）
- `sanic`（HTTP）、`websockets>=14` 新版 asyncio API、`loguru`（证据：`pyproject.toml`）
- 开发依赖组：`pytest`、`pytest-asyncio`、`httpx`（证据：`pyproject.toml` 的 `[dependency-groups]`）
- uv 管理依赖（`pyproject.toml` + `uv.lock` 唯一事实源）、src 布局、hatchling 构建

## 目录结构

- `src/jsrpc/`: 服务包。`config`（环境变量配置）/ `registry`（连接注册表）/ `ws_server`（协议路由）/ `http_server`（`/send` 入口）/ `main`（进程入口）
- `src/jsrpc/static/`: 注入浏览器端的 `client.js`（协议参考实现）
- `tests/`: 注册表单元测试 + 端到端协议测试（e2e 自管子进程与随机端口）
- `nb/specs/`: Spec Coding 过程产物（spec、验收场景与裁决记录）
- 根目录: `README.md`（使用者文档）、`pyproject.toml`、`uv.lock`、`.python-version`

## 编码规范

- 模块以中文 docstring 写明职责与协议/契约约束；统一 `from __future__ import annotations` + 现代类型注解（`X | None`）
- 日志统一 `loguru`，不用 `print`
- 注册表的失败信号返回 `None`、不抛异常，由 WS/HTTP 层翻译成结构化错误（证据：`src/jsrpc/registry.py`）
- 无 lint/formatter 配置，遵循现有文件风格，待补充统一规范

## 常用命令

- `uv sync`: 安装运行 + 开发依赖到 `.venv`
- `uv run jsrpc-server`: 单进程启动 HTTP+WS；`JSRPC_HTTP_HOST/JSRPC_HTTP_PORT/JSRPC_WS_HOST/JSRPC_WS_PORT` 可覆盖，默认 `127.0.0.1:5000` 与 `127.0.0.1:6789`
- `uv run pytest`: 全量单元 + 端到端测试，无需手工启动服务

## 禁止事项

- 不修改对外协议字段（js 客户端报文、`/send` 返回形状、`__uuid_seq__` 语义）：改动须先有端到端测试并评估与已在页面注入的旧 `client.js` 的兼容性
- 不新增第二份依赖清单（如 requirements.txt）；依赖只经 uv 安装，不向 `.venv` 直接 `pip install`
- 不摘除 Sanic 的 `single_process=True`、不开启多 worker：注册表与 WS 服务是进程内状态，多进程会破坏 RPC 路由（证据：`src/jsrpc/main.py` 注释）
- 不提交 `.venv`、缓存与任何密钥；不改写历史（不 force push、不 amend）

## 导航

- 当要改协议字段、路由语义或失败路径、需要确认验收边界时，读取 `nb/specs/2026-09-22-uv-migration-refactor.md`：uv 迁移重构的验收场景、协议不变范围与执行期裁决

## 项目陷阱

- Sanic 25 下 `workers=1` 仍走多进程管理器，子进程按名字重导入 app 会报 “app name not found” 启动失败；单进程须显式 `single_process=True`；证据：`src/jsrpc/main.py`
- `client.js` 的 clientId 每次页面加载生成一次、断线重连复用；注册表注销必须按连接身份校验，否则旧连接迟到的注销会误删重连后的新注册、该组静默不可用；证据：`tests/test_registry.py::test_stale_unregister_does_not_evict_reconnected_client`
- `websockets>=14` 已移除旧式双参 handler `(websocket, path)` 签名；单参签名、路径从 `ws.request.path` 解析；证据：`src/jsrpc/ws_server.py` 头注释
- 本机仓库 `core.autocrlf=true`，CRLF 行尾会让文本在肉眼 diff 下看似相同或不同；“文件逐字节一致”的结论必须用 `cmp`/md5，不能靠打印比对；证据：`git config core.autocrlf`
