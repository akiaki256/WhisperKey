import os
import sys
import pyaudio
import wave
import numpy as np
import config
from key_shortcut import MainStateManager
from error_dialog import show_error
from paths import TEMP_DIR

# インスタンス作成
state_manager = MainStateManager()

file_counter = 0  # ファイル名用のカウンター

temp_dir = TEMP_DIR  # tempフォルダのパス

# tempフォルダがなければ作成
if not os.path.exists(temp_dir):
    os.makedirs(temp_dir)


# マイクから音声をキャプチャ
def recording_function(device_index, sample_rate, wav_queue):
    """
    音量の閾値と無音判定の秒数は、画面で変えたらすぐ効くように、毎回 config から読む

    device_index: マイクデバイスのindex（Noneなら既定デバイス）
    sample_rate: サンプルレート（通常16000Hz）
    wav_queue: Whisperスレッドと共有するキュー
    """
    CHUNK = 2**10
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = sample_rate

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
        # 別スレッドから呼ばれるためsys.exitではプロセス全体が終了しない
        # os._exitでプロセスごと強制終了させる
        os._exit(1)

    def save_and_queue(frames):
        """録音した音声を wav にして、文字起こしのキューに入れる"""
        global file_counter

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

        # 文字起こしが先に終わって数が負にならないよう、キューに入れる前に数える
        state_manager.add_pending()
        wav_queue.put(output_path)
        print(f"キューに追加: {filename}")

    # マイクはオフの間も読み続ける(読まずにいると、溜まった古い音声が次の録音に混ざるため)
    # 録音オフのときは、声が大きくても「しきい値を超えていない」扱いにする
    # 録音中にオフにされたら、そこまでの音声をすぐ文字起こしに回す
    silence_duration = 0
    frames = []
    state = "waiting"

    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        audio_data = np.frombuffer(data, dtype=np.int16)
        audio_data = audio_data.astype(np.float32)
        volume = np.sqrt(np.mean(audio_data**2))  # 無音を判断するための指数になるvolumeを定義

        listening = state_manager.get_state() == "start"
        threshold = config.get("volume_threshold")
        duration = config.get("silence_duration")

        if state == "waiting":
            if listening and volume > threshold:
                print("録音開始！")
                state = "recording"
                frames = [data]

        elif state == "recording":
            if not listening:
                # オフが押されたところで区切る(押したあとの音声は入れない)
                save_and_queue(frames)
                state = "waiting"
                silence_duration = 0
                frames = []
                continue

            frames.append(data)
            if volume < threshold:
                silence_duration += CHUNK / RATE
                if silence_duration > duration:
                    save_and_queue(frames)

                    # 待機モードの条件復元
                    state = "waiting"
                    silence_duration = 0
                    frames = []

            else:
                silence_duration = 0
