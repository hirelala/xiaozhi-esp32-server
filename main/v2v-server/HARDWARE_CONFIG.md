# Hardware Configuration Guide

This guide explains how to configure ESP32 hardware to connect to the V2V LiveKit proxy server.

## Default Configuration

The hardware firmware is pre-configured with a default proxy server URL:
- Default URL: `ws://192.168.1.103:8765/v2v`

Update this to match your proxy server's actual IP address.

## Configuration Methods

### Method 1: Update Default URL in Firmware

Edit the default URL in the firmware source code:

File: `main/xiaozhi-hardware/main/protocols/websocket_protocol.cc`

```cpp
std::string url = settings.GetString("url", "ws://YOUR_SERVER_IP:8765/v2v");
```

Replace `YOUR_SERVER_IP` with your proxy server's IP address, then rebuild and flash the firmware.

### Method 2: Configure via OTA Server

If you have an OTA server set up, configure the websocket settings remotely:

```json
{
  "websocket": {
    "url": "ws://your-proxy-server:8765/v2v"
  }
}
```

### Method 3: Direct NVS Configuration

For advanced users, write directly to ESP32's NVS storage:

Namespace: `websocket`
Key: `url` (string) - WebSocket server URL

## LiveKit Configuration

LiveKit credentials are configured on the proxy server, not on the hardware.

Set these environment variables on the server:
1. **LIVEKIT_URL**: Your LiveKit server URL (e.g., `wss://your-app.livekit.cloud`)
2. **LIVEKIT_API_KEY**: Your LiveKit API key
3. **LIVEKIT_API_SECRET**: Your LiveKit API secret

Get credentials from your LiveKit Cloud dashboard or self-hosted LiveKit server.

## Verification

After configuration, check hardware logs:

```
Connecting to websocket server: ws://your-server:8765/v2v with version: X
```

If successful:
```
Websocket connected
```

## Troubleshooting

### Connection Failed

- Verify the proxy server is running and accessible
- Check firewall rules allow port 8765
- Ensure IP address is correct
- Check network connectivity

### Server Not Configured

If you see "Server not configured" error:
- Verify LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET are set on the server
- Check server logs for credential errors

### No Agent Response

If connected but no voice response:
- Ensure the LiveKit agent (v2v-voiceagent) is running and connected to LiveKit
- Check agent logs for errors
- Verify the agent is configured to join rooms matching the pattern `v2v-*`
