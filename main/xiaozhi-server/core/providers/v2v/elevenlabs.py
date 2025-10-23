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
            
            # Log the URL (with masked API key for security)
            masked_url = ws_url.replace(self.api_key, "***API_KEY***") if self.api_key else ws_url
            self.logger.bind(tag=TAG).info(f"Connecting to ElevenLabs Agents for device: {device_id}")
            self.logger.bind(tag=TAG).info(f"WebSocket URL: {masked_url}")
            
            # Connect to ElevenLabs WebSocket
            conn.elevenlabs_ws = await websockets.connect(ws_url)
            self.logger.bind(tag=TAG).info(f"✅ WebSocket connected successfully")
            
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
            
            self.logger.bind(tag=TAG).info(f"Sending init message: {json.dumps(init_message, indent=2)}")
            
            await conn.elevenlabs_ws.send(json.dumps(init_message))
            self.logger.bind(tag=TAG).info("Sent configuration to ElevenLabs")
            
            # Start receiving audio from ElevenLabs
            conn.elevenlabs_receive_task = asyncio.create_task(
                self._receive_audio_loop(conn)
            )
            
            conn.v2v_active = True
            self.logger.bind(tag=TAG).info("ElevenLabs Agents conversation started")
            self.logger.bind(tag=TAG).info(f"✅ Set conn.v2v_active = {conn.v2v_active}")
            self.logger.bind(tag=TAG).info("🎧 Waiting for audio from hardware and ElevenLabs...")

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
            self.logger.bind(tag=TAG).info("📡 Started ElevenLabs receive loop")
            async for message in conn.elevenlabs_ws:
                if not conn.v2v_active:
                    self.logger.bind(tag=TAG).info("V2V no longer active, stopping receive loop")
                    break
                
                if isinstance(message, str):
                    # Handle JSON messages (ping, events, metadata, audio, etc.)
                    await self._handle_json_message(conn, message)
                elif isinstance(message, bytes):
                    # ElevenLabs Agents uses JSON for everything, binary messages shouldn't happen
                    self.logger.bind(tag=TAG).warning(f"⚠️ Received unexpected binary message ({len(message)} bytes)")
                    # Try to decode as text/JSON
                    try:
                        text_message = message.decode('utf-8')
                        await self._handle_json_message(conn, text_message)
                    except:
                        self.logger.bind(tag=TAG).error("Failed to decode binary message as JSON")
                    
        except websockets.exceptions.ConnectionClosed:
            self.logger.bind(tag=TAG).info("ElevenLabs WebSocket connection closed")
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
                # Session started
                conn.elevenlabs_session_id = data.get("conversation_initiation_metadata_event", {}).get("conversation_id")
                self.logger.bind(tag=TAG).info(
                    f"ElevenLabs session started: {conn.elevenlabs_session_id}"
                )
                
            elif msg_type == "user_transcript":
                # User speech transcription - user finished speaking
                transcript = data.get("user_transcription_event", {}).get("user_transcript", "")
                self.logger.bind(tag=TAG).info(f"👤 User said: {transcript}")
                
                # User finished speaking - prepare for agent response
                conn.client_abort = False
                conn.client_is_speaking = False
                
                # Reset audio state to allow new agent response
                if hasattr(conn, 'elevenlabs_audio_started'):
                    conn.elevenlabs_audio_started = False
                                    
            elif msg_type == "agent_response" or msg_type == "agent_response_transcript":
                # Agent response - agent finished speaking
                transcript = data.get("agent_response_event", {}).get("agent_response", "")
                self.logger.bind(tag=TAG).info(f"🤖 Agent said: {transcript}")
                
                # ALWAYS reset state for next turn - ready to listen to user again
                if hasattr(conn, 'elevenlabs_audio_started'):
                    conn.elevenlabs_audio_started = False
                conn.client_is_speaking = False
                conn.client_abort = False
                
                # Send TTS stop message to hardware
                await send_tts_message(conn, "stop", None)
                                
            elif msg_type == "interruption":
                # ElevenLabs confirmed interruption - cleanup state
                self.logger.bind(tag=TAG).info("⚠️ ElevenLabs confirmed interruption")
                
                # Agent audio should already be stopped by listen handler
                # Just ensure state is clean
                if hasattr(conn, 'elevenlabs_audio_started'):
                    conn.elevenlabs_audio_started = False
                    
                if hasattr(conn, 'elevenlabs_audio_buffer'):
                    conn.elevenlabs_audio_buffer.clear()
                    
                conn.client_is_speaking = False
                
                self.logger.bind(tag=TAG).info("✅ Interruption confirmed - ready for user input")
                
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
                self.logger.bind(tag=TAG).debug(f"Sent pong with event_id={event_id}")
                
            else:
                self.logger.bind(tag=TAG).debug(f"Received message type: {msg_type}")
                
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
                # Create Opus encoder for hardware: 16kHz, mono, VoIP application
                conn.elevenlabs_opus_encoder = opuslib_next.Encoder(
                    16000, 1, opuslib_next.APPLICATION_VOIP
                )
            
            # Encode PCM to Opus (960 samples = 60ms at 16kHz, matching hardware)
            # ElevenLabs typically sends audio in chunks, may need buffering
            if not hasattr(conn, 'elevenlabs_audio_buffer'):
                conn.elevenlabs_audio_buffer = bytearray()
            
            # Send TTS start message on first audio chunk
            if not hasattr(conn, 'elevenlabs_audio_started') or not conn.elevenlabs_audio_started:
                conn.elevenlabs_audio_started = True
                
                # Reset user input counter so next user audio triggers activity detection
                if hasattr(conn, 'elevenlabs_input_count'):
                    delattr(conn, 'elevenlabs_input_count')
                
                # Clear abort flag to allow audio playback
                conn.client_abort = False
                
                # Reset flow control for clean audio streaming
                if hasattr(conn, 'audio_flow_control'):
                    delattr(conn, 'audio_flow_control')
                
                # Mark that system is speaking
                conn.client_is_speaking = True
                
                await send_tts_message(conn, "start", None)
                self.logger.bind(tag=TAG).info("📢 TTS start sent to hardware - agent speaking now")
            
            conn.elevenlabs_audio_buffer.extend(audio_data)
            
            # Process complete frames (960 samples * 2 bytes per sample = 1920 bytes)
            frame_size = 1920
            frames_sent = 0
            while len(conn.elevenlabs_audio_buffer) >= frame_size:
                # Double-check abort flag before each frame (user might interrupt)
                if conn.client_abort:
                    self.logger.bind(tag=TAG).info("⏹️ Audio playback aborted by user")
                    conn.elevenlabs_audio_buffer.clear()
                    break
                
                pcm_frame = bytes(conn.elevenlabs_audio_buffer[:frame_size])
                conn.elevenlabs_audio_buffer = conn.elevenlabs_audio_buffer[frame_size:]
                
                # Encode to Opus (60ms frame)
                opus_data = conn.elevenlabs_opus_encoder.encode(pcm_frame, 960)
                
                # Send to hardware using proper sendAudio function (with flow control)
                await sendAudio(conn, opus_data, frame_duration=60)
                frames_sent += 1
                    
            if frames_sent > 0:
                self.logger.bind(tag=TAG).debug(f"🔈 Sent {frames_sent} Opus frames to hardware")
                    
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
            # Send user_activity signal to trigger turn-taking
            user_activity_msg = {
                "type": "user_activity"
            }
            await conn.elevenlabs_ws.send(json.dumps(user_activity_msg))
            self.logger.bind(tag=TAG).info("🗣️ Sent user_activity signal to ElevenLabs (user wants to speak)")
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
            # Only log every 10th chunk to avoid spam (but always log first chunk)
            if not hasattr(conn, 'elevenlabs_input_count'):
                conn.elevenlabs_input_count = 0
                self.logger.bind(tag=TAG).info(f"🎤 👤 USER AUDIO INPUT STARTED - sending to ElevenLabs")
                
                # Automatically notify ElevenLabs of user activity on first audio chunk
                # This triggers turn-taking without requiring hardware to send explicit "listen" message
                if conn.client_is_speaking:
                    self.logger.bind(tag=TAG).info("🚨 User speaking while agent is speaking - triggering interruption")
                    conn.client_abort = True
                    if hasattr(conn, 'elevenlabs_audio_buffer'):
                        conn.elevenlabs_audio_buffer.clear()
                    if hasattr(conn, 'elevenlabs_audio_started'):
                        conn.elevenlabs_audio_started = False
                    await self.notify_user_speaking(conn)
                    conn.client_abort = False
                else:
                    self.logger.bind(tag=TAG).info("🎤 User started speaking (agent idle)")
                    await self.notify_user_speaking(conn)
            
            conn.elevenlabs_input_count += 1
            if conn.elevenlabs_input_count % 10 == 0:
                self.logger.bind(tag=TAG).debug(f"🎤 User audio: {conn.elevenlabs_input_count} chunks sent")
            
            # Decode Opus to PCM for ElevenLabs
            if not hasattr(conn, 'elevenlabs_opus_decoder'):
                import opuslib_next
                self.logger.bind(tag=TAG).info("Creating Opus decoder for 16kHz mono audio")
                conn.elevenlabs_opus_decoder = opuslib_next.Decoder(16000, 1)
            
            try:
                # Decode Opus to PCM (Hardware sends 60ms frames at 16kHz = 960 samples)
                pcm_data = conn.elevenlabs_opus_decoder.decode(audio_data, frame_size=960)
                
                # Send PCM audio to ElevenLabs
                if conn.elevenlabs_ws:
                    import base64
                    audio_b64 = base64.b64encode(pcm_data).decode('utf-8')
                    
                    # Send as JSON (ElevenLabs SDK format)
                    audio_message = {
                        "user_audio_chunk": audio_b64
                    }
                    
                    await conn.elevenlabs_ws.send(json.dumps(audio_message))
                else:
                    self.logger.bind(tag=TAG).error("ElevenLabs WebSocket is None!")
                
            except Exception as decode_error:
                self.logger.bind(tag=TAG).error(f"❌ Audio decode error: {decode_error}")
                import traceback
                self.logger.bind(tag=TAG).error(f"Traceback: {traceback.format_exc()}")
            
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
            
            # Close WebSocket connection
            if conn.elevenlabs_ws:
                await conn.elevenlabs_ws.close()
                conn.elevenlabs_ws = None

            self.logger.bind(tag=TAG).info("ElevenLabs conversation stopped")

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
        
        # Clean up connection attributes
        attrs_to_clean = [
            'elevenlabs_ws', 'elevenlabs_session_id', 'elevenlabs_receive_task',
            'elevenlabs_opus_decoder', 'elevenlabs_opus_encoder', 
            'elevenlabs_audio_buffer'
        ]
        
        for attr in attrs_to_clean:
            if hasattr(conn, attr):
                delattr(conn, attr)

        self.logger.bind(tag=TAG).info("ElevenLabs V2V cleanup completed")

