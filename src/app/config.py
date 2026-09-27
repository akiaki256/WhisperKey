"""
本体の「今の設定」(中身の読み書きは common/config_store.py)

- load_config(): 起動時に一度だけ呼ぶ。config.json を読んで「今の設定」にする
- get(key): 今の設定の値。録音・文字起こしのループは毎回ここを見に来るので、
  画面で変えた値が次の一回から効く
- update(changes): 一部の項目を変えて config.json に保存する。値は config_store が直す
  本体の中で config.json に書き込むときは、必ずここを通す
  (別々に書き込むと、片方の変更をもう片方が古い値で上書きしてしまうため)
"""

import sys
import threading

import config_store
from error_dialog import show_error

_current = None
_lock = threading.Lock()


def load_config():
    global _current
    try:
        _current = config_store.load()
        print("ユーザー設定の読込：完了")
        return dict(_current)

    except config_store.ConfigError as e:
        show_error("設定ファイルエラー", f"{e}\nソフトを終了します")
        print(f"error: {e}")
        sys.exit(1)


def get(key):
    return _current[key]


def get_all():
    return dict(_current)


def update(changes):
    """changes を今の設定に重ねて保存し、直したあとの設定を返す。保存に失敗したら OSError"""
    global _current
    with _lock:
        new = config_store.normalize({**_current, **changes})
        config_store.save(new)
        # 丸ごと差し替えるので、ほかのスレッドが途中の状態を見ることはない
        _current = new
        return dict(new)
