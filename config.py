import json

def load_config():  # config.jsonの読み込み
    with open('config.json', 'r', encoding='utf-8') as config:
        return json.load(config)