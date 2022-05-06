# -*- coding: UTF-8 -*-
# @Time : 2021/7/13 17:40
# @Author : zp

import random
import asyncio
import json
import websockets
import re
import uuid
from loguru import logger

# 实现一对多连接
USERS = {}
APIUSERS = {}
async def register(websocket, path):
    #web clientjs 连接注册
    if path and path.startswith('/register'):
        group = re.findall('\?group=(.*?)&',path)[0]
        clientId = re.findall('&clientId=(.*)',path)[0]
        if group not in USERS:
            USERS[group] = {}
        USERS[group][clientId] = websocket
        logger.info("USERS register success")
        logger.info(USERS)
        return "webclient",group,clientId
    if path and path.startswith('/invoke'):
        group = re.findall('\?group=(.*)',path)[0]
        clientId = str(uuid.uuid4())
        if group not in APIUSERS:
            APIUSERS[group] = {}
        APIUSERS[group][clientId] = websocket
        logger.info("APIUSERS register success")
        logger.info(USERS)
        return "apiclient",group,clientId
    return None, None, None

async def unregister(role, group, clientId):
    if role == 'webclient':
        USERS[group].pop(clientId)
        logger.info("USERS unregister over")
        logger.info(USERS)
    if role == 'apiclient':
        APIUSERS[group].pop(clientId)
        logger.info("APIUSERS unregister over")
        logger.info(APIUSERS)


async def counter(websocket, path):
    logger.info(path)
    role, group, clientId = await register(websocket, path)
    try:
        # 这样写会一直保持长连接
        async for orimessage in websocket:
            logger.info(orimessage)
            message = json.loads(orimessage)
            # 接收到api接口服务send来的消息时,action为必带的参数
            if "action" in message and role == 'apiclient':
                # 由于可能是分布式的,此处直接随机返回一个client执行rpc方法就行了
                message['__uuid_seq__'] = clientId
                await USERS[group][random.choice(list(USERS[group]))].send(json.dumps(message))

            #接收到web js client发来的消息时,需要由server将message send到api接口client
            if "status" in message and role == 'webclient':
                apiclient = message['__uuid_seq__']
                message.pop("__uuid_seq__", None)
                await APIUSERS[group][apiclient].send(json.dumps(message))

    finally:
        await unregister(role, group, clientId)
async def ws_run():
    asyncio.get_event_loop().run_until_complete(websockets.serve(counter, 'localhost', 6789))
    # asyncio.get_event_loop().run_forever()