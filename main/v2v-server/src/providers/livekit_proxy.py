import asyncio
import json
import base64
import logging
import os
import uuid
from typing import Optional
from fastapi import WebSocket
from livekit import rtc, api
import opuslib_next
import numpy as np
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


load_dotenv()
AGENT_NAME = os.getenv("LIVEKIT_AGENT_NAME", "xiaozhi-agent")


class LiveKitProxy:
    def __init__(self, livekit_url: str, api_key: str, api_secret: str, room_name: str = None):
        self.livekit_url = livekit_url
        self.api_key = api_key
        self.api_secret = api_secret
        self.room_name = room_name or f"hardware-{uuid.uuid4().hex[:8]}"
        self.room: Optional[rtc.Room] = None
        self.hardware_ws: Optional[WebSocket] = None
        self.audio_source: Optional[rtc.AudioSource] = None
        self.opus_encoder = opuslib_next.Encoder(16000, 1, opuslib_next.APPLICATION_VOIP)
        self.opus_decoder = opuslib_next.Decoder(16000, 1)
        self.audio_buffer = bytearray()
        self.active = False
        self.receive_task = None
        self.participant_identity = f"hardware-{uuid.uuid4().hex[:8]}"

    def _generate_token(self) -> str:
        token = (
            api.AccessToken(self.api_key, self.api_secret)
            .with_identity(self.participant_identity)
            .with_grants(api.VideoGrants(
                room_join=True,
                room=self.room_name,
                can_publish=True,
                can_subscribe=True
            ))
        )
        return token.to_jwt()

    async def _dispatch_agent(self):
        try:
            livekit_api = api.LiveKitAPI(
                url=self.livekit_url,
                api_key=self.api_key,
                api_secret=self.api_secret
            )
            
            dispatch = api.CreateAgentDispatchRequest(
                room=self.room_name,
                agent_name=AGENT_NAME
            )
            
            await livekit_api.agent_dispatch.create_dispatch(dispatch)
            logger.info(f"Dispatched agent '{AGENT_NAME}' to room: {self.room_name}")
            
            await livekit_api.aclose()
        except Exception as e:
            logger.error(f"Failed to dispatch agent: {e}")

    async def connect_to_livekit(self):
        self.room = rtc.Room()
        
        @self.room.on("participant_connected")
        def on_participant_connected(participant: rtc.RemoteParticipant):
            logger.info(f"Agent connected: {participant.identity}")
        
        @self.room.on("participant_disconnected")
        def on_participant_disconnected(participant: rtc.RemoteParticipant):
            logger.info(f"Agent disconnected: {participant.identity}")
        
        @self.room.on("track_subscribed")
        def on_track_subscribed(
            track: rtc.Track,
            publication: rtc.RemoteTrackPublication,
            participant: rtc.RemoteParticipant
        ):
            logger.info(f"Track subscribed: {track.kind} from {participant.identity}")
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                audio_stream = rtc.AudioStream(track)
                asyncio.ensure_future(self._receive_audio_from_livekit(audio_stream))
        
        token = self._generate_token()
        await self.room.connect(self.livekit_url, token)
        logger.info(f"Connected to LiveKit room: {self.room_name}")
        
        self.audio_source = rtc.AudioSource(16000, 1)
        track = rtc.LocalAudioTrack.create_audio_track("hardware-mic", self.audio_source)
        options = rtc.TrackPublishOptions()
        options.source = rtc.TrackSource.SOURCE_MICROPHONE
        await self.room.local_participant.publish_track(track, options)
        
        self.active = True
        logger.info("Audio track published to LiveKit")
        
        await self._dispatch_agent()

    def _resample_audio(self, pcm_data: bytes, from_rate: int, to_rate: int) -> bytes:
        if from_rate == to_rate:
            return pcm_data
        
        audio_array = np.frombuffer(pcm_data, dtype=np.int16)
        num_samples = int(len(audio_array) * to_rate / from_rate)
        resampled = np.interp(
            np.linspace(0, len(audio_array), num_samples),
            np.arange(len(audio_array)),
            audio_array.astype(np.float32)
        ).astype(np.int16)
        return resampled.tobytes()

    async def _receive_audio_from_livekit(self, audio_stream: rtc.AudioStream):
        logger.info("Starting audio receive from LiveKit agent...")
        frame_count = 0
        tts_started = False
        
        async for event in audio_stream:
            if not self.active:
                break
            
            try:
                audio_frame = event.frame
                frame_count += 1
                
                if frame_count == 1:
                    logger.info(f"First audio frame received: sample_rate={audio_frame.sample_rate}, "
                               f"channels={audio_frame.num_channels}, samples={audio_frame.samples_per_channel}")
                
                if not tts_started and self.hardware_ws:
                    await self.hardware_ws.send_json({"type": "tts", "state": "start"})
                    tts_started = True
                    logger.info("Sent TTS start to hardware")
                
                pcm_data = bytes(audio_frame.data)
                if audio_frame.sample_rate != 16000:
                    pcm_data = self._resample_audio(pcm_data, audio_frame.sample_rate, 16000)
                
                await self._send_audio_to_hardware(pcm_data)
                
                if frame_count % 50 == 0:
                    logger.info(f"Sent {frame_count} audio frames to hardware")
            except Exception as e:
                logger.error(f"Error processing audio from LiveKit: {e}", exc_info=True)

    async def _send_audio_to_hardware(self, pcm_data: bytes):
        try:
            if not self.hardware_ws:
                return
            
            self.audio_buffer.extend(pcm_data)
            
            frame_size = 1920
            packets_sent = 0
            while len(self.audio_buffer) >= frame_size:
                pcm_frame = bytes(self.audio_buffer[:frame_size])
                self.audio_buffer = self.audio_buffer[frame_size:]
                
                opus_data = self.opus_encoder.encode(pcm_frame, 960)
                
                await self.hardware_ws.send_bytes(opus_data)
                packets_sent += 1
            
            if packets_sent > 0 and not hasattr(self, '_first_packet_logged'):
                self._first_packet_logged = True
                logger.info(f"First opus packet sent to hardware (binary): {len(opus_data)} bytes")
                
        except Exception as e:
            logger.error(f"Error sending audio to hardware: {e}", exc_info=True)

    async def send_audio_to_livekit(self, opus_data: bytes):
        try:
            if not self.audio_source or not self.active:
                return
            
            pcm_data = self.opus_decoder.decode(opus_data, frame_size=960)
            
            import numpy as np
            pcm_array = np.frombuffer(pcm_data, dtype=np.int16)
            
            audio_frame = rtc.AudioFrame(
                data=pcm_array.tobytes(),
                sample_rate=16000,
                num_channels=1,
                samples_per_channel=len(pcm_array)
            )
            await self.audio_source.capture_frame(audio_frame)
            
        except Exception as e:
            logger.error(f"Failed to send audio to LiveKit: {e}")

    async def send_tts_stop(self):
        if self.hardware_ws:
            await self.hardware_ws.send_json({
                "type": "tts",
                "state": "stop"
            })

    async def disconnect(self):
        self.active = False
        
        if self.room:
            await self.room.disconnect()
            self.room = None
        
        self.hardware_ws = None
        logger.info("Disconnected from LiveKit")
