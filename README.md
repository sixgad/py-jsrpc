# py-jsrpc
python实现一套轻量、协程异步、websocket远程调用服务，js逆向、混淆加密一把梭，再也不用扣js了。

- [x] 将back_socket_server合并到web_server一起启动

安装依赖：

> pip install -r requirements.txt

启动步骤：

1. python web_server.py
2. 浏览器注入client.js
2. 调用接口，获取js执行结果

实战：blog地址，https://paker.net.cn/article?id=33



更成熟的方案，大家可以去看看virjar大佬的 [sekiro](https://github.com/virjar/sekiro)

