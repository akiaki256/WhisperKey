"""
モデルの置き場所と取得

Whisper だけでなく、あとから足すモデル(kotoba-whisper、ローカル LLM など)も同じ仕組みで扱う。
モデルを足すときは MODELS に一行足す。

- MODELS: モデルの一覧 {モデルの名前: Hugging Face の場所・取ってくるファイル・大きさの目安}
- local_path(name): 手元にあれば、そのフォルダ。無ければ None。**ネットには出ない**
- download(name, on_progress): Hugging Face から取ってくる。on_progress(0.0〜1.0) で進み具合を知らせる

しまい方は Hugging Face の形(models/models--Systran--faster-whisper-medium/snapshots/...)。
v4.4 までの faster-whisper が自分でしまっていた形と同じなので、手元にあるモデルはそのまま使える。
"""

import fnmatch
import os
import threading

# 本体では main.py の一番最初で決めている(Hugging Face のライブラリが読み込まれる前でないと効かないため)。
# このモジュールだけを使うとき(テストなど)のために、ここでも決めておく
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

import huggingface_hub

from paths import MODELS_DIR

# faster-whisper(CTranslate2 形式の Whisper)が使うファイル(faster_whisper.utils.download_model と同じ)
WHISPER_FILES = ["config.json", "preprocessor_config.json", "model.bin", "tokenizer.json", "vocabulary.*"]

MODELS = {
    "tiny": {"repo": "Systran/faster-whisper-tiny", "files": WHISPER_FILES, "size": "約 75 MB"},
    "base": {"repo": "Systran/faster-whisper-base", "files": WHISPER_FILES, "size": "約 145 MB"},
    "small": {"repo": "Systran/faster-whisper-small", "files": WHISPER_FILES, "size": "約 480 MB"},
    "medium": {"repo": "Systran/faster-whisper-medium", "files": WHISPER_FILES, "size": "約 1.5 GB"},
    "large-v3": {"repo": "Systran/faster-whisper-large-v3", "files": WHISPER_FILES, "size": "約 3.1 GB"},
}

# 手元にそろっていると言えるファイル(これが無ければ「無い」とみなす)
_REQUIRED = ["config.json", "model.bin"]

_POLL_SECONDS = 0.3


def _repo_dir(repo):
    """Hugging Face の形でしまったときの、そのモデルのフォルダ"""
    return os.path.join(MODELS_DIR, "models--" + repo.replace("/", "--"))


def local_path(name):
    """手元にあれば、そのフォルダ。無ければ None(ネットには出ない)"""
    info = MODELS.get(name)
    if info is None:
        return None
    try:
        path = huggingface_hub.snapshot_download(
            info["repo"], cache_dir=MODELS_DIR, allow_patterns=info["files"], local_files_only=True)
    except Exception:
        return None
    if all(os.path.exists(os.path.join(path, f)) for f in _REQUIRED):
        return path
    return None


def _folder_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass  # ダウンロード中に名前が変わったファイルは次の回で数える
    return total


def download(name, on_progress=None):
    """Hugging Face から取ってきて、そのフォルダを返す。失敗したら例外

    進み具合は、このモデルのフォルダの大きさを数えて、取ってくるファイルの合計と比べる
    (Hugging Face のダウンロードの仕組みに頼らず、どのモデルでも同じように数えられる)
    """
    info = MODELS[name]
    repo = info["repo"]

    total = 0
    if on_progress:
        siblings = huggingface_hub.HfApi().model_info(repo, files_metadata=True).siblings
        total = sum(s.size or 0 for s in siblings
                    if any(fnmatch.fnmatch(s.rfilename, pattern) for pattern in info["files"]))

    done = threading.Event()

    def watch():
        # 途中まで取ってあったぶん(やり直したとき)も、最初から数に入る
        while not done.wait(_POLL_SECONDS):
            if total:
                on_progress(min(_folder_size(_repo_dir(repo)) / total, 0.99))

    watcher = threading.Thread(target=watch, daemon=True) if on_progress else None
    if watcher:
        watcher.start()
    try:
        path = huggingface_hub.snapshot_download(repo, cache_dir=MODELS_DIR, allow_patterns=info["files"])
    finally:
        done.set()
    if on_progress:
        on_progress(1.0)
    return path
