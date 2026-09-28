"""
パスの集約モジュール
本体の各係から参照する。ファイルの場所はすべてここで決める。

- APP_DIR: ユーザーが書き換えるファイル(設定・辞書・モデル・一時ファイル)の置き場所
    exe化後: exeと同じフォルダ(インストール先)
    開発中: _local/dev_data
- ASSETS_DIR: exeに同梱する素材(アイコン)の置き場所
    exe化後: PyInstallerの展開先(sys._MEIPASS)/assets
    開発中: プロジェクト直下の assets
- UI_DIR: 本体のウィンドウの画面(HTML/CSS/JS)の置き場所
    exe化後: PyInstallerの展開先(sys._MEIPASS)/ui
    開発中: src/ui
- SOUNDS_DIR: 効果音(wav)の置き場所。利用者が wav を足せるように、exe に同梱したものではなく
  インストール先の assets を見る(ビルドとインストーラーが assets をインストール先にも置いている)
    exe化後: exeと同じフォルダ/assets/sounds
    開発中: プロジェクト直下の assets/sounds
- CUDA_DIRS: GPU版が使う NVIDIA の DLL(cuBLAS・cuDNN)の置き場所。exe に入れると起動のたびに
  一時フォルダへ展開されて遅く、LLM 補正の llama-server とも共有できないので、exe の外に置く
    exe化後: exeと同じフォルダ/cuda
    開発中: 仮想環境の nvidia パッケージ(cublas/bin・cudnn/bin)
- LLAMA_SERVER_EXE: 入力補正(GPU版)で裏で動かす llama.cpp の llama-server
    exe化後: exeと同じフォルダ/llama-server/llama-server.exe
    開発中: _local/vendor/llama-server/<版>/llama-server.exe(版は build.bat の LLAMA_VER と合わせる)
"""

import os
import sys

FROZEN = getattr(sys, "frozen", False)

# プロジェクトのルート(開発中のみ意味を持つ)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

if FROZEN:
    APP_DIR = os.path.dirname(sys.executable)
    ASSETS_DIR = os.path.join(sys._MEIPASS, "assets")
    UI_DIR = os.path.join(sys._MEIPASS, "ui")
    SOUNDS_DIR = os.path.join(APP_DIR, "assets", "sounds")
    CUDA_DIRS = [os.path.join(APP_DIR, "cuda")]
    LLAMA_SERVER_EXE = os.path.join(APP_DIR, "llama-server", "llama-server.exe")
else:
    APP_DIR = os.path.join(PROJECT_ROOT, "_local", "dev_data")
    ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
    UI_DIR = os.path.join(PROJECT_ROOT, "src", "ui")
    SOUNDS_DIR = os.path.join(PROJECT_ROOT, "assets", "sounds")
    _nvidia = os.path.join(sys.prefix, "Lib", "site-packages", "nvidia")
    CUDA_DIRS = [os.path.join(_nvidia, "cublas", "bin"), os.path.join(_nvidia, "cudnn", "bin")]
    LLAMA_SERVER_EXE = os.path.join(PROJECT_ROOT, "_local", "vendor", "llama-server", "b11216", "llama-server.exe")

# ユーザーデータ
CONFIG_JSON = os.path.join(APP_DIR, "config.json")
CONVERT_DICT_CSV = os.path.join(APP_DIR, "convert_dict.csv")
COMMAND_DICT_CSV = os.path.join(APP_DIR, "command_dict.csv")
MODELS_DIR = os.path.join(APP_DIR, "models")
TEMP_DIR = os.path.join(APP_DIR, "temp")
HISTORY_JSON = os.path.join(APP_DIR, "history.json")

# 配布フォルダ内の実行ファイル(exe化後のみ使用)
RESTART_BAT = os.path.join(APP_DIR, "restart.bat")


def asset(name):
    """同梱素材のパスを返す"""
    return os.path.join(ASSETS_DIR, name)
