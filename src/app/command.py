import csv
import webbrowser
import os

from error_dialog import show_error
from paths import COMMAND_DICT_CSV

# CSVファイルから辞書を作成する
def load_command_dict():
    try:
        with open(COMMAND_DICT_CSV, encoding='UTF-8') as f:
            reader = csv.DictReader(f)
            return {row['keyword']: {'tag': row['tag'], 'path': row['path']} for row in reader}
        
    except FileNotFoundError as e:
        show_error("設定ファイルエラー", f"'command_dict.csv'が見つかりません\nコマンド実行機能を無効にします\nerror: {e}")
        print(f"error: {e}")

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