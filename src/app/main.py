import os
import sys

# src/common を import できるようにする(exe化後は PyInstaller の --paths で同梱済み)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))

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
# CUDA DLL パス設定(GPU版)
# 開発時: 仮想環境のsite-packages内のnvidiaパッケージを参照
# exe化後: sys._MEIPASS配下に展開されたDLLを参照
# ========================================================
from edition import EDITION

if EDITION == "gpu":
    if getattr(sys, "frozen", False):
        # exe化後: PyInstallerが展開した一時ディレクトリ
        base_path = sys._MEIPASS
    else:
        # 開発中: 仮想環境のsite-packages
        base_path = os.path.join(os.path.dirname(sys.executable), "..", "Lib", "site-packages")
    
    cuda_bin = os.path.abspath(os.path.join(base_path, "nvidia", "cublas", "bin"))
    cudnn_bin = os.path.abspath(os.path.join(base_path, "nvidia", "cudnn", "bin"))
    
    for p in [cuda_bin, cudnn_bin]:
        if os.path.exists(p):
            os.environ["PATH"] = p + os.pathsep + os.environ["PATH"]
            # Python 3.8+ 推奨: DLL検索パスを明示的に追加
            if hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(p)
                except Exception:
                    pass


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
import main_window


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

## インジケーター(録音中の緑丸)を専用スレッドで起動
## メインスレッドは本体の窓(pywebview)が使うため。
## tkinter の窓の作成から mainloop までを、すべてこのスレッドの中で行う
def run_indicator():
    IndicatorWindow(settings["indicator_x"], settings["indicator_y"]).run()

threading.Thread(target=run_indicator, name="indicator", daemon=True).start()

## 録音スレッド開始
threading.Thread(
    target=recording_function,
    args=(
        settings["audio_device_index"],
        settings["audio_device_sample_rate"],
        wav_queue
    )
).start()

## 文字起こしスレッド開始
threading.Thread(
    target=whisper_function,
    args=(model, wav_queue)
).start()

## システムトレイを別スレッドで起動
tray_icon.start_tray_in_background()

## 本体の窓を表示(閉じられるまでここで待つ)
main_window.create(loaded_model=settings["model_size"])
main_window.start()

## 窓の×で閉じられたら、アプリごと終了する
## 録音・文字起こしのスレッドは止まらないので os._exit で終わらせる
os._exit(0)
