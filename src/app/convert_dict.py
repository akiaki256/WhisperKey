import csv

from error_dialog import show_error
from paths import CONVERT_DICT_CSV

# CSVファイルから辞書を作成する
def load_convert_dict():
    try:
        with open(CONVERT_DICT_CSV, encoding='UTF-8') as f:
            reader = csv.DictReader(f)
            return {row['before']: row['after'] for row in reader}
    except FileNotFoundError as e:
        show_error("設定ファイルエラー", f"'convert_dict.csv'が見つかりません。\n辞書変換機能を無効にします。\nerror: {e}")
        print(f"error: {e}")

def convert_text(text, convert_dict):
    # 長い順にソートして置換（短い語が先にマッチするのを防ぐ）
    sorted_items = sorted(convert_dict.items(), key=lambda x: len(x[0]), reverse=True)
    for before, after in sorted_items:
        if before in text:
            text = text.replace(before, after)
            print(f"変換: '{before}' → '{after}'")
    return text