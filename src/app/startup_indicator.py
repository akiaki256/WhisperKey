"""
起動中インジケーター
画面左上に「起動中...」を表示する軽量なウィジェット。
重いimport(faster_whisper等)の前に表示し、準備完了時に閉じる。

依存は tkinter のみ(標準ライブラリ)なので、
main.pyの最序盤で import しても起動が遅くならない。
"""

import tkinter as tk


class StartupIndicator:
    """起動中を知らせる小さな常時前面ウィンドウ"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)       # タイトルバーなし
        self.root.attributes('-topmost', True) # 常に最前面
        
        # 位置とサイズ(左上に配置、テキストに合わせて自動調整されるよう小さめに初期化)
        self.root.geometry('+5+20')
        
        # 薄いグレー背景
        bg_color = "#e0e0e0"
        fg_color = "#333333"
        
        self.root.config(bg=bg_color)
        
        # ラベル
        self.label = tk.Label(
            self.root,
            text="起動中...",
            bg=bg_color,
            fg=fg_color,
            font=("Meiryo UI", 10),
            padx=10,
            pady=4,
        )
        self.label.pack()
        
        # update_idletasksで即座に描画(mainloopなしで表示される)
        self.root.update()
    
    def close(self):
        """インジケーターを閉じる"""
        try:
            self.root.destroy()
        except Exception:
            pass
