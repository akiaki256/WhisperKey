import sys

import config_store
from error_dialog import show_error


def load_config():  # config.jsonの読み込み(中身は common/config_store.py)
    try:
        config = config_store.load()
        print("ユーザー設定の読込：完了")
        return config

    except config_store.ConfigError as e:
        show_error("設定ファイルエラー", f"{e}\nソフトを終了します")
        print(f"error: {e}")
        sys.exit(1)
