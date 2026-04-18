import os
import sys

# ========================================================
# 起動中インジケーター表示(重いimportより前、最優先)
# ========================================================
from startup_indicator import StartupIndicator
startup = StartupIndicator()


# ========================================================
# 多重起動防止
# ========================================================
import ctypes

try:
    import win32event
    import win32api
    import winerror
    
    _mutex_handle = win32event.CreateMutex(None, False, "Global\\WhisperKey_MainProcess")
    
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        # 起動中インジケーターを閉じてからエラー表示
        startup.close()
        ctypes.windll.user32.MessageBoxW(
            0,
            "WhisperKeyはすでに起動しています。",
            "起動エラー",
            0x30  # MB_OK + MB_ICONWARNING
        )
        sys.exit(0)
except ImportError:
    print("warning: pywin32 is not available. multi-instance check is skipped.")


# ========================================================
# CUDA DLL パス設定(GPU版 & 開発環境のみ)
# exe化後はPyInstallerが自動でDLLパスを解決するので、この処理は不要
# ========================================================
from edition import EDITION

if EDITION == "gpu" and not getattr(sys, "frozen", False):
    venv_path = os.path.dirname(sys.executable)
    cuda_bin = os.path.abspath(os.path.join(venv_path, "..", "Lib", "site-packages", "nvidia", "cublas", "bin"))
    cudnn_bin = os.path.abspath(os.path.join(venv_path, "..", "Lib", "site-packages", "nvidia", "cudnn", "bin"))
    
    os.environ["PATH"] = cuda_bin + os.pathsep + cudnn_bin + os.pathsep + os.environ["PATH"]


# ========================================================
# 起動時CUDAチェック(GPU版のみ)
# ========================================================
if EDITION == "gpu":
    from cuda_check import ensure_cuda_available
    try:
        ensure_cuda_available()
    except SystemExit:
        # CUDAチェック失敗時は起動中インジケーターを閉じて終了
        startup.close()
        raise


# ========================================================
# 重いimport(この間にモデル読込等で時間がかかる)
# ========================================================
import threading
from queue import Queue

from config import load_config
from cleanup import cleanup_temp
from model import load_model
from key_shortcut import MainStateManager
from audio import recording_function
from transcribe import whisper_function
from gui_indicator import IndicatorWindow
import tray_icon


# ========================================================
# 初期化処理
# ========================================================
state_manager = MainStateManager()

cleanup_temp()  # 残っていたtemp_ファイルを消去

settings = load_config()  # config.jsonを読み込む

## faster-Whisperのモデル読み込み
model = load_model(settings["model_size"])

## shortcut_key押下で聞き取りモード切り替え
state_manager.start_listener(settings["shortcut_key"])

print("動作準備完了")

# 起動中インジケーターを閉じる(ここで全準備完了)
startup.close()


# ========================================================
# メイン処理
# ========================================================
wav_queue = Queue()

# 通常インジケーター(録音中の緑丸)を作成
indicator = IndicatorWindow()

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

## システムトレイを別スレッドで起動
tray_icon.start_tray_in_background()

## インジケーター表示(mainloop)
indicator.run()
