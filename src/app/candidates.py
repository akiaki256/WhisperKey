"""
「候補を出す」の候補(GPU版の入力補正と一緒に使う)

最後に入力した文と、その候補の並びを持っておき、選ばれた候補に入れ替える。窓は candidate_window.py。
候補の並び(IME の次候補のつもり):
  1. 今の入力
  2. 同音異義語の確かめで確かめた場所を、一か所か二か所変えた文(確率が高い順。homophone.take_alternatives)
  3. 補正する前の文(音声辞書を通したあと、LLM の補正の前。今の入力と違うときだけ)
  句読点補正が動いたときは、2・3 の句読点も今の入力とそろえてある(transcribe.py)

- set_last(text, before_correction, alternatives): 入力したあとに呼ぶ
- forget(): 取り消し・音声実行のあとに呼ぶ(もう入れ替えられないので)
- get(): (候補の並び, 今の入力の番号, 版)。候補は {"text", "spans": [(始め, 長さ)], "note"}
    spans は最初の入力と違うところ(窓で背景色をつける)。版は候補が新しくなるたびに増える
- choose(i, 版): i 番目の候補に入れ替える(Backspace で今の入力を消して、貼り付ける)。入力履歴の一番新しいものも書き換える
    開発中だけ、入れ替えたら _local/dev_logs/candidate_choices.jsonl に一行ずつ記録する(exe化後は残さない)
    {"time", "input": 最初に入力した文, "from": 入れ替える前の文, "to": 選んだ文, "note": 選んだ候補の印(確率・補正前),
     "changes": [[前の言葉, 選んだ言葉], ...], "candidates": [[文, 印], ...]}
    窓を開いたあとに次の入力が来ていたら(版が違えば)、見ていた並びと違うので入れ替えない
    取り消しのキーと同じく、入力のあとにカーソルを動かしていると、違うところが消える
"""

import difflib
import json
import os
import threading
from datetime import datetime

import keyboard

import history
import paste
import undo_input
from paths import CANDIDATE_LOG_JSONL

MAX_ITEMS = 30   # 窓に並べる文の数の上限(今の入力も入れて)

_lock = threading.Lock()
_items = []      # 候補の並び。0 番目が最初に入力した文
_current = 0     # 今、入力されている候補の番号
_version = 0     # 候補が新しくなるたびに増やす(窓を開いたあとに次の入力が来たら、古い並びで入れ替えないため)


def _spans(base, text):
    """text のうち、base と違うところ [(始め, 長さ)]"""
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=base, b=text, autojunk=False).get_opcodes():
        if op in ("replace", "insert") and j2 > j1:
            out.append((j1, j2 - j1))
    return out


def set_last(text, before_correction, alternatives):
    """text: 入力した文。before_correction: LLM の補正の前の文
    alternatives: 一か所か二か所変えた文と確率 [(文, 確率), ...](homophone.take_alternatives() から)
    違うところは text と比べて出し直す(句読点補正や「。」を消す仕上げで、位置がずれるため)"""
    global _items, _current
    items = [{"text": text, "spans": [], "note": ""}]
    seen = {text}
    for alt, p in alternatives:
        if alt not in seen:
            seen.add(alt)
            items.append({"text": alt, "spans": _spans(text, alt), "note": f"{p:.0%}"})
    if before_correction and before_correction not in seen:
        items.append({"text": before_correction, "spans": _spans(text, before_correction), "note": "補正前"})
    items = items[:MAX_ITEMS]
    global _version
    with _lock:
        _items, _current = items, 0
        _version += 1


def forget():
    global _items, _current, _version
    with _lock:
        _items, _current = [], 0
        _version += 1


def get():
    """(候補の並び, 今の入力の番号, 版)。版は choose に渡す"""
    with _lock:
        return [dict(i) for i in _items], _current, _version


def choose(index, version):
    """index 番目の候補に入れ替える。同じ候補なら何もしない
    version: 窓を開いたときの版。そのあと次の入力が来ていたら(版が違えば)、見ていた並びと違うので入れ替えない"""
    global _current
    with _lock:
        if version != _version:
            print("候補を出す: 窓を開いたあとに次の入力があったので、入れ替えませんでした")
            return
        if not (0 <= index < len(_items)) or index == _current:
            return
        old, new = _items[_current]["text"], _items[index]["text"]
        record = {"input": _items[0]["text"], "from": old, "to": new, "note": _items[index]["note"],
                  "candidates": [[i["text"], i["note"]] for i in _items]}
        _current = index
    undo_input.wait_for_modifiers_released()   # Enter などを押したまま Backspace を送ると組み合わさるため
    for _ in range(len(old)):
        keyboard.send("backspace")
    paste.paste(new)
    undo_input.remember(new)          # 取り消しのキーで、入れ替えたあとの文を消せるように
    history.replace_latest(old, new)  # 直前の入力として LLM に渡るのが、選んだ文になるように
    print(f"候補を出す: {old} → {new}")
    _log_choice(record)


def _changes(old, new):
    """old と new で入れ替わったところ [[前の言葉, あとの言葉], ...]"""
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes():
        if op != "equal":
            out.append([old[i1:i2], new[j1:j2]])
    return out


def _log_choice(record):
    """入れ替えた記録を一行足す(開発中だけ)。失敗しても入力は止めない"""
    if not CANDIDATE_LOG_JSONL:
        return
    record = {"time": datetime.now().isoformat(timespec="seconds"), **record,
              "changes": _changes(record["from"], record["to"])}
    try:
        os.makedirs(os.path.dirname(CANDIDATE_LOG_JSONL), exist_ok=True)
        with open(CANDIDATE_LOG_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as e:
        print(f"候補を出す: 入れ替えの記録を残せませんでした: {e}")
