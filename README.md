# py-jsrpc
python实现一套轻量、协程异步、websocket远程调用服务，js逆向、混淆加密一把梭，再也不用扣js了。

- [x] HTTP 与 WS 两个服务单进程一起启动
- [x] 项目管理迁移到 [uv](https://docs.astral.sh/uv/)，重构为 src 包结构

## 安装依赖

> uv sync

## 启动服务

> uv run jsrpc-server

单进程同时启动 HTTP 与 WebSocket 两个服务，默认地址：

- HTTP: `http://127.0.0.1:5000`
- WS:   `ws://127.0.0.1:6789`

可用环境变量覆盖（重启生效）：

| 变量 | 默认值 |
| --- | --- |
| `JSRPC_HTTP_HOST` | `127.0.0.1` |
| `JSRPC_HTTP_PORT` | `5000` |
| `JSRPC_WS_HOST` | `127.0.0.1` |
| `JSRPC_WS_PORT` | `6789` |

## 使用步骤

1. `uv run jsrpc-server` 启动服务
2. 浏览器注入 js 客户端脚本（包内 [src/jsrpc/static/client.js](src/jsrpc/static/client.js)），注册组与动作
3. 调用接口，获取js执行结果(eg. http://127.0.0.1:5000/send?group=ws-group&action=clientTime)

## 运行测试

> uv run pytest

## 实战

blog地址，https://paker.net.cn/blog/33-%E5%AE%9E%E6%88%98%EF%BC%9Apython%E5%BC%80%E5%8F%91jsrpc%E6%9C%8D%E5%8A%A1%E4%B8%8E%E6%BC%94%E7%A4%BA/article.html

更成熟的方案，大家可以去看看virjar大佬的 [sekiro](https://github.com/virjar/sekiro)
