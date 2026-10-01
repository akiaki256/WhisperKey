"""
インジケーター(常に最前面の小さな窓)

表示方法(config の indicator_mode。0.1 秒ごとに見に行き、変わったら作り直す):
- dot(丸): いつも出ている。暗い丸の中にマイクのアイコン。クリックしても何も操作しない(つまんで動かすだけ)
    マイクの色: オフは灰色、録音中は緑、文字起こし中は黄色(操作パネルの録音ボタンと同じ)
    丸の枠: 通常は白、プッシュトゥトークのときは水色(操作パネルのプッシュトゥトークがオンのときの色)
- panel(操作パネル): いつも出ている。左から「つまむところ・録音・取り消し・プッシュトゥトーク」
    録音ボタン: 色で状態を見せる(オフは灰色、録音中は緑、文字起こし中は黄色)
                切り替えモードでは押すたびにオン/オフ。プッシュトゥトークでは押している間だけ録音
    取り消し:   直前の入力を取り消す(undo_input)。フォーカスを奪わないので、入力先のアプリに Backspace が届く
    プッシュトゥトーク: 押すたびにオン/オフ。オンのときはアクセント色
- hidden(表示しない)

共通:
- つまんで(ドラッグで)動かせる。丸は丸ごと、パネルは左端のつまむところ
  離した位置を config.json に保存し、次の起動でもそこに出す(丸とパネルで共通の位置)
- 設定の位置が変わったら(設定タブの「窓の位置を元に戻す」)、起動中でもそこへ動く
  モニターを外すなどして画面の外に出たら、初期位置に戻す(1 秒ごとに確かめる)
- 押してもフォーカスを奪わない(WS_EX_NOACTIVATE)。入力したいアプリにフォーカスが残るので、
  貼り付けの行き先がこの窓になってしまうことがない
- 丸のときは窓の背景の黒(#000000)を透明にして、丸の周りを抜く
  丸は Pillow で4倍の大きさで描いてから縮めた画像(ふちがなめらかになる)。丸の中に真っ黒は使わない
- パネルのときは透明をやめて、Windows 11 の DWM に角丸と白い枠を描いてもらう
  (透明にする設定があると角丸と枠が効かないため、表示方法ごとに切り替える)

tkinter はこの窓を作ったスレッドからしか触らない。
ほかのスレッドから呼ばれるのではなく、この窓が 0.1 秒ごとに状態を見に行く。
- 途中でエラーが起きても、次に見に行く予約は必ずする(一度のエラーで見張りが止まり、窓が固まらないように)
- 出ている間は 1 秒ごとに、最前面の一番上に置き直す。最前面の窓どうしの中でも、あとから前に出た窓が上になるので、
  タスクバー(これも最前面の窓)を押したり、ほかのアプリが最前面になったりすると、その下に潜り込んだままになるため
"""

import ctypes
from ctypes import wintypes
import threading
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

import candidates
import config
import config_store
import undo_input
from candidate_window import CandidateWindow
from key_shortcut import MainStateManager

state_manager = MainStateManager()

POLL_MS = 100
RAISE_EVERY = 10   # 最前面の一番上に置き直す間隔(POLL_MS の何回に一回か。1 秒)

# 状態の色(丸のマイクと、操作パネルの録音ボタンで共通)
GREEN = "lime"
YELLOW = "yellow"

# 丸
SIZE = 36          # 直径(ピクセル)
DOT_BORDER = 2     # 枠の太さ(ピクセル)
DOT_ICON_FONT = ("Segoe Fluent Icons", 13)

# 操作パネル(どのアプリの上でも見分けやすいよう、暗い色で固定)
PANEL_BG = "#202020"
PANEL_HOVER = "#333333"
ICON = "#ffffff"
ICON_DIM = "#9a9a9a"
ACCENT = "#60cdff"
ICON_FONT = ("Segoe Fluent Icons", 14)   # 本体の窓と同じ、Windows に入っているアイコンのフォント
GLYPH_GRIP = ""   # つまむところ
GLYPH_MIC = ""    # 録音
GLYPH_UNDO = ""   # 取り消し
GLYPH_PTT = ""    # プッシュトゥトーク(人差し指を立てた手)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetParent.argtypes = [wintypes.HWND]
_user32.GetParent.restype = wintypes.HWND
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = ctypes.c_long
_user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
_user32.SetWindowLongW.restype = ctypes.c_long
_user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
_user32.MonitorFromPoint.restype = wintypes.HMONITOR
_user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                 ctypes.c_int, ctypes.c_int, wintypes.UINT]
_user32.SetWindowPos.restype = wintypes.BOOL

_dwmapi = ctypes.WinDLL("dwmapi")

GWL_EXSTYLE = -20
DWMWA_WINDOW_CORNER_PREFERENCE = 33   # 角の形(Windows 11)
DWMWA_BORDER_COLOR = 34               # 枠の色(Windows 11)
DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2
DWMWA_COLOR_NONE = 0xFFFFFFFE         # 枠を描かない
BORDER_WHITE = 0x00FFFFFF             # COLORREF(0x00BBGGRR)
WS_EX_NOACTIVATE = 0x08000000
MONITOR_DEFAULTTONULL = 0
HWND_TOPMOST = wintypes.HWND(-1)
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010


