---
artifact: spec
mode: standard
status: completed
created: 2026-09-22
---

# HTTP 层从 Sanic 迁移到 FastAPI + Uvicorn

## 问题与目标

诊断已证明（spec 前置调查，2026-09-22）：sanic 25.12.1 的清理链在 `http_server.wait_closed()`（Python 3.12+ 语义="等所有连接处理完"）处等待空闲 keep-alive 连接被 120s 的 `KEEP_ALIVE_TIMEOUT` 回收，且自身的 15s 排空超时（`GRACEFUL_SHUTDOWN_TIMEOUT` 默认）位于其后、无法兜底——Ctrl+C 后最长 ~2 分钟不退出，裸 Sanic 复现，与本项目代码无关。

完成后：HTTP 层由 FastAPI 承载、Uvicorn 作为服务器运行；对外 HTTP/WS 协议逐字段不变（现有 11 项测试零修改通过）；SIGINT 停止时空闲 keep-alive 不再引发百秒级等待，关闭时长由显式的 graceful 超时约束；进程模型（单进程单事件循环同时运行 HTTP 与 WS）不变。

## 范围

- 依赖替换：移除 sanic；新增 fastapi 与 uvicorn（不带 standard 附加组）。
- HTTP 层重写为 FastAPI 应用：`/send` 路由的查询参数合并规则（同名后者覆盖）、响应体形状、HTTP 状态码（含各错误路径 200 + `{"error": ...}`）、RPC 兜底超时行为与 sanic 版完全一致。
- 进程入口重写：uvicorn 以编程方式运行；WS 服务的启动/关闭挂入应用生命周期（startup 启动、shutdown 关闭监听并断开在连客户端），与 uvicorn 共享单一事件循环。
- 显式设置 graceful 关闭超时（10s），约束在途请求的等待上限。
- 新增关机语义回归测试；README 与 AGENTS.md 同步（技术栈、失效的 sanic 陷阱条目处置）。

## 非目标

- 不把 uvicorn 访问日志接入 loguru（uvicorn 保留自身 stdlib 日志）。
- 不引入 Pydantic 模型做请求校验、不定制 OpenAPI 文档页。
- 不改 WS 协议、注册表、js 客户端与任何对外报文。
- 不启用 uvloop（Windows 不可用）、不使用 uvicorn 的多 worker/reload。

## 验收场景

1. `uv sync` 成功后 `.venv` 中无 sanic；锁文件中无 sanic 残留解析。
2. `uv run jsrpc-server` 单进程同时监听默认 `127.0.0.1:5000`（HTTP）与 `127.0.0.1:6789`（WS）；四个 `JSRPC_*` 环境变量覆盖行为与迁移前一致（变量名不变）。
3. 现有端到端与单元测试**文件零修改**通过：成功往返、动作失败透传、组内无客户端、缺 `action`/缺 `group` 的报文与状态码均与 sanic 版一致。
4. 关机回归：程序化触发服务器退出（等价 SIGINT 路径）且存在一条空闲 keep-alive HTTP 连接时，服务器在 12s 内完成停止返回（对照 sanic 实测 ~100-120s），随后 WS 监听端口不再可达。
5. `uv run pytest` 全量（含新增关机回归）通过。
6. README 与 AGENTS.md 的技术栈、启动说明与仓库实况一致；AGENTS.md 中仅适用于 sanic 的陷阱/禁止条目被替换为迁移后的等价约束，不留下指向已删依赖的内容。

## 设计决策

- **换服务器不降协议**：`/send` 全部对外可观察行为逐字段保留。HTTP 层自产的错误响应共 6 条字符串、均为 200 + `{"error": ...}`：`need action`、`need group`、`cannot reach ws server`、`timeout waiting for webclient response`、`ws connection closed before response`、`invalid json from webclient`；成功路径将 WS 对端报文 `json.loads` 后原样返回（`no webclient registered for group ...`、`webclient of group ... is gone` 属 WS 层生成、HTTP 层仅透传，不在 HTTP 层重写范围）。现有测试锁定前两条错误、`no webclient` 子串、成功形状与状态码；**其余三条（`cannot reach ws server`、`ws connection closed before response`、`invalid json from webclient`）现状零测试覆盖，本枚举即唯一契约**，实现与自审须逐字对照。查询参数用 starlette 多值项的 last-wins 合并复现 sanic 手工字典语义。
- **生命周期拥有 WS 服务**：应用启动钩子里拉起 websockets 服务器（句柄存于应用状态），关闭钩子里 `close()` + 等待完成 + 对在连客户端发送关闭并回收任务——停止顺序可控，杜绝 sanic 式"清理链先卡在 HTTP 再顾不上别的"。
- **graceful 关闭超时必须显式设置**（10s）：uvicorn 该参数默认无限等待在途请求，不显式设就是在新栈重演旧坑；空闲 keep-alive 连接在 uvicorn 关闭序列中即时关闭（此为本次迁移的核心假设，由验收 4 的回归测试作为证据，若测试失败视为假设证伪、回到设计门）。
- uvicorn 不带 standard 附加组：Windows 无 uvloop 可用、本项目不经 uvicorn 提供 WS 端点，纯 h11 依赖面最小。
- 入口保持 `uv run jsrpc-server` 控制台命令与 `python -m jsrpc` 两种形态；配置读取模块不动。
- loguru 仅继续覆盖本包日志；uvicorn 的启动/关闭 stdlib 日志原样保留（demo 项目，日志统一不值得引入 intercept 机制）。

