import json
import sys

from error_dialog import show_error


# DEFAULT_SETTING={
#     "volume_threshold": 1700,
#     "silence_duration": 1.3,
#     "shortcut_key": "f9",
#     "language": "ja",
#     "model_size": "small"
# }

def load_config():  # config.jsonの読み込み
    try:
        with open('config.json', 'r', encoding='utf-8') as config:
            print("ユーザー設定の読込：完了")
            return json.load(config)
        
    except FileNotFoundError as e:
        show_error("設定ファイルエラー", "'config.json'が見つかりません\nソフトを終了します")
        print(f"error: {e}")
        sys.exit(1)
    
    except json.JSONDecodeError as e:
        show_error("設定ファイルエラー", f"'config.json'の書式が不正です\nソフトを終了します")
        print(f"error: {e}")
        sys.exit(1)
