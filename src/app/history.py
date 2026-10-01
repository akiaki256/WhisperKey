"""
入力履歴(history.json)

- 残すのは、実際に入力(貼り付け)した文章だけ。音声実行は残さない
- 残すかどうか(history_enabled)は config が持つ
  スイッチがオフのあいだは新しい入力を足さないだけで、今ある履歴には触らない
- 新しいものが先頭。LIMIT 件を超えた古いものは消える
  (件数は選べない。入力補正が直前の入力を履歴から取るので、決まった数にしておく)
- add_listener(fn): 履歴が変わったら fn(今の履歴) を呼んでもらう(画面の一覧を更新するため)
- replace_latest(old, new): 「候補を出す」で別の候補を選んだとき、一番新しい入力を書き換える

中身: [{"time": "2026-09-27T21:30:05", "text": "入力した文章"}, ...]
    入力補正で直したときは、直す前の文も "raw" に残す(画面には出さない。LLM が変に直したときに見比べるため)
"""

import json
import os
import threading
from datetime import datetime

import config
from paths import HISTORY_JSON

LIMIT = 20

_entries = []
_lock = threading.Lock()
_listeners = []


def load():
    """起動時に読む。読めなければ空から始める(履歴が無くても動作には困らない)"""
    global _entries
    try:
        with open(HISTORY_JSON, encoding="utf-8") as f:
            data = json.load(f)
        # 件数を選べたころ(30 件まで)の履歴も、LIMIT 件にそろえる(ファイルは次に足したときに書き直される)
        _entries = [e for e in data if isinstance(e, dict) and isinstance(e.get("text"), str)][:LIMIT]
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


def add(text, raw=None):
    """入力した文章を先頭に足す。スイッチがオフなら何もしない
    raw: 入力補正で直す前の文(直していなければ None)"""
    global _entries
    if not config.get("history_enabled"):
        return
    entry = {"time": datetime.now().isoformat(timespec="seconds"), "text": text}
    if raw is not None and raw != text:
        entry["raw"] = raw
    with _lock:
        _entries = [entry] + _entries[:LIMIT - 1]
        try:
            _save()
        except OSError as e:
            print(f"入力履歴の保存に失敗: {e}")
    _notify()


def replace_latest(old_text, new_text):
    """一番新しい入力が old_text なら、new_text に書き換える(「候補を出す」で別の候補を選んだとき)
    直前の入力として LLM に渡るのが、キミの選んだ文になるように。補正する前の文(raw)はそのまま残す"""
    with _lock:
        if not _entries or _entries[0].get("text") != old_text:
            return
        _entries[0] = dict(_entries[0], text=new_text)
        try:
            _save()
        except OSError as e:
            print(f"入力履歴の保存に失敗: {e}")
    _notify()


def clear():
    """全部消す。ファイルごと消す"""
    global _entries
    with _lock:
        _entries = []
        if os.path.exists(HISTORY_JSON):
            os.remove(HISTORY_JSON)
    _notify()
