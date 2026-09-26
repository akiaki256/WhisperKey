import tkinter as tk
from key_shortcut import MainStateManager

state_manager = MainStateManager()

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
            fg="lime", 
            bg="black",
            font=("Arial", 40)
            )
        self.indicator_label.pack()
    
        ## 最初は非表示
        self.root.withdraw()

        ## コールバック登録
        state_manager.on_state_change = self.update_indicator

    def update_indicator(self, status):
        # 色を変える時
        if status == "start":
            self.root.deiconify()
        elif status == "stop":
            self.root.withdraw()

    def run(self):
        self.root.mainloop()






