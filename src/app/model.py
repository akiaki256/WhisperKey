from faster_whisper import WhisperModel
import os
import sys

from error_dialog import show_error
from edition import EDITION
from paths import MODELS_DIR


class ModelLoadError(Exception):
    """モデル読み込みに失敗した時の例外"""
    pass


def load_model(model_size):
    print("faster-Whisper model load：start")
    try:
        models_dir = MODELS_DIR

        if not os.path.exists(models_dir):
            print("not found 'models'dir")
            os.makedirs(models_dir)
            print("maked 'models'dir")

        # edition別にdevice/compute_typeを決定
        if EDITION == "gpu":
            device = "cuda"
            compute_type = "float16"
        else:  # cpu
            device = "cpu"
            compute_type = "int8"
        
        print(f"faster-Whisper model load：edition={EDITION}, device={device}, compute_type={compute_type}")
        
        model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            download_root=models_dir,
        )

        print(f"faster-Whisper model load：success! modelname={model_size}")

        return model
    
    except Exception as e:
        show_error(
            "モデル読み込みエラー",
            "faster-Whisperモデルの読み込みに失敗したためソフトを終了します\n\n"
            "以下のいずれかが原因の可能性があります:\n"
            "・config.jsonの'model_size'の値が不正\n"
            "・インターネット接続の問題\n"
            "・'models/'フォルダの破損\n"
            "・(GPU版のみ) CUDA/cuDNNが正しくインストールされていない"
        )
        print(f"error: {e}")
        sys.exit(1)
