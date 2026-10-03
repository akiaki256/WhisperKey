"""
入力補正の「よく使う言葉」(llm_vocab.csv)
同音異義語の確かめ(homophone.py)と、Whisper に渡すヒント(transcribe.py)で使う。
読みはカタカナで持つ(ひらがなで入れても、保存するときにカタカナにする)。読みが同じ言葉は二つ登録できない。

ファイルは「word,reading」の一行一組(言葉, 読み)。読みは全部手で入れてもらう。
読みが空の言葉は使わない(画面では枠を赤くして知らせる)。

- load(): 起動時に読む。ファイルが無ければ空。ひらがなの読みも、ここでカタカナにする
- get_rows() / save_rows(): 画面との受け渡し。[{"word": 言葉, "reading": 読み}, ...]
    save_rows は、読みが同じ言葉があれば DuplicateReading を出して保存しない
- get_current(): 使う分 [(読み, 言葉), ...]。文字起こしの係が毎回ここを見るので、保存した瞬間から効く
- import_from_dict(afters): 音声辞書の変換後のうち、前回取り込んだあとに増えたものだけを足す(読みは空)
    取り込んだ変換後は llm_vocab_imported.json に覚えておく。一覧から × で消した言葉を、次に押したときに拾い直さないため
    文字(ひらがな・カタカナ・漢字・英数字)を含まない変換後(空白、#、♡ など)は取り込まない
    (「しゃーぷ → #」を渡すと、「シャープな」まで # にされるおそれがあるため)
"""

import csv
import json
import os
import re
import unicodedata

from paths import LLM_VOCAB_CSV, LLM_VOCAB_IMPORTED_JSON

_rows = []

# 文字として数えるもの: 英数字(全角も)、ひらがな、カタカナ、漢字
_HAS_LETTER = re.compile(r"[0-9A-Za-z０-９Ａ-Ｚａ-ｚ぀-ヿ㐀-䶿一-鿿]")


class DuplicateReading(ValueError):
    """読みが同じ言葉が二つ以上ある。args[0] は [(読み, [言葉…]), ...]"""


def to_katakana(reading):
    """読みをカタカナにそろえる(ひらがな → カタカナ、全角半角をそろえる、前後の空白を取る)"""
    s = unicodedata.normalize("NFKC", reading or "").strip()
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)


def load():
    global _rows
    try:
        with open(LLM_VOCAB_CSV, encoding="utf-8", newline="") as f:
            _rows = [{"word": row.get("word") or "", "reading": to_katakana(row.get("reading"))}
                     for row in csv.DictReader(f) if row.get("word")]
    except FileNotFoundError:
        _rows = []
    except Exception as e:
        print(f"よく使う言葉の読み込みに失敗(空から始めます): {e}")
        _rows = []


def get_rows():
    return [dict(row) for row in _rows]


def get_current():
    return [(row["reading"], row["word"]) for row in _rows if row["reading"]]


def _write_atomic(path, write):
    # 一時ファイルに書いてから差し替える(途中で落ちても壊れない)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="") as f:
        write(f)
    os.replace(tmp_path, path)


def save_rows(rows):
    """画面の一覧をまるごと保存する。言葉が空の行は捨てる。読みはカタカナにする
    読みが同じ言葉があれば DuplicateReading(保存しない)。書き込みに失敗したら OSError"""
    global _rows
    clean = [{"word": row["word"].strip(), "reading": to_katakana(row["reading"])}
             for row in rows if row["word"].strip()]
    by_reading = {}
    for row in clean:
        if row["reading"]:
            by_reading.setdefault(row["reading"], []).append(row["word"])
    duplicates = [(r, words) for r, words in by_reading.items() if len(words) > 1]
    if duplicates:
        raise DuplicateReading(duplicates)

    def write(f):
        writer = csv.DictWriter(f, fieldnames=["word", "reading"])
        writer.writeheader()
        writer.writerows(clean)

    _write_atomic(LLM_VOCAB_CSV, write)
    _rows = clean


def _load_imported():
    try:
        with open(LLM_VOCAB_IMPORTED_JSON, encoding="utf-8") as f:
            data = json.load(f)
        return {w for w in data if isinstance(w, str)}
    except FileNotFoundError:
        return set()
    except Exception as e:
        print(f"取り込み済みの一覧の読み込みに失敗(空として続けます): {e}")
        return set()


def import_from_dict(afters):
    """増えた変換後を、読みを空にして一覧の先頭に足して保存する。足した数を返す。失敗したら OSError"""
    imported = _load_imported()
    existing = {row["word"] for row in _rows}
    new_words = []
    for after in afters:
        word = after.strip()
        if not _HAS_LETTER.search(word) or word in imported:
            continue
        imported.add(word)   # 一覧にもうあった言葉も、取り込み済みとして覚える
        if word not in existing and word not in new_words:
            new_words.append(word)

    if new_words:
        save_rows([{"word": w, "reading": ""} for w in new_words] + _rows)
    _write_atomic(LLM_VOCAB_IMPORTED_JSON,
                  lambda f: json.dump(sorted(imported), f, ensure_ascii=False, indent=2))
    return len(new_words)
