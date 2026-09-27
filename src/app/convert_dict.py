"""
音声辞書(convert_dict.csv)

ファイルは今までどおり「before,after」の一行一組(今の設定画面や、購入者が持っている CSV がそのまま使える)。
画面では、変換後が同じ行を一つの項目にまとめて見せる(多対一)。保存するときに一行一組にばらす。

- load_convert_dict(): 起動時に読んで「今の辞書」にする。ファイルが無ければ空の辞書
- get_current(): 今の辞書 {変換前: 変換後}。文字起こしの係が毎回ここを見るので、保存した瞬間から効く
- get_groups() / save_groups(): 画面との受け渡し。[{"after": 変換後, "befores": [変換前, ...]}, ...]

変換前・変換後の文字は、前後の空白も含めてそのまま扱う
(変換後が半角スペース1文字や空のこともある。空は聞き間違いを消す用)
"""

import csv
import os

from error_dialog import show_error
from paths import CONVERT_DICT_CSV

_current = {}


def _read_rows():
    """[(変換前, 変換後), ...]。ファイルが無ければ空。変換前が空の行は飛ばす"""
    if not os.path.exists(CONVERT_DICT_CSV):
        return []
    with open(CONVERT_DICT_CSV, encoding='UTF-8', newline='') as f:
        reader = csv.DictReader(f)
        return [(row['before'], row['after'] or '') for row in reader if row.get('before')]


# CSVファイルから辞書を作成する
def load_convert_dict():
    global _current
    try:
        _current = dict(_read_rows())
        return _current
    except Exception as e:
        show_error("設定ファイルエラー", f"'convert_dict.csv'を読み込めませんでした。\n辞書変換機能を無効にします。\nerror: {e}")
        print(f"error: {e}")


def get_current():
    return _current


def get_groups():
    """変換後が同じものをまとめる。並びは、最初に出てきた順"""
    groups = {}
    for before, after in _current.items():
        groups.setdefault(after, []).append(before)
    return [{"after": after, "befores": befores} for after, befores in groups.items()]


def save_groups(groups):
    """画面の項目を一行一組にばらして保存し、今の辞書を差し替える
    同じ変換前が別の変換後に入っていたら ValueError(どちらに変えればいいか決められないため)"""
    global _current
    rows = {}
    for group in groups:
        after = group["after"]
        for before in group["befores"]:
            if before == "":
                continue
            if before in rows and rows[before] != after:
                raise ValueError(f"「{before}」が2つの項目に入っています。どちらか一方にしてください")
            rows[before] = after

    # 一時ファイルに書いてから差し替える(途中で落ちても辞書が壊れない)
    tmp_path = CONVERT_DICT_CSV + ".tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["before", "after"])
        writer.writeheader()
        for before, after in rows.items():
            writer.writerow({"before": before, "after": after})
    os.replace(tmp_path, CONVERT_DICT_CSV)
    _current = rows


def convert_text(text, convert_dict):
    # 長い順にソートして置換（短い語が先にマッチするのを防ぐ）
    sorted_items = sorted(convert_dict.items(), key=lambda x: len(x[0]), reverse=True)
    for before, after in sorted_items:
        if before in text:
            text = text.replace(before, after)
            print(f"変換: '{before}' → '{after}'")
    return text
