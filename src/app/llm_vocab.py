"""
入力補正の「よく使う言葉」(llm_vocab.csv)
LLM に「よみがな → 言葉」の矢印の形で渡す(読みを書き写さずに正しく直せる。実験の「読み矢印」)。

ファイルは「word,reading」の一行一組(言葉, よみがな)。よみがなは全部手で入れてもらう。
よみがなが空の言葉は LLM に渡さない(画面では枠を赤くして知らせる)。

- load(): 起動時に読む。ファイルが無ければ空
- get_rows() / save_rows(): 画面との受け渡し。[{"word": 言葉, "reading": よみがな}, ...]
- get_current(): LLM に渡す分 [(よみがな, 言葉), ...]。文字起こしの係が毎回ここを見るので、保存した瞬間から効く
- import_from_dict(afters): 音声辞書の変換後のうち、前回取り込んだあとに増えたものだけを足す(よみがなは空)
    取り込んだ変換後は llm_vocab_imported.json に覚えておく。一覧から × で消した言葉を、次に押したときに拾い直さないため
    文字(ひらがな・カタカナ・漢字・英数字)を含まない変換後(空白、#、♡ など)は取り込まない
    (「しゃーぷ → #」を渡すと、「シャープな」まで # にされるおそれがあるため)
"""

import csv
import json
import os
import re

from paths import LLM_VOCAB_CSV, LLM_VOCAB_IMPORTED_JSON

_rows = []

# 文字として数えるもの: 英数字(全角も)、ひらがな、カタカナ、漢字
_HAS_LETTER = re.compile(r"[0-9A-Za-z０-９Ａ-Ｚａ-ｚ぀-ヿ㐀-䶿一-鿿]")


def load():
    global _rows
    try:
        with open(LLM_VOCAB_CSV, encoding="utf-8", newline="") as f:
            _rows = [{"word": row.get("word") or "", "reading": row.get("reading") or ""}
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
    """画面の一覧をまるごと保存する。言葉が空の行は捨てる。失敗したら OSError"""
    global _rows
    clean = [{"word": row["word"].strip(), "reading": row["reading"].strip()}
             for row in rows if row["word"].strip()]

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
    """増えた変換後を、よみがな空で一覧の先頭に足して保存する。足した数を返す。失敗したら OSError"""
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
