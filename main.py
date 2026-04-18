import os
import sys

# ★ PATH 環境変数に DLL パスを追加（最優先で検索される）
venv_path = os.path.dirname(sys.executable)
cuda_bin = os.path.abspath(os.path.join(venv_path, "..", "Lib", "site-packages", "nvidia", "cublas", "bin"))
cudnn_bin = os.path.abspath(os.path.join(venv_path, "..", "Lib", "site-packages", "nvidia", "cudnn", "bin"))

os.environ["PATH"] = cuda_bin + os.pathsep + cudnn_bin + os.pathsep + os.environ["PATH"]

# ====== 多重起動防止 ======
import ctypes

try:
    import win32event
    import win32api
    import winerror
    
    # 名前付きMutexを取得
    _mutex_handle = win32event.CreateMutex(None, False, "Global\\WhisperKey_MainProcess")
    
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        # すでに起動中 → Windows標準のMessageBoxでお知らせして終了
        ctypes.windll.user32.MessageBoxW(
            0,
            "WhisperKeyはすでに起動しています。",
            "起動エラー",
            0x30  # MB_OK + MB_ICONWARNING
        )
        sys.exit(0)
except ImportError:
    # pywin32が無い環境では多重起動チェックをスキップ
    print("warning: pywin32 is not available. multi-instance check is skipped.")
# ==========================

import threading          # 処理を同時実行できるようになる
from queue import Queue

from config import load_config
from cleanup import cleanup_temp
from model import load_model
from key_shortcut import MainStateManager
from audio import recording_function
from transcribe import whisper_function
from gui_indicator import IndicatorWindow

# インスタンス作成
state_manager = MainStateManager()
indicator = IndicatorWindow()


# 起動直後の処理
cleanup_temp() #残っていたtemp_ファイルを消去

settings = load_config() #config.jsonを読み込む

## faster-Whisperのモデル読み込み
model = load_model(settings["model_size"])

## shortcut_key押下で聞き取りモード切り替え
state_manager.start_listener(settings["shortcut_key"])

print("動作準備完了")
wav_queue = Queue()


# 以下メイン処理

## 録音スレッド開始
threading.Thread(
    target=recording_function,
    args=(
        settings["volume_threshold"],
        settings["silence_duration"],
        settings["audio_device_index"],
        settings["audio_device_sample_rate"],
        wav_queue
    )
).start()

## 文字起こしスレッド開始
threading.Thread(
    target=whisper_function,
    args=(model, settings["language"], wav_queue)
).start()

## インジケーター表示
indicator.run()