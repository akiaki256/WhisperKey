import time
import os
import sys
import pyaudio
import wave
import numpy as np
from key_shortcut import MainStateManager
from error_dialog import show_error

# インスタンス作成
state_manager = MainStateManager()

file_counter = 0  # ファイル名用のカウンター

this_file = os.path.abspath(__file__)
project_root = os.path.dirname(this_file)
temp_dir = os.path.join(project_root, "temp")  # tempフォルダのパス

# tempフォルダがなければ作成
if not os.path.exists(temp_dir):
    os.makedirs(temp_dir)


# マイクから音声をキャプチャ
def recording_function(threshold, duration, device_index, sample_rate, wav_queue):
    """
    threshold: 音量の閾値
    duration: 無音判定の秒数
    device_index: マイクデバイスのindex（Noneなら既定デバイス）
    sample_rate: サンプルレート（通常16000Hz）
    wav_queue: Whisperスレッドと共有するキュー
    """
    CHUNK = 2**10
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = sample_rate
    global file_counter

    p = pyaudio.PyAudio()

    # device_indexの有効性チェック
    if device_index is not None:
        try:
            info = p.get_device_info_by_index(device_index)
            if info['maxInputChannels'] <= 0:
                print(f"指定デバイス(index={device_index})は入力デバイスではありません。既定デバイスを使用します。")
                device_index = None
                RATE = 16000
        except Exception:
            print(f"指定デバイス(index={device_index})が見つかりません。既定デバイスを使用します。")
            device_index = None
            RATE = 16000

    # マイク接続を試みる
    try:
        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=CHUNK
        )
        print(f"マイク接続：成功（device_index={device_index}, rate={RATE}Hz）")

    except Exception as e:
        show_error(
            "マイク接続エラー",
            "マイクに接続できませんでした。\n"
            "マイクが接続されているか、Windowsの設定を確認してください。\n"
            "ソフトを終了します。\n\n"
            f"詳細: {e}"
        )
        print(f"error: {e}")
        p.terminate()
        sys.exit(1)

        try:
            RATE = 16000  # フォールバック時は16kHz固定
            stream = p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                input_device_index=None,  # 既定デバイス
                frames_per_buffer=CHUNK
            )
            print(f"マイク接続：成功（既定デバイス, rate={RATE}Hz）")

        except Exception as e2:
            # フォールバックも失敗したら終了
            show_error(
                "マイク接続エラー",
                "既定のデバイスでもマイクに接続できませんでした。\n"
                "マイクが接続されているか、Windowsの設定を確認してください。\n"
                "ソフトを終了します。\n\n"
                f"詳細: {e2}"
            )
            print(f"error: {e2}")
            p.terminate()
            sys.exit(1)

    silence_duration = 0
    frames = []
    state = "waiting"

    while True:

        if state_manager.get_state() == "start":

            while state_manager.get_state() == "start":
                data = stream.read(CHUNK)
                audio_data = np.frombuffer(data, dtype=np.int16)
                audio_data = audio_data.astype(np.float32)
                volume = np.sqrt(np.mean(audio_data**2))  # 無音を判断するための指数になるvolumeを定義

                if state == "waiting":
                    if volume > threshold:
                        print("録音開始！")
                        state = "recording"
                        frames = [data]

                elif state == "recording":
                    frames.append(data)
                    if volume < threshold:
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

                            # 待機モードの条件復元
                            state = "waiting"
                            silence_duration = 0
                            frames = []

                    else:
                        silence_duration = 0

        else:
            time.sleep(0.1)

