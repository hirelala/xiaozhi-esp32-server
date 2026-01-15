import json
import logging
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
import sys

from providers import LiveKitProxy

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

app = FastAPI(title="V2V LiveKit Proxy Server")

load_dotenv()
LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")


@app.on_event("startup")
async def startup_event():
    print("\n" + "="*60)
    print("V2V LiveKit Proxy Server Started")
    print("="*60)
    print(f"Listening on: ws://0.0.0.0:8765/v2v")
    print(f"LiveKit URL: {LIVEKIT_URL or 'NOT SET'}")
    print("="*60 + "\n")


@app.websocket("/v2v")
async def websocket_endpoint(websocket: WebSocket):
    client_host = websocket.client.host if websocket.client else "unknown"
    print(f"\n>>> WebSocket connection attempt from: {client_host}")
    
    await websocket.accept()
    
    device_id = websocket.headers.get("device-id", "unknown")
    protocol_version = websocket.headers.get("protocol-version", "unknown")
    
    print(f">>> Hardware CONNECTED!")
    print(f"    Device ID: {device_id}")
    print(f"    Client IP: {client_host}")
    print(f"    Protocol Version: {protocol_version}")
    logger.info(f"Hardware connected: {device_id} from {client_host}")
    
    if not LIVEKIT_URL or not LIVEKIT_API_KEY or not LIVEKIT_API_SECRET:
        logger.error("LiveKit credentials not configured")
        await websocket.close(code=1008, reason="Server not configured")
        return
    
    room_name = f"v2v-{device_id}"
    proxy = LiveKitProxy(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, room_name)
    proxy.hardware_ws = websocket
    
    try:
        await proxy.connect_to_livekit()
        
        await websocket.send_json({
            "type": "hello",
            "session_id": proxy.room_name,
            "transport": "websocket",
            "audio_params": {
                "sample_rate": 16000,
                "format": "opus",
                "frame_duration": 60
            }
        })
        
        while True:
            data = await websocket.receive()
            
            if "text" in data:
                message = json.loads(data["text"])
                msg_type = message.get("type")
                
                if msg_type == "hello":
                    logger.info("Received hello from hardware")
                elif msg_type == "listen":
                    logger.info(f"Hardware listening state: {message.get('state')}")
                elif msg_type == "abort":
                    logger.info("Hardware aborted playback")
                    await proxy.send_tts_stop()
                
            elif "bytes" in data:
                opus_data = data["bytes"]
                await proxy.send_audio_to_livekit(opus_data)
                
    except WebSocketDisconnect:
        print(f"<<< Hardware DISCONNECTED: {device_id}")
        logger.info("Hardware disconnected")
    except Exception as e:
        print(f"!!! ERROR for {device_id}: {e}")
        logger.error(f"Error in WebSocket handler: {e}")
    finally:
        await proxy.disconnect()
        print(f"<<< Connection closed: {device_id}\n")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "v2v-livekit-proxy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)
