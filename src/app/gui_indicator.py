"""
録音中インジケーター(常に最前面の小さな丸)

表示:
- 文字起こしが残っている → 黄色(録音のオン/オフに関わらず)
- 録音オン             → 緑
- 録音オフ             → 消える

操作:
- つまんで(ドラッグで)動かせる。離した位置を config.json に保存し、次の起動でもそこに出す
- 押してもフォーカスを奪わない(WS_EX_NOACTIVATE)。入力したいアプリにフォーカスが残るので、
  貼り付けの行き先がこの窓になってしまうことがない

tkinter はこの窓を作ったスレッドからしか触らない。
ほかのスレッドから呼ばれるのではなく、この窓が 0.1 秒ごとに状態を見に行く。
"""

import ctypes
from ctypes import wintypes
import tkinter as tk

import config
import config_store
from key_shortcut import MainStateManager

state_manager = MainStateManager()

GREEN = "lime"
YELLOW = "yellow"
POLL_MS = 100
SIZE = 30

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetParent.argtypes = [wintypes.HWND]
_user32.GetParent.restype = wintypes.HWND
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = ctypes.c_long
_user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
_user32.SetWindowLongW.restype = ctypes.c_long
_user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
_user32.MonitorFromPoint.restype = wintypes.HMONITOR

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
MONITOR_DEFAULTTONULL = 0


def _on_screen(x, y):
    """丸の中心がどこかのモニターの上にあるか(モニターを外したあとに、画面外に出ないように)"""
    center = wintypes.POINT(x + SIZE // 2, y + SIZE // 2)
    return bool(_user32.MonitorFromPoint(center, MONITOR_DEFAULTTONULL))


class IndicatorWindow:

    # 常に最前面に表示される小さなウィンドウ
    def __init__(self, x, y):
        if not _on_screen(x, y):
            d = config_store.defaults()
            x, y = d["indicator_x"], d["indicator_y"]

        self.root = tk.Tk()
        self.root.overrideredirect(True)  # タイトルバーなし
        self.root.attributes('-topmost', True)  # 常に最前面
        self.root.attributes('-transparentcolor', 'black')  # 背景透明化
        self.root.geometry(f'{SIZE}x{SIZE}+{x}+{y}')
        self.root.config(bg='black') # ウィンドウ背景を黒に

        ## ラベル作成・配置
        self.indicator_label = tk.Label(
            self.root,
            text="●",
            fg=GREEN,
            bg="black",
            font=("Arial", 40),
            cursor="fleur",  # つまめることがわかるカーソル
            )
        self.indicator_label.pack()

        ## 押してもフォーカスを奪わないようにする
        self.root.update_idletasks()
        hwnd = _user32.GetParent(self.root.winfo_id())
        style = _user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)

        ## つまんで動かす
        self.drag_offset = None
        self.indicator_label.bind("<ButtonPress-1>", self.on_press)
        self.indicator_label.bind("<B1-Motion>", self.on_drag)
        self.indicator_label.bind("<ButtonRelease-1>", self.on_release)

        ## 最初は非表示
        self.root.withdraw()
        self.visible = False

        self.root.after(POLL_MS, self.update_indicator)

    def on_press(self, event):
        self.drag_offset = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())
        self.start_pos = (self.root.winfo_x(), self.root.winfo_y())

    def on_drag(self, event):
        if self.drag_offset is None:
            return
        dx, dy = self.drag_offset
        self.root.geometry(f'+{event.x_root - dx}+{event.y_root - dy}')

    def on_release(self, event):
        if self.drag_offset is None:
            return
        self.drag_offset = None

        pos = (self.root.winfo_x(), self.root.winfo_y())
        if pos != self.start_pos:
            self.save_position(*pos)

    def save_position(self, x, y):
        try:
            config.update({"indicator_x": x, "indicator_y": y})
        except Exception as e:
            # 保存できなくても、今の起動中は動かした位置のまま使える
            print(f"インジケーターの位置の保存に失敗: {e}")

    def update_indicator(self):
        recording = state_manager.get_state() == "start"
        transcribing = state_manager.is_transcribing()

        if recording or transcribing:
            self.indicator_label.config(fg=YELLOW if transcribing else GREEN)
            if not self.visible:
                self.root.deiconify()
                self.visible = True
        elif self.visible and self.drag_offset is None:  # つまんでいる途中では消さない
            self.root.withdraw()
            self.visible = False

        self.root.after(POLL_MS, self.update_indicator)

    def run(self):
        self.root.mainloop()
