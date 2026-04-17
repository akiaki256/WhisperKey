import time
import os
import pyaudio
import wave
import numpy as np
from key_shortcut import MainStateManager

# インスタンス作成
state_manager = MainStateManager()

file_counter = 0  # ファイル名用のカウンター

this_file = os.path.abspath(__file__)
project_root = os.path.dirname(this_file)
temp_dir = os.path.join(project_root, "temp")# tempフォルダのパス

# tempフォルダがなければ作成
if not os.path.exists(temp_dir):
    os.makedirs(temp_dir)

#マイクから音声をキャプチャ
def recording_function(threshold, duration, wav_queue):
    """
    threshold: 音量の閾値
    duration: 無音判定の秒数
    wav_queue: Whisperスレッドと共有するキュー
    """
    CHUNK = 2**10
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    global file_counter

    p = pyaudio.PyAudio()
    stream = p.open(format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK)

    silence_duration = 0
    frames = []
    state = "waiting"

    while True:

        if state_manager.get_state() == "start":

            while state_manager.get_state() == "start":
                data = stream.read(CHUNK)
                audio_data = np.frombuffer(data, dtype=np.int16)
                audio_data = audio_data.astype(np.float32)
                volume = np.sqrt(np.mean(audio_data**2))   #無音を判断するための指数になるvolumeを定義

                if state == "waiting":
                    if volume > threshold:
                        print("録音開始！")
                        state = "recording"
                        frames = [data]

                elif state == "recording":
                    frames.append(data)
                    if volume < threshold :
                        silence_duration += CHUNK / RATE
                        if silence_duration > duration:

                            # ファイル名を作成
                            file_counter += 1
                            filename = f"temp_{file_counter}.wav"
                            output_path = os.path.join(temp_dir, filename)
                            
                            # wavファイルとして書き込み
                            wf = wave.open(output_path, 'wb')
                            wf.setnchannels(CHANNELS)
                            wf.setsampwidth(p.get_sample_size(FORMAT))
                            wf.setframerate(RATE)
                            wf.writeframes(b''.join(frames))
                            wf.close()
                            
                            wav_queue.put(output_path)
                            print(f"キューに追加: {filename}")

                            #待機モードの条件復元
                            state = "waiting"
                            silence_duration = 0
                            frames = []

                    else:
                        silence_duration = 0
                        
        else:
            time.sleep(0.1)
    

