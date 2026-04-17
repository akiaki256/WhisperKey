import keyboard
import winsound

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
        self.shortcut_key = shortcut_key
        keyboard.add_hotkey(shortcut_key, self.toggle_state)
        winsound.Beep(1200, 100)
        winsound.Beep(1600, 100)  # Hz, ms


    # ホットキーを再登録する処理
    def reset_shortcut(self):
        keyboard.remove_hotkey(self.shortcut_key)
        keyboard.add_hotkey(self.shortcut_key, self.toggle_state)