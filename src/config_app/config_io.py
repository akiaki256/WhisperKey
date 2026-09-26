"""
config.json の読み書き(設定画面用)
中身は common/config_store.py に任せ、ここではエラーの表示だけを行う。
"""

import sys
from CTkMessagebox import CTkMessagebox

import config_store


def load_config():
    """
    config.json を読み込み、おかしな値を直して返す。
    ファイルが無ければ初期値で作られる。書式不正は致命エラーでアプリ終了。
    """
    try:
        return config_store.load()
    except config_store.ConfigError as e:
        CTkMessagebox(
            title="設定ファイルエラー",
            message=f"{e}\n終了します。",
            icon="cancel",
            option_1="OK",
        )
        sys.exit(1)


def save_config(config):
    """
    config.json に書き込み。
    書き込み失敗時は例外を投げる(呼び出し側で処理)。
    """
    config_store.save(config)
