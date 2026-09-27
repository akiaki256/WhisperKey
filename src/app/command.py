"""
音声実行(command_dict.csv)

ファイルは「keyword,tag,path」の一行一組(今の設定画面や、購入者が持っている CSV がそのまま使える)。
話した言葉がキーワードと完全に一致したら、入力する代わりに path を開く。
判定は音声辞書で置き換えたあとの言葉で行う(transcribe.py)ので、言い方の揺れは辞書で吸収できる。

- load_command_dict(): 起動時に読んで「今のコマンド」にする。ファイルが無ければ空
- get_current(): 今のコマンド {キーワード: {"tag": 種類, "path": 開くもの}}。毎回ここを見るので、保存した瞬間から効く
- get_rows() / save_rows(): 画面との受け渡し。[{"keyword", "tag", "path"}, ...]
"""

import csv
import webbrowser
import os

from config_store import COMMAND_TYPES
from error_dialog import show_error
from paths import COMMAND_DICT_CSV

_TAGS = [tag for tag, _ in COMMAND_TYPES]
_current = {}


# CSVファイルから辞書を作成する
def load_command_dict():
    global _current
    try:
        commands = {}
        if os.path.exists(COMMAND_DICT_CSV):
            with open(COMMAND_DICT_CSV, encoding='UTF-8', newline='') as f:
                for row in csv.DictReader(f):
                    if row.get('keyword'):
                        commands[row['keyword']] = {'tag': row['tag'], 'path': row['path']}
        _current = commands
        return _current

    except Exception as e:
        show_error("設定ファイルエラー", f"'command_dict.csv'を読み込めませんでした\nコマンド実行機能を無効にします\nerror: {e}")
        print(f"error: {e}")


def get_current():
    return _current


def get_rows():
    return [{"keyword": keyword, "tag": data["tag"], "path": data["path"]} for keyword, data in _current.items()]


def save_rows(rows):
    """画面の一覧を保存し、今のコマンドを差し替える
    キーワードか開くものが空の行は、入力の途中とみなして保存しない
    同じキーワードが2つあったら ValueError(どちらを開けばいいか決められないため)"""
    global _current
    commands = {}
    for row in rows:
        keyword, tag, path = row["keyword"], row["tag"], row["path"]
        if keyword == "" or path == "":
            continue
        if keyword in commands:
            raise ValueError(f"キーワード「{keyword}」が2つあります。どちらか一方にしてください")
        commands[keyword] = {"tag": tag if tag in _TAGS else "url", "path": path}

    # 一時ファイルに書いてから差し替える(途中で落ちてもファイルが壊れない)
    tmp_path = COMMAND_DICT_CSV + ".tmp"
    with open(tmp_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["keyword", "tag", "path"])
        writer.writeheader()
        for keyword, data in commands.items():
            writer.writerow({"keyword": keyword, "tag": data["tag"], "path": data["path"]})
    os.replace(tmp_path, COMMAND_DICT_CSV)
    _current = commands


def execute_command(original_text, command_dict):
    # 文章全体の前後の空白だけ除去して比較(Whisperの出力癖への対策)
    cleaned_text = original_text.strip()
    for keyword, data in command_dict.items():
        if keyword == cleaned_text:

            if data['tag'] == 'url':
                webbrowser.open(data['path'])
                print(f"URL開く: {keyword} → {data['path']}")

            elif data['tag'] == 'file':
                os.startfile(data['path'])
                print(f"ファイルを開く: {keyword} → {data['path']}")

            return True
    print(f"コマンド該当なし: {original_text}")
    return False
