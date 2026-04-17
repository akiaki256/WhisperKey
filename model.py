from faster_whisper import WhisperModel
import os
import sys

from error_dialog import show_error

class ModelLoadError(Exception):
    """モデル読み込みに失敗した時の例外"""
    pass

def load_model(model_size):
    print("faster-Whisper model load：start")
    try:
        #modelsフォルダのパスを作成
        this_file = os.path.abspath(__file__)
        project_root = os.path.dirname(this_file)
        models_dir = os.path.join(project_root, "models")

        if not os.path.exists(models_dir):
            print("not found 'models'dir")
            os.makedirs(models_dir)
            print("maked 'models'dir")

        # 自動判定（CUDAあれば使う、なければCPU）
        model = WhisperModel(model_size, 
                        device="auto",
                        compute_type="float16",
                        download_root=models_dir) 

        # GPUの有無を確認 "cuda" or "cpu"
        print(f"faster-Whisper model load：device={model.model.device}") 
        print(f"faster-Whisper model load：success! modelname={model_size}")

        return model
    
    except Exception as e:
        show_error("モデル読み込みエラー", 
                   "faster-Whisperモデルの読み込みに失敗したためソフトを終了します\n\n"
                   "以下のいずれかが原因の可能性があります:\n"
                   "・config.jsonの'model_size'の値が不正\n"
                   "・インターネット接続の問題\n"
                   "・'models/'フォルダの破損")
        print(f"error: {e}")
        sys.exit(1)


