import csv
import webbrowser
import subprocess

# CSVファイルから辞書を作成する
def load_command_dict():
    with open('command_dict.csv', encoding='UTF-8') as f:
        reader = csv.DictReader(f)
        return {row['keyword']: {'tag': row['tag'], 'path': row['path']} for row in reader}

def execute_command(original_text, command_dict):
    for keyword, data in command_dict.items():
        if keyword in original_text:

            if data['tag'] == 'url':
                webbrowser.open(data['path'])
                print(f"URL開く: {keyword} → {data['path']}")

            elif data['tag'] == 'soft':
                subprocess.Popen(data['path'])
                print(f"ソフト起動: {keyword} → {data['path']}")

            return True
    print(f"コマンド該当なし: {original_text}")
    return False