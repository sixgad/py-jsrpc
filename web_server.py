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


@app.route('/send', methods=['GET'])
async def get_request(request):
    # http://127.0.0.1:5000/send?group=ws-group&action=clientTime
    args_dic = {}
    for params in request.query_args:
        args_dic[params[0]] = str(params[1])
    if "action" not in args_dic:
        return response.json({"error": "need action"})
    group = args_dic.pop('group')
    async with websockets.connect(f'ws://localhost:6789/invoke?group={group}') as websocket:
        await websocket.send(json.dumps(args_dic))
        res = await websocket.recv()
        logger.info(res)
    return response.json(json.loads(res))


if __name__ == '__main__':
    app.add_task(ws_run())
    app.run(debug=False, host="127.0.0.1", port=5000)
