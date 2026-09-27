"""
録音中インジケーター(常に最前面の小さな丸)

表示:
- 文字起こしが残っている → 黄色(録音のオン/オフに関わらず)
- 録音オン             → 緑
- 録音オフ             → 消える

tkinter はこの窓を作ったスレッドからしか触らない。
ほかのスレッドから呼ばれるのではなく、この窓が 0.1 秒ごとに状態を見に行く。
"""

import tkinter as tk
from key_shortcut import MainStateManager

state_manager = MainStateManager()

GREEN = "lime"
YELLOW = "yellow"
POLL_MS = 100

class IndicatorWindow:

    # 常に最前面に表示される小さなウィンドウ
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # タイトルバーなし
        self.root.attributes('-topmost', True)  # 常に最前面
        self.root.attributes('-transparentcolor', 'black')  # 背景透明化
        self.root.geometry('30x30+5+20')  # サイズ30x30、左上に配置
        self.root.config(bg='black') # ウィンドウ背景を黒に

        ## ラベル作成・配置
        self.indicator_label = tk.Label(
            self.root,
            text="●",
            fg=GREEN,
            bg="black",
            font=("Arial", 40)
            )
        self.indicator_label.pack()

        ## 最初は非表示
        self.root.withdraw()
        self.visible = False

        self.root.after(POLL_MS, self.update_indicator)

    def update_indicator(self):
        recording = state_manager.get_state() == "start"
        transcribing = state_manager.is_transcribing()

        if recording or transcribing:
            self.indicator_label.config(fg=YELLOW if transcribing else GREEN)
            if not self.visible:
                self.root.deiconify()
                self.visible = True
        elif self.visible:
            self.root.withdraw()
            self.visible = False

        self.root.after(POLL_MS, self.update_indicator)

    def run(self):
        self.root.mainloop()
