"""
ElevenLabs Voice2Voice Provider
Implements real-time voice-to-voice conversation using ElevenLabs Agents Platform
Documentation: https://elevenlabs.io/docs/agents-platform/overview
"""

import asyncio
import json
import websockets
from typing import Dict, Any, Optional
from .base import V2VProviderBase
from core.handle.sendAudioHandle import sendAudio, send_tts_message

TAG = __name__


class V2VProvider(V2VProviderBase):
    """ElevenLabs Agents Platform Voice2Voice提供者"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.agent_id = config.get("agent_id", "")
        
        # Optional configurations
        self.signed_url = config.get("signed_url", None)  # For authenticated agents
        self.audio_format = config.get("audio_format", "pcm_16000")  # PCM 16kHz default
        
        # Validate configuration
        if not self.api_key or not self.agent_id:
            self.logger.bind(tag=TAG).warning(
                "ElevenLabs V2V configuration incomplete. Please set api_key and agent_id"
            )

    async def initialize(self, conn) -> bool:
        """
        初始化ElevenLabs Agents连接

        Args:
            conn: 连接对象

        Returns:
            bool: 初始化是否成功
        """
        try:
            # Initialize connection attributes
            conn.elevenlabs_ws = None
            conn.elevenlabs_session_id = None
            conn.v2v_active = False
            conn.elevenlabs_receive_task = None

            self.logger.bind(tag=TAG).info("ElevenLabs Agents V2V initialized successfully")
            return True

        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Failed to initialize ElevenLabs Agents V2V: {e}")
            return False

    async def start_conversation(self, conn) -> None:
        """
        开始ElevenLabs Agents对话会话

        Args:
            conn: 连接对象
        """
        try:
            device_id = conn.headers.get("device-id", "unknown")
            
            # Build WebSocket URL
            if self.signed_url:
                # Use pre-signed URL for authenticated agents
                ws_url = self.signed_url
            else:
                # Use public agent URL
                ws_url = f"wss://api.elevenlabs.io/v1/convai/conversation?agent_id={self.agent_id}"
            
            # Add API key as query parameter if not using signed URL
            if not self.signed_url:
                ws_url += f"&api_key={self.api_key}"
            
            # Connect to ElevenLabs WebSocket
            conn.elevenlabs_ws = await websockets.connect(ws_url)
            self.logger.bind(tag=TAG).info(f"✅ ElevenLabs WebSocket connected for device: {device_id}")
            
            # Send initial configuration
            # DON'T override prompt - agent config doesn't allow it
            # Just specify audio format
            init_message = {
                "type": "conversation_initiation_client_data",
                "conversation_config_override": {
                    "audio": {
                        "input": {
                            "encoding": "pcm_16000",
                            "sample_rate": 16000
                        },
                        "output": {
                            "encoding": "pcm_16000",
                            "sample_rate": 16000
                        }
                    }
                }
            }
            
            await conn.elevenlabs_ws.send(json.dumps(init_message))
            
            # Start receiving audio from ElevenLabs
            conn.elevenlabs_receive_task = asyncio.create_task(
                self._receive_audio_loop(conn)
            )
            
            conn.v2v_active = True
            self.logger.bind(tag=TAG).info("✅ ElevenLabs conversation started")

        except Exception as e:
            self.logger.bind(tag=TAG).error(
                f"Failed to start ElevenLabs conversation: {e}"
            )
            conn.v2v_active = False

    async def _receive_audio_loop(self, conn):
        """
        接收来自ElevenLabs的音频和消息

        Args:
            conn: 连接对象
        """
        try:
            async for message in conn.elevenlabs_ws:
                if not conn.v2v_active:
                    break
                
                if isinstance(message, str):
                    await self._handle_json_message(conn, message)
                elif isinstance(message, bytes):
                    try:
                        text_message = message.decode('utf-8')
                        await self._handle_json_message(conn, text_message)
                    except:
                        self.logger.bind(tag=TAG).error("Failed to decode binary message")
                    
        except websockets.exceptions.ConnectionClosed:
            conn.v2v_active = False
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Error in ElevenLabs receive loop: {e}")
            conn.v2v_active = False

    async def _handle_json_message(self, conn, message: str):
        """
        处理来自ElevenLabs的JSON消息

        Args:
            conn: 连接对象
            message: JSON消息字符串
        """
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "conversation_initiation_metadata":
                conn.elevenlabs_session_id = data.get("conversation_initiation_metadata_event", {}).get("conversation_id")
                
            elif msg_type == "user_transcript":
                transcript = data.get("user_transcription_event", {}).get("user_transcript", "")
                self.logger.bind(tag=TAG).info(f"👤 User: {transcript}")
                
                conn.client_abort = False
                conn.client_is_speaking = False
                
                if hasattr(conn, 'elevenlabs_audio_started'):
                    conn.elevenlabs_audio_started = False
                                    
            elif msg_type == "agent_response" or msg_type == "agent_response_transcript":
                transcript = data.get("agent_response_event", {}).get("agent_response", "").strip()
                self.logger.bind(tag=TAG).info(f"🤖 Agent: {transcript}")
                
                if hasattr(conn, 'elevenlabs_audio_started'):
                    conn.elevenlabs_audio_started = False
                conn.client_is_speaking = False
                conn.client_abort = False
                
                await send_tts_message(conn, "stop", None)
                                
            elif msg_type == "interruption":
                if hasattr(conn, 'elevenlabs_audio_started'):
                    conn.elevenlabs_audio_started = False
                    
                if hasattr(conn, 'elevenlabs_audio_buffer'):
                    conn.elevenlabs_audio_buffer.clear()
                    
                conn.client_is_speaking = False
                
            elif msg_type == "audio":
                # Agent audio response (from SDK: audio_event.audio_base_64)
                audio_event = data.get("audio_event", {})
                audio_b64 = audio_event.get("audio_base_64", "")
                if audio_b64:
                    import base64
                    pcm_data = base64.b64decode(audio_b64)
                    await self._handle_audio_output(conn, pcm_data)
                    
            elif msg_type == "ping":
                # Send pong to keep connection alive (must include event_id from ping)
                ping_event = data.get("ping_event", {})
                event_id = ping_event.get("event_id")
                pong_message = {
                    "type": "pong",
                    "event_id": event_id
                }
                await conn.elevenlabs_ws.send(json.dumps(pong_message))
                
            else:
                pass
                
        except json.JSONDecodeError as e:
            self.logger.bind(tag=TAG).error(f"Failed to parse ElevenLabs message: {e}")
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Error handling ElevenLabs message: {e}")

    async def _handle_audio_output(self, conn, audio_data: bytes):
        """
        处理来自ElevenLabs的音频输出并发送到硬件

        Args:
            conn: 连接对象
            audio_data: PCM音频数据
        """
        try:
            # ElevenLabs sends PCM audio, need to encode to Opus for hardware
            if not hasattr(conn, 'elevenlabs_opus_encoder'):
                import opuslib_next
                conn.elevenlabs_opus_encoder = opuslib_next.Encoder(
                    16000, 1, opuslib_next.APPLICATION_VOIP
                )
            
            if not hasattr(conn, 'elevenlabs_audio_buffer'):
                conn.elevenlabs_audio_buffer = bytearray()
            
            if not hasattr(conn, 'elevenlabs_audio_started'):
                conn.elevenlabs_audio_started = False
            
            conn.elevenlabs_audio_buffer.extend(audio_data)
            
            frame_size = 1920
            pre_buffer_size = frame_size * 2
            
            if not conn.elevenlabs_audio_started:
                if len(conn.elevenlabs_audio_buffer) >= pre_buffer_size:
                    conn.elevenlabs_audio_started = True
                    
                    if hasattr(conn, 'elevenlabs_input_count'):
                        conn.elevenlabs_input_count = 0
                        conn.elevenlabs_user_activity_sent = False
                    
                    conn.client_abort = False
                    
                    if hasattr(conn, 'audio_flow_control'):
                        delattr(conn, 'audio_flow_control')
                    
                    conn.client_is_speaking = True
                    
                    await send_tts_message(conn, "start", None)
                else:
                    return
            
            while len(conn.elevenlabs_audio_buffer) >= frame_size:
                if conn.client_abort:
                    conn.elevenlabs_audio_buffer.clear()
                    break
                
                pcm_frame = bytes(conn.elevenlabs_audio_buffer[:frame_size])
                conn.elevenlabs_audio_buffer = conn.elevenlabs_audio_buffer[frame_size:]
                
                opus_data = conn.elevenlabs_opus_encoder.encode(pcm_frame, 960)
                await sendAudio(conn, opus_data, frame_duration=60)
                    
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Error handling audio output: {e}")

    async def notify_user_speaking(self, conn) -> None:
        """
        通知ElevenLabs用户开始说话（用于触发转弯）
        
        Args:
            conn: 连接对象
        """
        if not hasattr(conn, 'elevenlabs_ws') or not conn.elevenlabs_ws:
            return
            
        try:
            user_activity_msg = {
                "type": "user_activity"
            }
            await conn.elevenlabs_ws.send(json.dumps(user_activity_msg))
        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Failed to send user_activity: {e}")

    async def handle_audio_input(self, conn, audio_data: bytes) -> None:
        """
        处理输入音频并发送到ElevenLabs

        Args:
            conn: 连接对象
            audio_data: 音频数据（Opus格式）
        """
        # Check if V2V is active
        v2v_active = getattr(conn, 'v2v_active', False)
        has_ws = hasattr(conn, 'elevenlabs_ws') and conn.elevenlabs_ws is not None
        
        if not v2v_active or not has_ws:
            self.logger.bind(tag=TAG).warning(f"V2V not ready: v2v_active={v2v_active}, has_ws={has_ws}")
            self.logger.bind(tag=TAG).warning(f"Checking conn attributes: v2v_active exists={hasattr(conn, 'v2v_active')}, elevenlabs_ws exists={hasattr(conn, 'elevenlabs_ws')}")
            return

        try:
            if not hasattr(conn, 'elevenlabs_input_count'):
                conn.elevenlabs_input_count = 0
                conn.elevenlabs_user_activity_sent = False
            
            conn.elevenlabs_input_count += 1
            
            if not conn.elevenlabs_user_activity_sent and conn.elevenlabs_input_count >= 5:
                if conn.client_is_speaking:
                    self.logger.bind(tag=TAG).info("👤 User interrupting agent")
                    conn.client_abort = True
                    if hasattr(conn, 'elevenlabs_audio_buffer'):
                        conn.elevenlabs_audio_buffer.clear()
                    if hasattr(conn, 'elevenlabs_audio_started'):
                        conn.elevenlabs_audio_started = False
                
                await self.notify_user_speaking(conn)
                conn.elevenlabs_user_activity_sent = True
                
                if conn.client_is_speaking:
                    conn.client_abort = False
            
            if not hasattr(conn, 'elevenlabs_opus_decoder'):
                import opuslib_next
                conn.elevenlabs_opus_decoder = opuslib_next.Decoder(16000, 1)
            
            try:
                pcm_data = conn.elevenlabs_opus_decoder.decode(audio_data, frame_size=960)
                
                if conn.elevenlabs_ws:
                    import base64
                    audio_b64 = base64.b64encode(pcm_data).decode('utf-8')
                    
                    audio_message = {
                        "user_audio_chunk": audio_b64
                    }
                    
                    await conn.elevenlabs_ws.send(json.dumps(audio_message))
                
            except Exception as decode_error:
                self.logger.bind(tag=TAG).error(f"Audio decode error: {decode_error}")
            
        except Exception as e:
            self.logger.bind(tag=TAG).error(
                f"Failed to handle audio input in ElevenLabs: {e}"
            )

    async def stop_conversation(self, conn) -> None:
        """
        停止ElevenLabs对话

        Args:
            conn: 连接对象
        """
        try:
            conn.v2v_active = False
            
            # Stop receive task
            if hasattr(conn, 'elevenlabs_receive_task') and conn.elevenlabs_receive_task:
                conn.elevenlabs_receive_task.cancel()
                try:
                    await conn.elevenlabs_receive_task
                except asyncio.CancelledError:
                    pass
            
            if conn.elevenlabs_ws:
                await conn.elevenlabs_ws.close()
                conn.elevenlabs_ws = None

        except Exception as e:
            self.logger.bind(tag=TAG).error(
                f"Error stopping ElevenLabs conversation: {e}"
            )

    async def cleanup(self, conn) -> None:
        """
        清理ElevenLabs资源

        Args:
            conn: 连接对象
        """
        await self.stop_conversation(conn)
        
        attrs_to_clean = [
            'elevenlabs_ws', 'elevenlabs_session_id', 'elevenlabs_receive_task',
            'elevenlabs_opus_decoder', 'elevenlabs_opus_encoder', 
            'elevenlabs_audio_buffer'
        ]
        
        for attr in attrs_to_clean:
            if hasattr(conn, attr):
                delattr(conn, attr)

