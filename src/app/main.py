import os
import sys

# src/common を import できるようにする(exe化後は PyInstaller の --paths で同梱済み)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))

# Hugging Face(モデルのダウンロード)の決まりごと。ライブラリが読み込まれる前に決めないと効かない
# - Xet を使わない: 途中のデータをインストール先の外(ユーザーの .cache)に貯めず、進み具合も数えられるように
# - 進捗バーを出さない: exe はコンソールの無い形でビルドしているので、書き込む先が無くてエラーになる
# - シンボリックリンクが使えない警告を出さない(Windows では実物を置く形で問題なく動く)
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

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
# 置き場所は paths.CUDA_DIRS(exe化後: exeの横の cuda、開発中: 仮想環境の nvidia パッケージ)
# ctranslate2 を初めて読み込む(cuda_check)より前に足さないと効かない
# ========================================================
from edition import EDITION
from paths import CUDA_DIRS

if EDITION == "gpu":
    for p in CUDA_DIRS:
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
import model
import model_store
from key_shortcut import MainStateManager
from audio import recording_function
from transcribe import whisper_function
from gui_indicator import IndicatorWindow
import tray_icon
import main_window
import history
import llm_correct
import llm_vocab
import undo_input
import candidates
import candidate_window
import sounds


# ========================================================
# 初期化処理
# ========================================================
state_manager = MainStateManager()

cleanup_temp()  # 残っていたtemp_ファイルを消去

settings = load_config()  # config.jsonを読み込む
history.load()  # 入力履歴(history.json)を読み込む
llm_vocab.load()  # 入力補正の「よく使う言葉」(llm_vocab.csv)を読み込む

## faster-Whisperのモデル読み込み
## 選ばれているモデルが手元に無ければ読み込まずに起動する(窓がモデルタブを開いて、ダウンロードしてもらう)
## 手元にあるのに読めない(壊れている、CUDA が無いなど)ときは、エラーを出して終了する
model_missing = model_store.local_path(settings["model_size"]) is None
if model_missing:
    print(f"モデル '{settings['model_size']}' が手元にありません。ダウンロードを待ちます")
else:
    startup.set_status(f"モデルを読み込み中({settings['model_size']})…")
    try:
        model.set_model(model.load_model(settings["model_size"]), settings["model_size"])
    except model.ModelLoadError as e:
        startup.close()
        model.exit_with_load_error(e)

## 入力補正(GPU版、オンのとき)の llama-server を裏で立ち上げる。待たずに次へ進み、準備ができるまでは補正せずに入力する
llm_correct.start()

## ショートカットキーの登録(音声入力・入力モード切り替え・直前の入力を取り消す・候補を出す)
## 登録できなくても終了しない(窓がショートカットタブを開いて知らせ、そこで選び直してもらう)
## 取り消したら「候補を出す」の候補も忘れる(入れ替える入力が無くなるので)
state_manager.set_handler("undo", lambda: (undo_input.undo(), candidates.forget()))
state_manager.can_start = model.is_ready
state_manager.on_start_blocked = lambda: main_window.show("model")  # モデルタブでダウンロードしてもらう
## 候補を出す(GPU版だけ)。候補の窓が開いている間だけ ↑↓・Enter・Esc も借りる(candidate_window.py)
state_manager.set_handler("candidates", lambda: candidate_window.request("open_or_next"))
state_manager.set_handler("cand_up", lambda: candidate_window.request("up"))
state_manager.set_handler("cand_down", lambda: candidate_window.request("down"))
state_manager.set_handler("cand_ok", lambda: candidate_window.request("ok"))
state_manager.set_handler("cand_cancel", lambda: candidate_window.request("cancel"))
shortcut_errors = state_manager.start_listener({
    "toggle": settings["shortcut_key"],
    "undo": settings["undo_key"],
    "mode": settings["mode_key"],
    **({"candidates": settings["candidates_key"]} if EDITION == "gpu" else {}),
})

print("動作準備完了")

# 起動中インジケーターを閉じる(ここで全準備完了)
startup.close()
sounds.play("startup")  # 準備ができたことを音で知らせる


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
    args=(wav_queue,)
).start()

## 文字起こしスレッド開始
threading.Thread(
    target=whisper_function,
    args=(wav_queue,)
).start()

## システムトレイを別スレッドで起動
tray_icon.start_tray_in_background()

## 本体の窓を表示(閉じられるまでここで待つ)
main_window.create(
    shortcut_errors={action: error[0] for action, error in shortcut_errors.items()},
)
main_window.start()

## 窓の×で閉じられたら、アプリごと終了する
## 録音・文字起こしのスレッドは止まらないので os._exit で終わらせる
os._exit(0)
