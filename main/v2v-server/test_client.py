import asyncio
import websockets
import json
import base64
import sounddevice as sd
import numpy as np
import opuslib_next as opuslib
from queue import Queue
import sys

SAMPLE_RATE = 16000
FRAME_SIZE = 960
CHANNELS = 1

AUDIO_THRESHOLD = 0.15
SILENCE_FRAMES_BEFORE_STOP = 150


class HardwareSimulator:
    def __init__(self, uri):
        self.uri = uri
        self.websocket = None
        self.running = False
        
        self.opus_encoder = opuslib.Encoder(SAMPLE_RATE, CHANNELS, opuslib.APPLICATION_VOIP)
        self.opus_decoder = opuslib.Decoder(SAMPLE_RATE, CHANNELS)
        
        self.audio_input_queue = Queue()
        self.audio_output_queue = Queue()
        
        self.agent_speaking = False
        self.silence_counter = 0
        self.total_sent_bytes = 0
        self.total_received_bytes = 0
        
    def audio_input_callback(self, indata, frames, time, status):
        if status:
            print(f"Input status: {status}")
        if self.running:
            audio_data = indata.copy().flatten()
            self.audio_input_queue.put(audio_data)
    
    def audio_output_callback(self, outdata, frames, time, status):
        if status:
            print(f"Output status: {status}")
        
        if self.audio_output_queue.qsize() > 0:
            try:
                data = self.audio_output_queue.get_nowait()
                if len(data) == frames:
                    outdata[:] = data.reshape(-1, 1)
                else:
                    outdata.fill(0)
            except Exception:
                outdata.fill(0)
        else:
            outdata.fill(0)
    
    async def send_audio_loop(self):
        print("Audio capture started")
        while self.running:
            try:
                if not self.audio_input_queue.empty():
                    pcm_data = self.audio_input_queue.get()
                    
                    if len(pcm_data) == FRAME_SIZE:
                        audio_level = np.abs(pcm_data).mean()
                        
                        if self.agent_speaking and audio_level < AUDIO_THRESHOLD:
                            self.silence_counter += 1
                            if self.silence_counter < SILENCE_FRAMES_BEFORE_STOP:
                                await asyncio.sleep(0.01)
                                continue
                        else:
                            self.silence_counter = 0
                        
                        if audio_level > AUDIO_THRESHOLD or not self.agent_speaking:
                            pcm_bytes = (pcm_data * 32767).astype(np.int16).tobytes()
                            opus_data = self.opus_encoder.encode(pcm_bytes, FRAME_SIZE)
                            
                            await self.websocket.send(opus_data)
                            self.total_sent_bytes += len(opus_data)
                            
                            self._print_progress_bar("UP", self.total_sent_bytes, audio_level)
                
                await asyncio.sleep(0.01)
            except Exception as e:
                print(f"\nError sending audio: {e}")
                break
    
    def _print_progress_bar(self, label, total_bytes, level=None):
        kb = total_bytes / 1024
        bar_length = 20
        if level is not None:
            filled = int(bar_length * min(level * 10, 1.0))
            bar = "#" * filled + "-" * (bar_length - filled)
            sys.stdout.write(f"\r{label}: {kb:6.1f}KB [{bar}] {level:.3f}")
        else:
            bar = "#" * bar_length
            sys.stdout.write(f"\r{label}: {kb:6.1f}KB [{bar}]")
        sys.stdout.flush()
    
    async def receive_audio_loop(self):
        print("Audio playback started")
        try:
            async for message in self.websocket:
                if not self.running:
                    break
                
                if isinstance(message, str):
                    data = json.loads(message)
                    msg_type = data.get("type")
                    
                    if msg_type == "hello":
                        print("\nReceived hello response from server")
                        session_id = data.get("session_id", "")
                        print(f"   Session ID: {session_id}")
                    
                    elif msg_type == "audio":
                        opus_b64 = data.get("data", "")
                        if opus_b64:
                            try:
                                opus_data = base64.b64decode(opus_b64)
                                pcm_data = self.opus_decoder.decode(opus_data, FRAME_SIZE)
                                
                                pcm_array = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32767.0
                                self.audio_output_queue.put(pcm_array)
                                self.total_received_bytes += len(opus_data)
                                
                                audio_level = np.abs(pcm_array).mean()
                                self._print_progress_bar("DN", self.total_received_bytes, audio_level)
                            except Exception as e:
                                print(f"\nError decoding audio: {e}")
                    
                    elif msg_type == "tts":
                        state = data.get("state")
                        if state == "start":
                            self.agent_speaking = True
                            self.silence_counter = 0
                            print("\nAgent started speaking")
                        elif state == "stop":
                            self.agent_speaking = False
                            self.silence_counter = 0
                            print("\nAgent stopped speaking")
                    
                    else:
                        print(f"\nReceived: {data}")
                        
        except websockets.exceptions.ConnectionClosed:
            print("\nConnection closed")
        except Exception as e:
            print(f"\nError receiving audio: {e}")
    
    async def run(self):
        headers = {
            "device-id": "simulator_laptop"
        }
        
        print(f"Connecting to {self.uri}...")
        async with websockets.connect(self.uri, additional_headers=headers) as websocket:
            self.websocket = websocket
            self.running = True
            
            print("Connected to proxy server")
            
            hello_message = {
                "type": "hello",
                "version": 1,
                "audio_params": {
                    "format": "opus",
                    "sample_rate": SAMPLE_RATE,
                    "channels": CHANNELS,
                    "frame_duration": 60
                }
            }
            await websocket.send(json.dumps(hello_message))
            print("Sent hello message")
            
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=np.float32,
                blocksize=FRAME_SIZE,
                callback=self.audio_input_callback
            ), sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype=np.float32,
                blocksize=FRAME_SIZE,
                callback=self.audio_output_callback
            ):
                print("\n" + "="*50)
                print("Hardware Simulator Running")
                print("="*50)
                print("Press Ctrl+C to stop\n")
                
                send_task = asyncio.create_task(self.send_audio_loop())
                receive_task = asyncio.create_task(self.receive_audio_loop())
                
                try:
                    await asyncio.gather(send_task, receive_task)
                except KeyboardInterrupt:
                    print("\nStopping...")
                    self.running = False
                    send_task.cancel()
                    receive_task.cancel()


async def main():
    uri = "ws://localhost:8765/v2v"
    simulator = HardwareSimulator(uri)
    
    try:
        await simulator.run()
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    print("Starting Hardware Simulator...")
    print(f"   Sample Rate: {SAMPLE_RATE} Hz")
    print(f"   Frame Size: {FRAME_SIZE} samples")
    print(f"   Channels: {CHANNELS}")
    print()
    
    print("Available audio devices:")
    print(sd.query_devices())
    print()
    
    asyncio.run(main())
