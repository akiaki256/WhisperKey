"""
パスの集約モジュール
本体・設定画面の両方から参照する。ファイルの場所はすべてここで決める。

- APP_DIR: ユーザーが書き換えるファイル(設定・辞書・モデル・一時ファイル)の置き場所
    exe化後: exeと同じフォルダ(インストール先)
    開発中: _local/dev_data
- ASSETS_DIR: exeに同梱する素材(アイコン)の置き場所
    exe化後: PyInstallerの展開先(sys._MEIPASS)/assets
    開発中: プロジェクト直下の assets
- UI_DIR: 本体のウィンドウの画面(HTML/CSS/JS)の置き場所
    exe化後: PyInstallerの展開先(sys._MEIPASS)/ui
    開発中: src/ui
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
else:
    APP_DIR = os.path.join(PROJECT_ROOT, "_local", "dev_data")
    ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
    UI_DIR = os.path.join(PROJECT_ROOT, "src", "ui")

# ユーザーデータ
CONFIG_JSON = os.path.join(APP_DIR, "config.json")
CONVERT_DICT_CSV = os.path.join(APP_DIR, "convert_dict.csv")
COMMAND_DICT_CSV = os.path.join(APP_DIR, "command_dict.csv")
MODELS_DIR = os.path.join(APP_DIR, "models")
TEMP_DIR = os.path.join(APP_DIR, "temp")

# 配布フォルダ内の実行ファイル(exe化後のみ使用)
RESTART_BAT = os.path.join(APP_DIR, "restart.bat")
CONFIG_EXE = os.path.join(APP_DIR, "Config.exe")

# 開発中に設定画面を起動するスクリプト
CONFIG_SCRIPT = os.path.join(PROJECT_ROOT, "src", "config_app", "main_config.py")


def asset(name):
    """同梱素材のパスを返す"""
    return os.path.join(ASSETS_DIR, name)
