"""
Whisper のモデルの読み込みと、「今読み込まれているモデル」

- load_model(name): 手元のフォルダから読む(ネットには出ない)。失敗したら ModelLoadError
  以前はモデル名を渡していたため、モデルが手元にあっても起動のたびに Hugging Face へ新しい版を聞きに行っていた
- set_model(model, name) / get_model() / is_ready(): 今読み込まれているモデル
  選ばれているモデルが手元に無いまま起動したときは、ダウンロードが終わってから読み込まれる。
  文字起こしの係は get_model() で、読み込まれるまで待つ
- exit_with_load_error(e): 起動時に読み込めなかったとき(壊れている、CUDA が無いなど)。エラーを出して終了する
"""

from faster_whisper import WhisperModel
import os
import sys
import threading

import model_store
from error_dialog import show_error
from edition import EDITION
from paths import MODELS_DIR


class ModelLoadError(Exception):
    """モデル読み込みに失敗した時の例外"""
    pass


_model = None
_model_name = None
_ready = threading.Event()


def load_model(model_size):
    """手元のフォルダからモデルを読む。手元に無い・読めないときは ModelLoadError"""
    print("faster-Whisper model load：start")
    os.makedirs(MODELS_DIR, exist_ok=True)

    path = model_store.local_path(model_size)
    if path is None:
        raise ModelLoadError(f"モデル '{model_size}' が手元にありません")

    # edition別にdevice/compute_typeを決定
    if EDITION == "gpu":
        device = "cuda"
        compute_type = "float16"
    else:  # cpu
        device = "cpu"
        compute_type = "int8"

    print(f"faster-Whisper model load：edition={EDITION}, device={device}, compute_type={compute_type}")
    try:
        model = WhisperModel(path, device=device, compute_type=compute_type)
    except Exception as e:
        raise ModelLoadError(str(e)) from e

    print(f"faster-Whisper model load：success! modelname={model_size}")
    return model


def set_model(model, name):
    global _model, _model_name
    _model, _model_name = model, name
    _ready.set()


def get_model():
    """今のモデル。まだ読み込まれていなければ、読み込まれるまで待つ"""
    _ready.wait()
    return _model


def is_ready():
    return _ready.is_set()


def loaded_name():
    """読み込まれているモデルの名前(まだなら None)"""
    return _model_name


def exit_with_load_error(e):
    show_error(
        "モデル読み込みエラー",
        "faster-Whisperモデルの読み込みに失敗したためソフトを終了します\n\n"
        "以下のいずれかが原因の可能性があります:\n"
        "・'models/'フォルダの破損\n"
        "・(GPU版のみ) CUDA/cuDNNが正しくインストールされていない"
    )
    print(f"error: {e}")
    sys.exit(1)
