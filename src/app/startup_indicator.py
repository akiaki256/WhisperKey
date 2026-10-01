"""
起動中インジケーター
画面左上に「WhisperKey / 起動中…」のカードを出す。
重いimport(faster_whisper等)の前に表示し、準備完了時に閉じる。

見た目は操作パネル(gui_indicator.py)とそろえる:
- 暗い背景に、水色のマイクのアイコン、「WhisperKey」、その下に小さく今の段階(set_status で変える)
- 角丸と白い枠は Windows 11 の DWM に描いてもらう
- 中身は Pillow で 4 倍の大きさに描いてから縮めた画像(文字のふちがなめらかになり、ClearType の色のにじみも出ない)
- フォントが見つからないとき(古い Windows など)は、文字だけの表示にする

依存は tkinter と Pillow だけ(どちらも読み込みが軽い)なので、
main.pyの最序盤で import しても起動が遅くならない。
アニメーションは入れない。起動中はメインのスレッドが重い読み込みで止まり、描き直せないため。
"""

import ctypes
import os
import tkinter as tk

from PIL import Image, ImageDraw, ImageFont, ImageTk

# 見た目(操作パネルと同じ色)
WIDTH, HEIGHT = 196, 48
SCALE = 4
BG = "#202020"
TITLE_COLOR = "#ffffff"
STATUS_COLOR = "#9a9a9a"
ACCENT = "#60cdff"
GLYPH_MIC = "\uE720"

_FONTS = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
ICON_FONTS = ["SegoeIcons.ttf", "segmdl2.ttf"]   # Segoe Fluent Icons(Windows 11)、Segoe MDL2 Assets(Windows 10)
TITLE_FONT = "YuGothB.ttc"
STATUS_FONT = "YuGothM.ttc"

# DWM(gui_indicator.py と同じ)。Windows 10 では効かないが、失敗しても困らない
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWCP_ROUND = 2
BORDER_WHITE = 0x00FFFFFF


def _font(names, size):
    for name in names:
        try:
            return ImageFont.truetype(os.path.join(_FONTS, name), size * SCALE)
        except OSError:
            continue
    raise OSError(f"フォントが見つかりません: {names}")


def _dwm_set(hwnd, attribute, value):
    try:
        v = ctypes.c_uint(value)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(v), ctypes.sizeof(v))
    except OSError:
        pass


class StartupIndicator:
    """起動中を知らせる小さな常時前面ウィンドウ"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)       # タイトルバーなし
        self.root.attributes('-topmost', True) # 常に最前面
        self.root.geometry('+5+20')
        self.root.config(bg=BG)

        try:
            self.fonts = (_font(ICON_FONTS, 18), _font([TITLE_FONT], 12), _font([STATUS_FONT], 10))
            self.label = tk.Label(self.root, bd=0, bg=BG)
        except OSError as e:
            print(f"起動中の表示: {e}(文字だけで表示します)")
            self.fonts = None
            self.label = tk.Label(self.root, bg=BG, fg=TITLE_COLOR, font=("Yu Gothic UI", 10), padx=10, pady=4)
        self.label.pack()
        self.set_status("起動中…")

        # 角丸と白い枠(操作パネルと同じ)
        self.root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        _dwm_set(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
        _dwm_set(hwnd, DWMWA_BORDER_COLOR, BORDER_WHITE)

        # update で即座に描画(mainloop なしで表示される)
        self.root.update()

    def _render(self, status):
        icon_font, title_font, status_font = self.fonts
        big = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE), BG)
        draw = ImageDraw.Draw(big)
        draw.text((14 * SCALE, HEIGHT * SCALE // 2), GLYPH_MIC, font=icon_font, fill=ACCENT, anchor="lm")
        draw.text((44 * SCALE, 17 * SCALE), "WhisperKey", font=title_font, fill=TITLE_COLOR, anchor="lm")
        draw.text((44 * SCALE, 33 * SCALE), status, font=status_font, fill=STATUS_COLOR, anchor="lm")
        return big.resize((WIDTH, HEIGHT), Image.LANCZOS)

    def set_status(self, status):
        """下の小さい文字(今の段階)を変える"""
        try:
            if self.fonts:
                self.image = ImageTk.PhotoImage(self._render(status), master=self.root)   # tk が捨てないよう持っておく
                self.label.config(image=self.image)
            else:
                self.label.config(text=f"WhisperKey  {status}")
            self.root.update()
        except Exception as e:
            print(f"起動中の表示の更新に失敗: {e}")

    def close(self):
        """インジケーターを閉じる"""
        try:
            self.root.destroy()
        except Exception:
            pass
