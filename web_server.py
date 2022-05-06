# -*- coding: utf-8 -*-
# @Time   : 2021/7/13 21:18
# @Author : zp
# @Python3.7
import asyncio
import websockets
import json
from loguru import logger
from sanic import Sanic, response
import threading
from back_socket_server import ws_run

app = Sanic(__name__)

@app.route('/send',methods=['GET'])
async def get_request(request):
    #http://127.0.0.1:5000/send?group=ws-group&action=clientTime
    args_dic = {}
    for params in request.query_args:
        args_dic[params[0]] = str(params[1])
    if "action" not in args_dic:
        return response.json({"error":"need action"})
    group = args_dic.pop('group')
    async with websockets.connect(f'ws://localhost:6789/invoke?group={group}') as websocket:
        await websocket.send(json.dumps(args_dic))
        res = await websocket.recv()
        logger.info(res)
    return response.json(json.loads(res))

# 定义一个专门创建事件循环loop的函数，在另一个线程中启动它
def start_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

if __name__ == '__main__':
    new_loop = asyncio.new_event_loop()  # 在当前线程下创建事件循环，（未启用），在start_loop里面启动它
    t = threading.Thread(target=start_loop, args=(new_loop,))  # 通过当前线程开启新的线程去启动事件循环
    t.start()
    asyncio.run_coroutine_threadsafe(ws_run(), new_loop)
    app.run(debug=False, host="127.0.0.1", port=5000)