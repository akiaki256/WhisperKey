import os
import sys

# ★ PATH 環境変数に DLL パスを追加（最優先で検索される）
venv_path = os.path.dirname(sys.executable)
cuda_bin = os.path.abspath(os.path.join(venv_path, "..", "Lib", "site-packages", "nvidia", "cublas", "bin"))
cudnn_bin = os.path.abspath(os.path.join(venv_path, "..", "Lib", "site-packages", "nvidia", "cudnn", "bin"))

os.environ["PATH"] = cuda_bin + os.pathsep + cudnn_bin + os.pathsep + os.environ["PATH"]


import threading          # 処理を同時実行できるようになる
from queue import Queue

from config import load_config
from cleanup import cleanup_temp
from model import load_model, ModelLoadError
from key_shortcut import MainStateManager
from audio import recording_function
from transcribe import whisper_function
from gui_indicator import IndicatorWindow

# インスタンス作成
state_manager = MainStateManager()
indicator = IndicatorWindow()


DEFAULT_SETTING={
    "volume_threshold": 1700,
    "silence_duration": 1.3,
    "shortcut_key": "f9",
    "language": "ja",
    "model_size": "small"
}

# 起動直後の処理
cleanup_temp() #残っていたtemp_ファイルを消去
try:
    settings = load_config() #config.jsonを読み込む
    print("ユーザー設定の読込：完了")
except:
    settings = DEFAULT_SETTING
    print("設定ファイルが読込：不可のためデフォルト設定で起動します")


## faster-Whisperのモデル読み込み
print("faster-Whisper model load：start")
try:
    model = load_model(settings["model_size"])
    print(f"faster-Whisper model load：success! modelname={settings["model_size"]}")
except ModelLoadError as e:
    sys.exit(str(e))

## shortcut_key押下で聞き取りモード切り替え
state_manager.start_listener(settings["shortcut_key"])

print("動作準備完了")
wav_queue = Queue()



# 以下メイン処理

## 録音スレッド開始
threading.Thread(
    target=recording_function,
    args=(settings["volume_threshold"], settings["silence_duration"], wav_queue)
).start()

## 文字起こしスレッド開始
threading.Thread(
    target=whisper_function,
    args=(model, settings["language"], wav_queue)
).start()

## インジケーター表示
indicator.run()