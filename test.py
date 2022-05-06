# -*- coding: utf-8 -*-
# @Time   : 2021/12/19 21:41
# @Author : zp
# @Python3.7

import requests
url = "http://127.0.0.1:5000/send?group=ws-group&action=clientTime"
import time
st_time = time.time()
print(requests.get(url).json())
print("共花费", time.time()-st_time)