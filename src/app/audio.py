import collections
import math
import os
import sys
import time
import pyaudio
import wave
import numpy as np
import config
from key_shortcut import MainStateManager
from error_dialog import show_error
from paths import TEMP_DIR
import audio_devices
from config_store import DEFAULT_DEVICE_LABEL

# インスタンス作成
state_manager = MainStateManager()

file_counter = 0  # ファイル名用のカウンター

# 今の音量(しきい値と同じ物差し)。録音のループが CHUNK ごとに書き、設定タブのレベルメーターが読む
_level = 0.0


def get_level():
    return _level

temp_dir = TEMP_DIR  # tempフォルダのパス

CHUNK = 2**10
FORMAT = pyaudio.paInt16
CHANNELS = 1

# 選んだマイクが抜かれていないか・戻ってきたかを見る間隔(CHUNK の数)。1 CHUNK は 1024 / 16000 = 0.064 秒なので約2秒
MIC_CHECK_CHUNKS = 31

# プレロール: 録音が始まる前の音を、この秒数ぶん取っておき、録音の頭にくっつける
# 録音は音量がしきい値を超えたかたまりから始まるので、それより前の小さな音(話し始めの子音など)が切れるのを防ぐ
PRE_ROLL_SECONDS = 0.3

# tempフォルダがなければ作成
if not os.path.exists(temp_dir):
    os.makedirs(temp_dir)


def open_mic(device_name):
    """
    PyAudio を作り直してから、マイクを名前で探して開く
    - PyAudio は作った瞬間のマイクの一覧を覚え続けるので、開くたびに作り直す(抜き差しに追いつくため)
    - 番号(index)は抜き差しでずれるため、名前で探す
    - 見つからない・開けないときは、既定のマイクで開く

    戻り値: (PyAudio, ストリーム, 実際に開いたマイクの名前)。既定のマイクも開けなければ None
    """
    rate = config.get("audio_device_sample_rate")
    p = pyaudio.PyAudio()

    device = audio_devices.find_device_by_name(device_name, p)  # 「既定のデバイス」なら None
    if device is None and device_name != DEFAULT_DEVICE_LABEL:
        print(f"マイク「{device_name}」が見つかりません。既定のマイクを使用します。")
    candidates = [(device["index"], device_name), (None, DEFAULT_DEVICE_LABEL)] if device else [(None, DEFAULT_DEVICE_LABEL)]

    for index, name in candidates:
        try:
            stream = p.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=rate,
                input=True,
                input_device_index=index,
                frames_per_buffer=CHUNK
            )
            print(f"マイク接続：成功（{name}, device_index={index}, rate={rate}Hz）")
            return p, stream, name
        except Exception as e:
            print(f"マイク接続：失敗（{name}, device_index={index}）: {e}")

    p.terminate()
    return None


def close_mic(p, stream):
    try:
        stream.close()
    except Exception:
        pass  # 抜かれたマイクは閉じるときにエラーになることがある
    p.terminate()


def exit_with_mic_error():
    show_error(
        "マイク接続エラー",
        "マイクに接続できませんでした。\n"
        "マイクが接続されているか、Windowsの設定を確認してください。\n"
        "ソフトを終了します。"
    )
    # 別スレッドから呼ばれるためsys.exitではプロセス全体が終了しない
    # os._exitでプロセスごと強制終了させる
    os._exit(1)


# マイクから音声をキャプチャ
def recording_function(wav_queue):
    """
    音量の閾値・無音判定の秒数・マイクは、画面で変えたらすぐ効くように、毎回 config から読む

    マイクを開き直すのは次のとき。開き直す前に、録音途中の音声を文字起こしに回す
    - 画面でマイクが変えられた
    - 選んだマイクが抜かれた
    - 読み込みでエラーが出た

    選んだマイクが抜かれた・開けなかったときは、設定も「既定のデバイス」に書き換える
    (表示と中身をそろえる。差し直しても自動では戻らないので、画面で選び直してもらう)

    wav_queue: Whisperスレッドと共有するキュー
    """
    global _level

    def set_default_mic():
        try:
            config.update({"audio_device_name": DEFAULT_DEVICE_LABEL})  # 画面にも知らせが届く
        except OSError as e:
            print(f"マイクの設定の保存に失敗: {e}")

    def open_selected_mic():
        """設定で選ばれているマイクを開く。開けずに既定のマイクになったら、設定も既定に書き換える"""
        wanted = config.get("audio_device_name")
        opened = open_mic(wanted)
        if opened is None:
            exit_with_mic_error()
        p, stream, name = opened
        if name != wanted:
            set_default_mic()
        # 既定に書き換えられていれば、それが「選ばれているマイク」
        return p, stream, name, config.get("audio_device_name")

    # current_mic: 今開いているマイク / requested_mic: 開いたときに設定で選ばれていたマイク
    # 設定が変わったかは requested_mic と比べる(設定の保存に失敗して食い違っても、開き直し続けないため)
    p, stream, current_mic, requested_mic = open_selected_mic()
    RATE = config.get("audio_device_sample_rate")
    chunk_count = 0

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
        wf.setsampwidth(pyaudio.get_sample_size(FORMAT))
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

    # 待っている間の、直近 PRE_ROLL_SECONDS ぶんの音(録音が始まったら頭にくっつける)
    # 一つの録音を文字起こしに回したら空にする(前の録音の終わりが、次の録音の頭に二重に入らないように)
    pre_roll = collections.deque(maxlen=max(1, math.ceil(PRE_ROLL_SECONDS * RATE / CHUNK)))

    reopen = False

    while True:
        # ---- マイクを開き直すかどうか ----
        chunk_count += 1
        if (chunk_count % MIC_CHECK_CHUNKS == 0
                and current_mic != DEFAULT_DEVICE_LABEL
                and current_mic not in audio_devices.get_live_input_names()):
            print(f"マイク「{current_mic}」が抜かれました。既定のマイクに切り替えます。")
            set_default_mic()

        if config.get("audio_device_name") != requested_mic:
            reopen = True

        if reopen:
            if state == "recording":
                save_and_queue(frames)
                state = "waiting"
                silence_duration = 0
                frames = []
            pre_roll.clear()   # 前のマイクの音を、次のマイクの録音に混ぜない
            close_mic(p, stream)
            p, stream, current_mic, requested_mic = open_selected_mic()
            reopen = False

        # ---- 読み込み ----
        try:
            data = stream.read(CHUNK, exception_on_overflow=False)
        except Exception as e:
            print(f"マイクの読み込みでエラー: {e}")
            reopen = True
            time.sleep(0.5)
            continue
        audio_data = np.frombuffer(data, dtype=np.int16)
        audio_data = audio_data.astype(np.float32)
        volume = np.sqrt(np.mean(audio_data**2))  # 無音を判断するための指数になるvolumeを定義
        _level = float(volume)  # 設定タブのレベルメーター用(録音オフの間も測っている)

        listening = state_manager.get_state() == "start"
        threshold = config.get("volume_threshold")
        duration = config.get("silence_duration")

        if state == "waiting":
            if listening and volume > threshold:
                print("録音開始！")
                state = "recording"
                frames = list(pre_roll) + [data]   # しきい値を超える前の音も入れる(プレロール)
                pre_roll.clear()
            else:
                pre_roll.append(data)

        elif state == "recording":
            if not listening:
                # オフが押されたところで区切る(押したあとの音声は入れない)
                save_and_queue(frames)
                state = "waiting"
                silence_duration = 0
                frames = []
                pre_roll.clear()
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
                    pre_roll.clear()

            else:
                silence_duration = 0