## 验证策略

- 协议不变：现有 e2e（起真实入口子进程、模拟 js 客户端、走公开 HTTP/WS）文件零修改全绿，即公开接缝上的完整回归；三条无测试覆盖的错误字符串按设计决策的枚举清单在实现与自审中逐字对照（为其新增协议触发测试需伪造 WS 对端行为，测试成本与收益不匹配）。
- 关机语义：新增测试在测试进程内以编程方式驱动 uvicorn 服务器停止（模拟 SIGINT 之后的关闭序列），停止前建立一条已响应完毕、保持打开的 keep-alive 连接，断言停止调用在 12s 内返回、端口关闭；红→绿基线用 sanic 时代 harness 的实测（RED@60s / GREEN@~100s）作对照证据。
- 运行验证：默认端口启动观察两个监听日志与失败路径 curl；`uv run pytest` 全量为完成门禁。

## 实现切片

- [x] **切片 1：HTTP 栈整体替换，协议回归全绿**
  - 触点：依赖声明（sanic→fastapi+uvicorn）、HTTP 服务模块、进程入口、WS 服务启停钩子
  - 验证：`uv run pytest`（11 项既有测试，文件零修改）→ 全绿；`uv run jsrpc-server` 默认端口启动 → HTTP+WS 双监听日志、失败路径 curl 返回与迁移前同形；host 两项覆盖由配置模块零改动结构性保证；6 条错误字符串按枚举逐字对照（其中 3 条无测试覆盖，以对照为证据）
- [x] **切片 2：关机语义回归测试固化**
  - 触点：测试目录新增关机场景（服务器停止 + 空闲 keep-alive 连接 + 限时断言）
  - 验证：`uv run pytest` → 新测试通过（停止 ≤12s、WS 端口释放），既有测试不回归
- [x] **切片 3：文档与项目上下文同步**
  - 触点：README 技术栈与说明；AGENTS.md 技术栈、禁止事项与陷阱中 sanic 专属条目、编码规范日志条目补 uvicorn stdlib 日志例外、导航章指向本 spec
  - 验证：文档描述与仓库实况逐条核对（uv.lock 无 sanic、入口命令、超时配置存在）；`uv run pytest` 最终全绿

## Rulings

- 2026-09-22/切片1：入口显式 `http="h11"`（而非 uvicorn 默认 `auto`）。依据：迁移中发现 venv 残留的 httptools 0.8.0（sanic 时代遗留、不在 lock）被 auto 自动加载后在 Python 3.14 下静默不解析请求——TCP 收请求但永不应答，4 项 e2e 全 ReadTimeout；同条件显式 h11 即时应答。uv sync --exact 清残留 + 入口锁 h11 双保险。代价：放弃 httptools 解析性能（demo 项目无感），h11 是 uvicorn 硬依赖恒可用。
- 2026-09-22/切片1：为解除 venv 文件锁，终止了工作区遗留的旧版 `uv run jsrpc-server` 进程树与两个 harness 孤儿探针（诊断阶段自产）。依据：迁移必需；服务重启即恢复。代价：无（服务即本次迁移要替换之物）。
- 2026-09-22/复审：响应改用 `CompatJSONResponse`（`ensure_ascii=True`）。依据：sanic 走 stdlib json 默认转义，starlette 默认输出原始 UTF-8——同一 JSON 值的字节表示不同，本项目返回值常含中文，按协议字节契约对齐；中文回包实测 wire 为 `\uXXXX` 转义。代价：若未来需要原始 UTF-8 字节需显式改回。
- 2026-09-22/复审：关闭 FastAPI 默认文档面（docs/redoc/openapi 置 None）。依据：对外契约只有 /send GET，不引入迁移前不存在的可浏览表面；实测 /docs、/openapi.json 均 404。代价：失去 /docs 便利（demo 项目不需要）。
- 2026-09-22/复审：关机回归测试增加线程异常捕获。依据：uvicorn 停止链若抛异常导致线程早退，原断言组合（not alive + elapsed 小 + 端口关闭）会全部成立而放行——补 thread_errors 断言封堵该盲区。

残余面（复审确认为框架默认、非违约，留作后续事项）：starlette 对 GET 路由自动接受 HEAD（会执行处理函数）；非 /send 路径 404 体为 starlette `{"detail": ...}` 形态。
