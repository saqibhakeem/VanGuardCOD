import asyncio
import json

import httpx
import websockets

BASE = "http://127.0.0.1:8100"
HEADERS = {"X-Tenant-API-Key": "vcod_live_demo_key_2026"}


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE, headers=HEADERS) as client:
        orders = (await client.get("/api/v1/orders")).json()
        order_id = orders[0]["id"]
        call = (
            await client.post(f"/api/v1/calls/trigger-outbound/{order_id}")
        ).json()
        ws_url = call["ws_url"]

    print("connecting", ws_url)
    async with websockets.connect(ws_url) as ws:
        print(json.loads(await ws.recv()))
        await ws.send(
            json.dumps(
                {"event": "text_utterance", "text": "Yes, confirm the order"}
            )
        )
        for _ in range(30):
            try:
                frame = json.loads(await asyncio.wait_for(ws.recv(), 5))
            except asyncio.TimeoutError:
                break
            print(frame["event"])
            if frame["event"] == "telemetry":
                break
        await ws.send(json.dumps({"event": "hangup"}))
        await ws.recv()


asyncio.run(main())