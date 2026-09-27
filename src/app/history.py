"""
入力履歴(history.json)

- 残すのは、実際に入力(貼り付け)した文章だけ。音声実行は残さない
- 残すかどうか(history_enabled)と件数(history_limit)は config が持つ
  スイッチがオフのあいだは新しい入力を足さないだけで、今ある履歴には触らない
- 新しいものが先頭。件数を超えた古いものは消える
- add_listener(fn): 履歴が変わったら fn(今の履歴) を呼んでもらう(画面の一覧を更新するため)

中身: [{"time": "2026-09-27T21:30:05", "text": "入力した文章"}, ...]
"""

import json
import os
import threading
from datetime import datetime

import config
from paths import HISTORY_JSON

_entries = []
_lock = threading.Lock()
_listeners = []


def load():
    """起動時に読む。読めなければ空から始める(履歴が無くても動作には困らない)"""
    global _entries
    try:
        with open(HISTORY_JSON, encoding="utf-8") as f:
            data = json.load(f)
        _entries = [e for e in data if isinstance(e, dict) and isinstance(e.get("text"), str)]
    except FileNotFoundError:
        _entries = []
    except Exception as e:
        print(f"入力履歴の読み込みに失敗(空から始めます): {e}")
        _entries = []


def get():
    return list(_entries)


def add_listener(fn):
    _listeners.append(fn)


def _save():
    # 一時ファイルに書いてから差し替える(途中で落ちても壊れない)
    tmp_path = HISTORY_JSON + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_entries, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, HISTORY_JSON)


def _notify():
    entries = get()
    for fn in _listeners:
        try:
            fn(entries)
        except Exception as e:
            print(f"入力履歴の通知でエラー: {e}")


def add(text):
    """入力した文章を先頭に足す。スイッチがオフなら何もしない"""
    global _entries
    if not config.get("history_enabled"):
        return
    entry = {"time": datetime.now().isoformat(timespec="seconds"), "text": text}
    with _lock:
        _entries = [entry] + _entries[:config.get("history_limit") - 1]
        try:
            _save()
        except OSError as e:
            print(f"入力履歴の保存に失敗: {e}")
    _notify()


def trim(limit):
    """件数を limit に減らす(件数の設定を下げたとき)。消した件数を返す"""
    global _entries
    with _lock:
        removed = len(_entries) - limit
        if removed <= 0:
            return 0
        _entries = _entries[:limit]
        _save()
    _notify()
    return removed


def clear():
    """全部消す。ファイルごと消す"""
    global _entries
    with _lock:
        _entries = []
        if os.path.exists(HISTORY_JSON):
            os.remove(HISTORY_JSON)
    _notify()