def _dwm_set(hwnd, attribute, value):
    """窓の見た目を DWM にお願いする。Windows 10 では効かないが、失敗しても動作には困らない"""
    v = ctypes.c_uint(value)
    _dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), attribute, ctypes.byref(v), ctypes.sizeof(v))


def _circle_image(border_color):
    """丸の画像。4倍の大きさで描いてから縮めて、ふちをなめらかにする
    外側を枠の色で塗り、内側をパネルと同じ暗い色で塗る。丸の外は黒(窓の透明にする色)"""
    scale = 4
    big = SIZE * scale
    border = DOT_BORDER * scale
    img = Image.new("RGB", (big, big), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([0, 0, big - 1, big - 1], fill=border_color)
    draw.ellipse([border, border, big - 1 - border, big - 1 - border], fill=PANEL_BG)
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def _on_screen(x, y):
    """左上の少し内側がどこかのモニターの上にあるか(モニターを外したあとに、画面外に出ないように)"""
    point = wintypes.POINT(x + SIZE // 2, y + SIZE // 2)
    return bool(_user32.MonitorFromPoint(point, MONITOR_DEFAULTTONULL))


class IndicatorWindow:

    # 常に最前面に表示される小さなウィンドウ
    def __init__(self, x, y):
        if not _on_screen(x, y):
            d = config_store.defaults()
            x, y = d["indicator_x"], d["indicator_y"]
        self.x, self.y = x, y

        self.root = tk.Tk()
        self.root.overrideredirect(True)  # タイトルバーなし
        self.root.attributes('-topmost', True)  # 常に最前面
        self.root.attributes('-transparentcolor', 'black')  # 背景透明化
        self.root.config(bg='black') # ウィンドウ背景を黒に
        self.root.geometry(f'+{x}+{y}')

        ## 押してもフォーカスを奪わないようにする
        self.root.update_idletasks()
        self.hwnd = _user32.GetParent(self.root.winfo_id())
        style = _user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        _user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE)

        self.mode = None       # 今作ってある表示方法
        self.content = None    # 今の中身(丸のラベル、またはパネルの枠)
        self.drag_offset = None
        self.ticks = 0         # 見に行った回数(最前面に置き直す間隔を数える)

        ## 最初は非表示
        self.root.withdraw()
        self.visible = False

        # 「候補を出す」の窓(GPU版)。tkinter を同じスレッドで使うため、この Tk の上に作る
        self.candidate_window = CandidateWindow(self.root)

        self.root.after(POLL_MS, self.update_indicator)

    # ---- 中身を作る ----

    def build_dot(self):
        canvas = tk.Canvas(self.root, width=SIZE, height=SIZE, bg="black", highlightthickness=0,
                           cursor="fleur")  # つまめることがわかるカーソル
        # 枠が白いものと水色のもの。プッシュトゥトークかどうかで入れ替える(tk が捨てないよう持っておく)
        self.dot_images = {
            False: ImageTk.PhotoImage(_circle_image("#ffffff"), master=self.root),
            True: ImageTk.PhotoImage(_circle_image(ACCENT), master=self.root),
        }
        self.dot_circle = canvas.create_image(0, 0, anchor="nw", image=self.dot_images[False])
        self.dot_mic = canvas.create_text(SIZE // 2, SIZE // 2, text=GLYPH_MIC, font=DOT_ICON_FONT, fill=ICON_DIM)
        self.bind_drag(canvas)  # クリックしても操作はしない。つまんで動かすだけ
        self.dot_canvas = canvas
        return canvas

    def build_panel(self):
        frame = tk.Frame(self.root, bg=PANEL_BG)  # 枠は DWM が白く描く

        grip = tk.Label(frame, text=GLYPH_GRIP, font=("Segoe Fluent Icons", 10),
                        fg=ICON_DIM, bg=PANEL_BG, padx=4, cursor="fleur")
        grip.pack(side="left", fill="y")
        self.bind_drag(grip)

        self.mic_button = self.panel_button(frame, GLYPH_MIC, self.on_mic_press, self.on_mic_release)
        self.undo_button = self.panel_button(frame, GLYPH_UNDO, None, self.on_undo)
        self.ptt_button = self.panel_button(frame, GLYPH_PTT, None, self.on_ptt)
        return frame

    def panel_button(self, parent, glyph, on_press, on_release):
        button = tk.Label(parent, text=glyph, font=ICON_FONT, fg=ICON, bg=PANEL_BG, padx=8, pady=5, cursor="hand2")
        button.pack(side="left")
        button.bind("<Enter>", lambda e: button.config(bg=PANEL_HOVER))
        button.bind("<Leave>", lambda e: button.config(bg=PANEL_BG))
        if on_press:
            button.bind("<ButtonPress-1>", lambda e: on_press())
        if on_release:
            button.bind("<ButtonRelease-1>", lambda e: on_release())
        return button

    def apply_mode(self, mode):
        """表示方法が変わったら、中身を作り直す。位置はそのまま"""
        if self.content is not None:
            self.content.destroy()
            self.content = None

        if mode == "dot":
            # 丸の周りの黒を透明にする。角丸と枠はなし
            self.root.attributes('-transparentcolor', 'black')
            _dwm_set(self.hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DONOTROUND)
            _dwm_set(self.hwnd, DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE)
            self.content = self.build_dot()
            self.content.pack()
            self.root.geometry(f'{SIZE}x{SIZE}+{self.x}+{self.y}')
        elif mode == "panel":
            # 透明をやめて、角丸と白い枠をつける(背景と同化しないように)
            self.root.attributes('-transparentcolor', '')
            _dwm_set(self.hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
            _dwm_set(self.hwnd, DWMWA_BORDER_COLOR, BORDER_WHITE)
            self.content = self.build_panel()
            self.content.pack()
            self.root.geometry("")  # 大きさの指定を外して、パネルの中身に合わせる
            self.root.geometry(f'+{self.x}+{self.y}')

        self.mode = mode
        self.root.withdraw()
        self.visible = False  # 出すかどうかは update_indicator が決める

    # ---- パネルのボタン ----

    def on_mic_press(self):
        if config.get("push_to_talk"):
            state_manager.set_state("start")   # 押している間だけ録音
        else:
            state_manager.toggle_state()

    def on_mic_release(self):
        if config.get("push_to_talk"):
            state_manager.set_state("stop")

    def on_undo(self):
        # Backspace を送り終わるまで窓が固まらないよう、別のスレッドで
        # 取り消したら「候補を出す」の候補も忘れる(入れ替える入力が無くなるので)
        threading.Thread(target=lambda: (undo_input.undo(), candidates.forget()), daemon=True).start()

    def on_ptt(self):
        try:
            state_manager.set_push_to_talk(not config.get("push_to_talk"))
        except OSError as e:
            print(f"プッシュトゥトークの切り替えに失敗: {e}")

    # ---- つまんで動かす ----

    def bind_drag(self, widget):
        widget.bind("<ButtonPress-1>", self.on_press)
        widget.bind("<B1-Motion>", self.on_drag)
        widget.bind("<ButtonRelease-1>", self.on_release)

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
            self.x, self.y = pos
            self.save_position(*pos)

    def save_position(self, x, y):
        try:
            config.update({"indicator_x": x, "indicator_y": y})
        except Exception as e:
            # 保存できなくても、今の起動中は動かした位置のまま使える
            print(f"インジケーターの位置の保存に失敗: {e}")

    # ---- 0.1 秒ごとに状態を見る ----

    def update_indicator(self):
        try:
            self.refresh()
        except Exception as e:
            print(f"インジケーターの更新でエラー(次の回も続けます): {e!r}")
        finally:
            self.root.after(POLL_MS, self.update_indicator)

    def raise_to_top(self):
        """最前面の一番上に置き直す。フォーカスは奪わず、位置と大きさも変えない"""
        _user32.SetWindowPos(self.hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def follow_position(self):
        """位置を合わせる(つまんでいる途中は何もしない)
        - 設定の位置が変わったら(「窓の位置を元に戻す」のボタン)、そこへ動く
        - モニターを外すなどして画面の外に出ていたら、初期位置に戻して保存する"""
        if self.drag_offset is not None:
            return
        x, y = config.get("indicator_x"), config.get("indicator_y")
        if self.ticks % RAISE_EVERY == 0 and not _on_screen(x, y):
            d = config_store.defaults()
            x, y = d["indicator_x"], d["indicator_y"]
            self.save_position(x, y)
        if (x, y) != (self.x, self.y):
            self.x, self.y = x, y
            self.root.geometry(f"+{x}+{y}")

    def refresh(self):
        mode = config.get("indicator_mode")
        if mode != self.mode:
            self.apply_mode(mode)
        self.follow_position()

        recording = state_manager.get_state() == "start"
        transcribing = state_manager.is_transcribing()

        if mode == "dot":
            show = True
            self.dot_canvas.itemconfigure(self.dot_mic, fill=YELLOW if transcribing else GREEN if recording else ICON_DIM)
            self.dot_canvas.itemconfigure(self.dot_circle, image=self.dot_images[config.get("push_to_talk")])
        elif mode == "panel":
            show = True
            self.mic_button.config(fg=YELLOW if transcribing else GREEN if recording else ICON_DIM)
            self.ptt_button.config(fg=ACCENT if config.get("push_to_talk") else ICON_DIM)
        else:
            show = False

        if show and not self.visible:
            self.root.deiconify()
            self.visible = True
        elif not show and self.visible and self.drag_offset is None:  # つまんでいる途中では消さない
            self.root.withdraw()
            self.visible = False

        self.ticks += 1
        if self.visible and self.ticks % RAISE_EVERY == 0:
            self.raise_to_top()

    def run(self):
        self.root.mainloop()
