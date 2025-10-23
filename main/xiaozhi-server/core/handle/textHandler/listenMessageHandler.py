import time
from typing import Dict, Any

from core.handle.receiveAudioHandle import handleAudioMessage, startToChat
from core.handle.reportHandle import enqueue_asr_report
from core.handle.sendAudioHandle import send_stt_message, send_tts_message
from core.handle.textMessageHandler import TextMessageHandler
from core.handle.textMessageType import TextMessageType
from core.utils.util import remove_punctuation_and_length

TAG = __name__

class ListenTextMessageHandler(TextMessageHandler):
    """Listen消息处理器"""

    @property
    def message_type(self) -> TextMessageType:
        return TextMessageType.LISTEN

    async def handle(self, conn, msg_json: Dict[str, Any]) -> None:
        if "mode" in msg_json:
            conn.client_listen_mode = msg_json["mode"]
            conn.logger.bind(tag=TAG).debug(
                f"客户端拾音模式：{conn.client_listen_mode}"
            )
        if msg_json["state"] == "start":
            conn.client_have_voice = True
            conn.client_voice_stop = False
            
            # V2V mode: IMMEDIATELY interrupt agent and prioritize user input
            if getattr(conn, 'enable_voice2voice', False) and hasattr(conn, 'v2v') and conn.v2v:
                conn.logger.bind(tag=TAG).info("👤 🚨 USER INPUT DETECTED - HIGHEST PRIORITY!")
                
                # STEP 1: Stop agent audio immediately
                conn.client_abort = True
                conn.client_is_speaking = False
                
                # STEP 2: Clear audio buffers to prevent old audio from playing
                if hasattr(conn, 'elevenlabs_audio_buffer'):
                    conn.elevenlabs_audio_buffer.clear()
                if hasattr(conn, 'elevenlabs_audio_started'):
                    conn.elevenlabs_audio_started = False
                    
                # STEP 3: Reset flow control for clean state
                if hasattr(conn, 'audio_flow_control'):
                    conn.audio_flow_control = None
                
                # STEP 4: Notify ElevenLabs that user wants to speak (triggers interruption)
                await conn.v2v.notify_user_speaking(conn)
                
                # STEP 5: Clear abort flag to allow user audio input
                conn.client_abort = False
                
                # STEP 6: Reset input counter for clean logging
                if hasattr(conn, 'elevenlabs_input_count'):
                    conn.elevenlabs_input_count = 0
                
                conn.logger.bind(tag=TAG).info("✅ Agent interrupted, ready for user input")
        elif msg_json["state"] == "stop":
            conn.client_have_voice = True
            conn.client_voice_stop = True
            if len(conn.asr_audio) > 0:
                await handleAudioMessage(conn, b"")
        elif msg_json["state"] == "detect":
            conn.client_have_voice = False
            conn.asr_audio.clear()
            if "text" in msg_json:
                conn.last_activity_time = time.time() * 1000
                original_text = msg_json["text"]  # 保留原始文本
                filtered_len, filtered_text = remove_punctuation_and_length(
                    original_text
                )

                # 识别是否是唤醒词
                is_wakeup_words = filtered_text in conn.config.get("wakeup_words")
                # 是否开启唤醒词回复
                enable_greeting = conn.config.get("enable_greeting", True)

                if is_wakeup_words and not enable_greeting:
                    # 如果是唤醒词，且关闭了唤醒词回复，就不用回答
                    await send_stt_message(conn, original_text)
                    await send_tts_message(conn, "stop", None)
                    conn.client_is_speaking = False
                elif is_wakeup_words:
                    conn.just_woken_up = True
                    # 上报纯文字数据（复用ASR上报功能，但不提供音频数据）
                    enqueue_asr_report(conn, "嘿，你好呀", [])
                    await startToChat(conn, "嘿，你好呀")
                else:
                    # 上报纯文字数据（复用ASR上报功能，但不提供音频数据）
                    enqueue_asr_report(conn, original_text, [])
                    # 否则需要LLM对文字内容进行答复
                    await startToChat(conn, original_text)