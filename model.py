from faster_whisper import WhisperModel
import os

class ModelLoadError(Exception):
    """モデル読み込みに失敗した時の例外"""
    pass

def load_model(model_size):

    #modelsフォルダのパスを作成
    this_file = os.path.abspath(__file__)
    project_root = os.path.dirname(this_file)
    models_dir = os.path.join(project_root, "models")

    if not os.path.exists(models_dir):
        print("not found 'models'dir")
        os.makedirs(models_dir)
        print("maked 'models'dir")

    # 自動判定（CUDAあれば使う、なければCPU）
    try:
        model = WhisperModel(model_size, 
                        device="auto",
                        compute_type="float16",
                        download_root=models_dir
                        ) 
            
    except Exception as e:
        raise ModelLoadError(f"model lord errer: {e}") from e

    # GPUの有無を確認
    print(f"faster-Whisper model load：device={model.model.device}")  # "cuda" or "cpu"

    return model


