import keyboard
import winsound
import sys

from error_dialog import show_error

class MainStateManager():
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.state = "stop"
            cls._instance.on_state_change = None
        return cls._instance

    def get_state(self):
        return self.state

    def toggle_state(self):
        if self.state == "stop":
            self.state = "start"
            print("聞き取りモード：スタート")
            winsound.Beep(1200, 200) # Hz, ms
        else:
            self.state = "stop"
            print("聞き取りモード：ストップ")
            winsound.Beep(250, 200) # Hz, ms

        if self.on_state_change:
            self.on_state_change(self.state)

        return self.state

    # ホットキー初回登録(stateの切り替えを実行する処理を付与)
    def start_listener(self, shortcut_key):
        try:
            self.shortcut_key = shortcut_key
            keyboard.add_hotkey(shortcut_key, self.toggle_state)
            winsound.Beep(1200, 100)
            winsound.Beep(1600, 100)  # Hz, ms
        except Exception as e:
            show_error("ショートカットキー登録エラー", 
                       "ショートカットキーの読み込みに失敗したためソフトを終了します\n\n"
                       "以下のいずれかが原因の可能性があります:\n"
                       "・config.jsonの'shortcut_key'の値が不正\n"
                       "・keyboardライブラリの問題")
            print(f"error: {e}")
            sys.exit(1)


    # ホットキーを再登録する処理
    def reset_shortcut(self):
        keyboard.remove_hotkey(self.shortcut_key)
        keyboard.add_hotkey(self.shortcut_key, self.toggle_state)