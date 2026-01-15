# V2V LiveKit Proxy Server

A lightweight proxy server that bridges ESP32 hardware with LiveKit voice agents.

## Architecture

```
ESP32 Hardware <-> V2V Proxy Server <-> LiveKit Room <-> LiveKit Agent
     (Opus)            (PCM)              (WebRTC)        (STT/LLM/TTS)
```

The proxy server handles:
1. WebSocket connection from ESP32 hardware
2. Opus ↔ PCM audio transcoding
3. LiveKit room management
4. Audio streaming to/from LiveKit agent

## Installation

```bash
pip install -r requirements.txt
```

## Configuration

Set environment variables:

```bash
export LIVEKIT_URL="wss://your-livekit-server.livekit.cloud"
export LIVEKIT_API_KEY="your_api_key"
export LIVEKIT_API_SECRET="your_api_secret"
```

Or create a `.env` file:

```bash
cp env.template .env
# Edit .env with your credentials
```

## Running

Start the proxy server:

```bash
cd src
python main.py
```

The server listens on `ws://0.0.0.0:8765/v2v`

## LiveKit Agent

This proxy works with a LiveKit voice agent deployed separately (see `v2v-voiceagent`). The agent handles:
- Speech-to-Text (STT)
- Large Language Model (LLM) processing
- Text-to-Speech (TTS)
- Voice Activity Detection (VAD)

When hardware connects, the proxy creates a LiveKit room and the agent automatically joins to handle conversations.

## Protocol

### Hardware -> Server

Hello message (JSON):
```json
{
  "type": "hello",
  "version": 1,
  "audio_params": {
    "format": "opus",
    "sample_rate": 16000,
    "channels": 1,
    "frame_duration": 60
  }
}
```

Audio packets: Raw Opus bytes via WebSocket binary frames

### Server -> Hardware

Hello response:
```json
{
  "type": "hello",
  "session_id": "v2v-device-id",
  "transport": "websocket",
  "audio_params": {
    "sample_rate": 16000,
    "format": "opus",
    "frame_duration": 60
  }
}
```

Audio packets (JSON):
```json
{
  "type": "audio",
  "data": "base64_encoded_opus_data",
  "duration": 60
}
```

TTS control:
```json
{
  "type": "tts",
  "state": "stop"
}
```

## Docker Deployment

```bash
docker build -t v2v-proxy .
docker run -p 8765:8765 \
  -e LIVEKIT_URL="wss://your-server.livekit.cloud" \
  -e LIVEKIT_API_KEY="your_api_key" \
  -e LIVEKIT_API_SECRET="your_api_secret" \
  v2v-proxy
```

## Health Check

```bash
curl http://localhost:8765/health
```
