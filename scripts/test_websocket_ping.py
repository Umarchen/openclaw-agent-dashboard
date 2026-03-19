#!/usr/bin/env python3
"""测试 WebSocket JSON 心跳"""
import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    print("请安装: pip install websockets")
    sys.exit(1)


async def test():
    uri = "ws://localhost:38272/ws"
    print("连接 WebSocket...")
    async with websockets.connect(uri, close_timeout=2) as ws:
        # 1. 可能收到 full_state（若后端正常），或直接进入 ping 测试
        # 先发送 JSON ping 测试心跳逻辑
        print("1. 发送 JSON ping...")
        await ws.send(json.dumps({"type": "ping", "timestamp": 1234567}))
        msg = await asyncio.wait_for(ws.recv(), timeout=3)
        data = json.loads(msg)
        if data.get("type") != "pong":
            print(f"FAIL: 期望 pong, 收到 {data.get('type')}")
            return False
        print("2. JSON ping -> pong: OK")

        # 3. 发送纯文本 ping
        await ws.send("ping")
        msg = await asyncio.wait_for(ws.recv(), timeout=3)
        data = json.loads(msg)
        if data.get("type") != "pong":
            print(f"FAIL: 期望 pong, 收到 {data.get('type')}")
            return False
        print("3. 文本 ping -> pong: OK")

    print("所有 WebSocket 测试通过!")
    return True


if __name__ == "__main__":
    ok = asyncio.run(test())
    sys.exit(0 if ok else 1)
