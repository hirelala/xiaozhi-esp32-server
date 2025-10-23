"""
LiveKit Voice2Voice Provider
Implements real-time voice-to-voice conversation using LiveKit Agents framework
"""

import asyncio
from typing import Dict, Any, Optional
from .base import V2VProviderBase

TAG = __name__


class V2VProvider(V2VProviderBase):
    """LiveKit Voice2Voice提供者 - 使用LiveKit Agents框架"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key", "")
        self.api_secret = config.get("api_secret", "")
        self.url = config.get("url", "")
        
        # OpenAI settings for the agent (optional, can be configured separately)
        self.openai_api_key = config.get("openai_api_key", "")
        self.openai_model = config.get("openai_model", "gpt-4o-realtime-preview-2024-12-17")
        
        # Validate configuration
        if not self.api_key or not self.api_secret or not self.url:
            self.logger.bind(tag=TAG).warning(
                "LiveKit V2V configuration incomplete. Please set api_key, api_secret, and url"
            )

    async def initialize(self, conn) -> bool:
        """
        初始化LiveKit Agents连接

        Args:
            conn: 连接对象

        Returns:
            bool: 初始化是否成功
        """
        try:
            # Import LiveKit Agents SDK
            try:
                from livekit import agents, rtc
                from livekit.agents import JobContext, WorkerOptions, cli
                from livekit.agents.llm import ChatContext
                from livekit.plugins import openai, silero, noise_cancellation
                
                conn.livekit_agents = agents
                conn.livekit_rtc = rtc
                conn.livekit_openai = openai
                conn.livekit_silero = silero
                conn.livekit_noise_cancellation = noise_cancellation
                
            except ImportError as e:
                self.logger.bind(tag=TAG).error(
                    f"LiveKit Agents SDK not installed: {e}. "
                    "Please run: pip install 'livekit-agents[silero,turn-detector,openai]' "
                    "livekit-plugins-noise-cancellation"
                )
                return False

            # Initialize connection attributes
            conn.v2v_room = None
            conn.v2v_session = None
            conn.v2v_active = False
            conn.v2v_agent_task = None

            self.logger.bind(tag=TAG).info("LiveKit Agents V2V initialized successfully")
            return True

        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Failed to initialize LiveKit Agents V2V: {e}")
            return False

    async def start_conversation(self, conn) -> None:
        """
        开始LiveKit Agents对话会话

        Args:
            conn: 连接对象
        """
        try:
            if not hasattr(conn, 'livekit_agents'):
                self.logger.bind(tag=TAG).error("LiveKit Agents SDK not initialized")
                return

            from livekit import agents, rtc
            from livekit.agents import AutoSubscribe, JobContext
            from livekit.plugins import openai, silero
            
            device_id = conn.headers.get("device-id", "unknown")
            room_name = f"xiaozhi_{device_id}"
            
            # Create access token for the agent
            from livekit import api
            token = api.AccessToken(self.api_key, self.api_secret)
            token.with_identity(f"agent_{device_id}")
            token.with_name(f"XiaoZhi Agent {device_id}")
            token.with_grants(api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            ))
            jwt_token = token.to_jwt()

            # Connect to room
            conn.v2v_room = rtc.Room()
            
            # Setup room event handlers
            @conn.v2v_room.on("participant_connected")
            def on_participant_connected(participant: rtc.RemoteParticipant):
                self.logger.bind(tag=TAG).info(
                    f"Participant connected: {participant.identity}"
                )

            @conn.v2v_room.on("track_subscribed")
            def on_track_subscribed(
                track: rtc.Track,
                publication: rtc.RemoteTrackPublication,
                participant: rtc.RemoteParticipant,
            ):
                self.logger.bind(tag=TAG).info(
                    f"Track subscribed: {track.kind} from {participant.identity}"
                )

            # Connect to the room
            await conn.v2v_room.connect(self.url, jwt_token)
            self.logger.bind(tag=TAG).info(f"Connected to LiveKit room: {room_name}")

            # Start the voice agent session
            conn.v2v_agent_task = asyncio.create_task(
                self._run_voice_agent(conn, room_name)
            )
            
            conn.v2v_active = True
            self.logger.bind(tag=TAG).info("LiveKit Voice Agent session started")

        except Exception as e:
            self.logger.bind(tag=TAG).error(
                f"Failed to start LiveKit conversation: {e}"
            )
            conn.v2v_active = False

    async def _run_voice_agent(self, conn, room_name: str):
        """
        运行LiveKit Voice Agent

        Args:
            conn: 连接对象
            room_name: 房间名称
        """
        try:
            from livekit import agents
            from livekit.agents import AutoSubscribe, JobContext
            from livekit.agents.voice_assistant import VoiceAssistant
            from livekit.plugins import openai, silero
            
            # Get agent prompt from connection config
            # Handle both string and dict formats
            prompt_config = conn.config.get("prompt", "")
            if isinstance(prompt_config, dict):
                agent_prompt = prompt_config.get("system_prompt", "你是一个智能助手，可以帮助用户解答问题。")
            else:
                # prompt is stored as a string
                agent_prompt = prompt_config if prompt_config else "你是一个智能助手，可以帮助用户解答问题。"
            
            # Create assistant configuration
            assistant = VoiceAssistant(
                vad=silero.VAD.load(),  # Use Silero VAD for voice activity detection
                stt=openai.STT(),  # OpenAI Speech-to-Text
                llm=openai.LLM(model=self.openai_model),  # OpenAI LLM (GPT-4 Realtime)
                tts=openai.TTS(),  # OpenAI Text-to-Speech
                chat_ctx=agents.llm.ChatContext().append(
                    role="system",
                    text=agent_prompt,
                ),
            )

            # Start the assistant
            assistant.start(conn.v2v_room)
            
            self.logger.bind(tag=TAG).info("Voice Assistant started in room")

            # Handle incoming audio from the hardware
            # The assistant will automatically handle VAD, STT, LLM, and TTS
            
            # Keep the task running
            while conn.v2v_active:
                await asyncio.sleep(0.1)

        except Exception as e:
            self.logger.bind(tag=TAG).error(f"Voice agent error: {e}")
            conn.v2v_active = False

    async def handle_audio_input(self, conn, audio_data: bytes) -> None:
        """
        处理输入音频并发送到LiveKit

        Args:
            conn: 连接对象
            audio_data: 音频数据（Opus格式）
        """
        if not conn.v2v_active or not conn.v2v_room:
            return

        try:
            # Create audio source if not exists
            if not hasattr(conn, 'v2v_audio_source'):
                from livekit import rtc
                
                # Create audio source: 16kHz sample rate, 1 channel
                conn.v2v_audio_source = rtc.AudioSource(16000, 1)
                
                # Create and publish audio track
                track = rtc.LocalAudioTrack.create_audio_track(
                    "microphone", conn.v2v_audio_source
                )
                
                options = rtc.TrackPublishOptions()
                options.source = rtc.TrackSource.SOURCE_MICROPHONE
                
                await conn.v2v_room.local_participant.publish_track(
                    track, options
                )
                
                self.logger.bind(tag=TAG).info("Published audio track to LiveKit")

            # Decode Opus to PCM for LiveKit
            # Hardware sends Opus-encoded audio, we need PCM for LiveKit
            if not hasattr(conn, 'v2v_opus_decoder'):
                import opuslib_next
                conn.v2v_opus_decoder = opuslib_next.Decoder(16000, 1)
            
            try:
                # Decode Opus to PCM (frame_size depends on the opus packet)
                # Typically 320 samples for 20ms at 16kHz
                pcm_data = conn.v2v_opus_decoder.decode(audio_data, frame_size=320)
                
                # Create audio frame for LiveKit
                from livekit import rtc
                import numpy as np
                
                # Convert bytes to numpy array (int16)
                audio_array = np.frombuffer(pcm_data, dtype=np.int16)
                
                # Create AudioFrame
                audio_frame = rtc.AudioFrame(
                    data=audio_array.tobytes(),
                    sample_rate=16000,
                    num_channels=1,
                    samples_per_channel=len(audio_array),
                )
                
                # Capture the frame to the audio source
                await conn.v2v_audio_source.capture_frame(audio_frame)
                
            except Exception as decode_error:
                self.logger.bind(tag=TAG).debug(f"Audio decode error: {decode_error}")
            
        except Exception as e:
            self.logger.bind(tag=TAG).error(
                f"Failed to handle audio input in LiveKit: {e}"
            )

    async def stop_conversation(self, conn) -> None:
        """
        停止LiveKit对话

        Args:
            conn: 连接对象
        """
        try:
            conn.v2v_active = False
            
            # Stop the agent task
            if hasattr(conn, 'v2v_agent_task') and conn.v2v_agent_task:
                conn.v2v_agent_task.cancel()
                try:
                    await conn.v2v_agent_task
                except asyncio.CancelledError:
                    pass
            
            # Unpublish tracks
            if hasattr(conn, 'v2v_audio_source') and conn.v2v_room:
                if conn.v2v_room.local_participant:
                    tracks = conn.v2v_room.local_participant.track_publications
                    for sid, track_pub in tracks.items():
                        await conn.v2v_room.local_participant.unpublish_track(sid)

            # Disconnect from room
            if conn.v2v_room:
                await conn.v2v_room.disconnect()
                conn.v2v_room = None

            self.logger.bind(tag=TAG).info("LiveKit conversation stopped")

        except Exception as e:
            self.logger.bind(tag=TAG).error(
                f"Error stopping LiveKit conversation: {e}"
            )

    async def cleanup(self, conn) -> None:
        """
        清理LiveKit资源

        Args:
            conn: 连接对象
        """
        await self.stop_conversation(conn)
        
        # Clean up connection attributes
        attrs_to_clean = [
            'v2v_room', 'v2v_session', 'v2v_audio_source', 
            'v2v_agent_task', 'v2v_opus_decoder',
            'livekit_agents', 'livekit_rtc', 'livekit_openai',
            'livekit_silero', 'livekit_noise_cancellation'
        ]
        
        for attr in attrs_to_clean:
            if hasattr(conn, attr):
                delattr(conn, attr)

        self.logger.bind(tag=TAG).info("LiveKit V2V cleanup completed")
