"""
「候補を出す」の窓(GPU版。IME の変換候補の窓のつもり)

- 候補を出すキー(初期値 F8)で開く。開いたときは、今の入力を選んでいる(Enter を押しても何も変わらない)
  開いている間は、F8 をもう一度・↓ で次、↑ で前、Enter で確定、Esc で閉じる。行をクリックしても確定
- 確定したら candidates.choose で入れ替える(Backspace で今の入力を消して貼り付ける)。窓は閉じる
- ↑↓・Enter・Esc は、窓が開いている間だけ WhisperKey が借りる(RegisterHotKey)。閉じたらすぐ返す
  窓はフォーカスを奪わない(入力先のアプリにフォーカスを残すため)ので、キーは窓には届かない
  Enter を借りっぱなしにしないよう、IDLE_CLOSE_SECONDS 触らなかったら閉じる
- 最初の入力と違うところに背景色をつける
- 一度に見せるのは VISIBLE_ROWS 行まで。選んでいる行が外に出たら、見せる範囲をずらす(ホイールでも動かせる)
- 開発中だけ、いちばん下に「この中にない」を出す。押すと、正解の文を打つ小さな窓を開き、候補と一緒に記録する
  (candidates.log_miss。Enter で記録、Esc・閉じるで正解なしとして記録)
- 見た目は操作パネルと同じ(暗い色、角丸と白い枠)。つまんで(見出しをドラッグして)動かせて、位置を config に覚える
  覚えるのは「横の真ん中」と「下の端」(candidates_x / candidates_y)。候補の長さで窓の幅が変わっても同じ場所に出るように
  覚えていなければ、画面の中央下に出す。出すたびに、窓全体をモニターの見える範囲(タスクバーを除く)に収める
- つまんでいる間・マウスが乗っている間は閉じない(「候補はありません」のときも、位置を合わせる時間があるように)
- 設定タブの「窓の位置を元に戻す」で、覚えた位置を消せる(次に開いたときから画面の中央下)

tkinter はインジケーターの窓(gui_indicator.py)と同じスレッドで動かす(そのスレッドの Tk の上に作る)。
ほかのスレッド(ショートカットキーの待ち受け)からは request() でお願いを置き、この窓が POLL_MS ごとに拾う。
"""

import ctypes
from ctypes import wintypes
import queue
import threading
import time
import tkinter as tk

import candidates
import config
from key_shortcut import MainStateManager

state_manager = MainStateManager()

POLL_MS = 30
IDLE_CLOSE_SECONDS = 7
MESSAGE_SECONDS = 3
BOTTOM_MARGIN = 140   # 覚えていないとき、画面の下の端からどれだけ上に出すか
VISIBLE_ROWS = 10     # 一度に見せる行の数

# 窓が開いている間だけ借りるキー(key_shortcut.ACTIONS と合わせる)
TEMP_KEYS = {"cand_up": "up", "cand_down": "down", "cand_ok": "enter", "cand_cancel": "escape"}

BG = "#202020"
ROW_SELECTED = "#383838"
ROW_HOVER = "#2c2c2c"
TEXT = "#ffffff"
DIM = "#9a9a9a"
ACCENT = "#60cdff"
CHANGED_BG = "#1f5470"     # 最初の入力と違うところの背景
TEXT_FONT = ("Yu Gothic UI", 13)
SMALL_FONT = ("Yu Gothic UI", 9)
NUMBER_FONT = ("Yu Gothic UI", 11)

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.GetParent.argtypes = [wintypes.HWND]
_user32.GetParent.restype = wintypes.HWND
_user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.GetWindowLongW.restype = ctypes.c_long
_user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
_user32.SetWindowLongW.restype = ctypes.c_long
_user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
_user32.MonitorFromPoint.restype = wintypes.HMONITOR


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


_user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MONITORINFO)]
_user32.GetMonitorInfoW.restype = wintypes.BOOL
_dwmapi = ctypes.WinDLL("dwmapi")

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWCP_ROUND = 2
BORDER_WHITE = 0x00FFFFFF
MONITOR_DEFAULTTONULL = 0
MONITOR_DEFAULTTONEAREST = 2
EDGE_MARGIN = 8   # 画面の端に寄せるときの余白

_requests = queue.Queue()


def request(command):
    """ほかのスレッドからのお願い: "open_or_next" / "up" / "down" / "ok" / "cancel" """
    _requests.put(command)


def _dwm_set(hwnd, attribute, value):
    v = ctypes.c_uint(value)
    _dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), attribute, ctypes.byref(v), ctypes.sizeof(v))


def _on_screen(x, y):
    return bool(_user32.MonitorFromPoint(wintypes.POINT(x, y), MONITOR_DEFAULTTONULL))


def _work_area(x, y):
    """(x, y) に一番近いモニターの、タスクバーを除いた範囲 (左, 上, 右, 下)"""
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(_MONITORINFO)
    _user32.GetMonitorInfoW(_user32.MonitorFromPoint(wintypes.POINT(x, y), MONITOR_DEFAULTTONEAREST), ctypes.byref(info))
    r = info.rcWork
    return r.left, r.top, r.right, r.bottom


class _MissDialog:
    """正解の文を打つ小さな窓(開発中だけ)。今の入力を入れておくので、直して Enter"""

    def __init__(self, root, items, current, x, y):
        self.items, self.current, self.done = items, current, False
        top = tk.Toplevel(root)
        top.title("正解の文(開発用)")
        top.attributes("-topmost", True)
        top.config(bg=BG)
        tk.Label(top, text="正解の文(Enter で記録 / Esc で正解なしとして記録)", font=SMALL_FONT, fg=DIM, bg=BG).pack(
            anchor="w", padx=12, pady=(10, 4))
        self.entry = tk.Entry(top, font=TEXT_FONT, width=48)
        self.entry.insert(0, items[current]["text"])
        self.entry.pack(fill="x", padx=12, pady=(0, 12))
        self.entry.bind("<Return>", lambda e: self.finish(self.entry.get().strip() or None))
        self.entry.bind("<Escape>", lambda e: self.finish(None))
        top.protocol("WM_DELETE_WINDOW", lambda: self.finish(None))
        top.geometry(f"+{x}+{y}")
        self.top = top
        top.after(50, self.grab_focus)

    def grab_focus(self):
        self.top.lift()
        self.top.focus_force()
        self.entry.focus_set()
        self.entry.select_range(0, "end")

    def finish(self, correct):
        if self.done:
            return
        self.done = True
        try:
            candidates.log_miss(self.items, self.current, correct)
        finally:
            self.top.destroy()


def _set_temp_keys(on):
    """↑↓・Enter・Esc を借りる / 返す"""
    for action, key in TEMP_KEYS.items():
        error = state_manager.register_shortcut(action, key if on else "")
        if on and error:
            print(f"候補を出す: {key} を借りられませんでした: {error[1]}")


class CandidateWindow:
    def __init__(self, root):
        self.root = root
        self.top = None
        self.rows = []          # 行ごとの {"frame", "bar", "labels": [(ラベル, 違うところか)]}
        self.first = 0          # 見せている一番上の行
        self.selected = 0
        self.last_touch = 0.0
        self.message_until = None
        self.drag_offset = None
        self.version = None     # 開いたときの候補の版(candidates.choose に渡す)
        self.items = []         # 開いたときの候補の並び(「この中にない」の記録に使う)
        self.current = 0
        self.root.after(POLL_MS, self.poll)

    # ---- お願いを拾う ----

    def poll(self):
        try:
            while True:
                try:
                    command = _requests.get_nowait()
                except queue.Empty:
                    break
                self.handle(command)
            now = time.monotonic()
            if self.top is not None and (self.drag_offset is not None or self.pointer_inside()):
                # つまんでいる間・マウスが乗っている間は閉じない(位置を合わせたり、読んだりする時間)
                self.last_touch = now
                if self.message_until is not None:
                    self.message_until = max(self.message_until, now + MESSAGE_SECONDS)
            if self.top is not None and self.message_until is None and now - self.last_touch > IDLE_CLOSE_SECONDS:
                self.close()
            if self.message_until is not None and now > self.message_until:
                self.close()
            if self.top is not None and self.message_until is None and candidates.get()[2] != self.version:
                self.close()   # 開いたあとに次の入力が来た(並びが古くなった)ので閉じる
        except Exception as e:
            print(f"候補の窓でエラー(次の回も続けます): {e!r}")
        finally:
            self.root.after(POLL_MS, self.poll)

    def handle(self, command):
        if self.top is None or self.message_until is not None:
            if command == "open_or_next":
                self.open()
            return
        self.last_touch = time.monotonic()
        if command in ("open_or_next", "down"):
            self.select((self.selected + 1) % len(self.rows))
        elif command == "up":
            self.select((self.selected - 1) % len(self.rows))
        elif command == "ok":
            self.confirm(self.selected)
        elif command == "cancel":
            self.close()

    def pointer_inside(self):
        px, py = self.top.winfo_pointerxy()
        x, y = self.top.winfo_rootx(), self.top.winfo_rooty()
        return x <= px < x + self.top.winfo_width() and y <= py < y + self.top.winfo_height()

    # ---- 開く・閉じる ----

    def open(self):
        items, current, self.version = candidates.get()
        self.items, self.current = items, current
        self.close()
        self.build(items, current)
        if not items or len(items) == 1:
            # 入れ替えられる候補が無いときは、知らせるだけで、キーは借りない
            self.message_until = time.monotonic() + MESSAGE_SECONDS
            return
        self.message_until = None
        self.last_touch = time.monotonic()
        self.select(current)   # 開いたときは今の入力を選んでいる(F8 をもう一度・↓ で次へ)
        _set_temp_keys(True)

    def close(self):
        if self.top is None:
            return
        borrowed = self.message_until is None
        self.top.destroy()
        self.top = None
        self.rows = []
        self.first = 0
        self.message_until = None
        if borrowed:
            _set_temp_keys(False)

    def report_miss(self):
        """「この中にない」: 窓を閉じて、正解の文を打つ窓を開く"""
        items, current = self.items, self.current
        x, y = self.top.winfo_rootx(), self.top.winfo_rooty()
        self.close()
        _MissDialog(self.root, items, current, x, y)

    def confirm(self, index):
        self.close()
        # Backspace と貼り付けが終わるまで窓のスレッドが固まらないよう、別のスレッドで
        threading.Thread(target=candidates.choose, args=(index, self.version), daemon=True).start()

    # ---- 中身を作る ----

    def build(self, items, current):
        top = tk.Toplevel(self.root)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        top.config(bg=BG)
        self.top = top

        header = tk.Frame(top, bg=BG, cursor="fleur")
        header.pack(fill="x", padx=12, pady=(8, 4))
        tk.Label(header, text="候補", font=("Yu Gothic UI", 10, "bold"), fg=TEXT, bg=BG).pack(side="left")
        hint = "F8・↑↓ で選ぶ　Enter で確定　Esc で閉じる" if len(items) > 1 else "ほかの候補はありません"
        if not items:
            hint = "候補はまだありません(入力補正で入力したあとに使えます)"
        tk.Label(header, text=hint, font=SMALL_FONT, fg=DIM, bg=BG).pack(side="left", padx=(12, 0))
        for w in (header, *header.winfo_children()):
            self.bind_drag(w)

        self.more_above = tk.Label(top, text="", font=SMALL_FONT, fg=DIM, bg=BG)
        self.more_above.pack(fill="x", padx=12)
        body = tk.Frame(top, bg=BG)
        body.pack(fill="both", padx=6)
        self.more_below = tk.Label(top, text="", font=SMALL_FONT, fg=DIM, bg=BG)
        self.more_below.pack(fill="x", padx=12, pady=(0, 8))
        for i, item in enumerate(items):
            self.rows.append(self.build_row(body, i, item, current))
        for w in (top, body, self.more_above, self.more_below):
            w.bind("<MouseWheel>", self.on_wheel)
        if candidates.LOG_ENABLED and items:   # 開発中だけ
            miss = tk.Label(top, text="この中にない(正解を記録)", font=SMALL_FONT, fg=DIM, bg=BG, cursor="hand2")
            miss.pack(anchor="e", padx=12, pady=(0, 8))
            miss.bind("<ButtonRelease-1>", lambda e: self.report_miss())
        self.first = 0   # 開いたあとの select で、今の入力が見えるところまでずらす
        self.show_rows()

        top.update_idletasks()
        hwnd = _user32.GetParent(top.winfo_id())
        _user32.SetWindowLongW(hwnd, GWL_EXSTYLE, _user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_NOACTIVATE)
        _dwm_set(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
        _dwm_set(hwnd, DWMWA_BORDER_COLOR, BORDER_WHITE)
        self.place()

    def show_rows(self):
        """self.first から VISIBLE_ROWS 行だけ見せる。上下に隠れている数も出す"""
        for row in self.rows:
            row["frame"].pack_forget()
        for row in self.rows[self.first:self.first + VISIBLE_ROWS]:
            row["frame"].pack(fill="x", pady=1)
        above, below = self.first, max(0, len(self.rows) - self.first - VISIBLE_ROWS)
        self.more_above.config(text=f"▲ ほかに {above} 件" if above else "")
        self.more_below.config(text=f"▼ ほかに {below} 件" if below else "")

    def scroll_to(self, index):
        """index の行が見えるように、見せる範囲をずらす"""
        first = self.first
        if index < first:
            first = index
        elif index >= first + VISIBLE_ROWS:
            first = index - VISIBLE_ROWS + 1
        if first != self.first:
            self.first = first
            self.show_rows()
            self.place()

    def on_wheel(self, event):
        self.last_touch = time.monotonic()
        step = -1 if event.delta > 0 else 1
        first = min(max(self.first + step, 0), max(0, len(self.rows) - VISIBLE_ROWS))
        if first != self.first:
            self.first = first
            self.show_rows()
            self.place()

    def build_row(self, parent, index, item, current):
        frame = tk.Frame(parent, bg=BG, cursor="hand2")
        bar = tk.Frame(frame, bg=BG, width=3)
        bar.pack(side="left", fill="y")
        number = tk.Label(frame, text=str(index + 1), font=NUMBER_FONT, fg=DIM, bg=BG, width=2)
        number.pack(side="left", padx=(4, 6))
        labels = [(number, False)]

        text, spans = item["text"], sorted(item["spans"])
        pos = 0
        for start, length in spans + [(len(text), 0)]:
            if start > pos:
                lbl = tk.Label(frame, text=text[pos:start], font=TEXT_FONT, fg=TEXT, bg=BG, padx=0, pady=3)
                lbl.pack(side="left")
                labels.append((lbl, False))
            if length:
                lbl = tk.Label(frame, text=text[start:start + length], font=TEXT_FONT, fg=TEXT, bg=CHANGED_BG, padx=1, pady=3)
                lbl.pack(side="left")
                labels.append((lbl, True))
            pos = max(pos, start + length)

        note = "入力中" if index == current else item["note"]
        note_label = tk.Label(frame, text=note, font=SMALL_FONT, fg=DIM, bg=BG)
        note_label.pack(side="right", padx=(16, 8))
        labels.append((note_label, False))

        for w in (frame, bar, *[l for l, _ in labels]):
            w.bind("<MouseWheel>", self.on_wheel)
            w.bind("<Enter>", lambda e, i=index: self.hover(i, True))
            w.bind("<Leave>", lambda e, i=index: self.hover(i, False))
            w.bind("<ButtonRelease-1>", lambda e, i=index: self.confirm(i))
        return {"frame": frame, "bar": bar, "labels": labels}

    def paint(self, index, bg):
        row = self.rows[index]
        row["frame"].config(bg=bg)
        row["bar"].config(bg=ACCENT if index == self.selected else bg)
        for lbl, changed in row["labels"]:
            if not changed:
                lbl.config(bg=bg)

    def select(self, index):
        old, self.selected = self.selected, index
        if 0 <= old < len(self.rows):
            self.paint(old, BG)
        self.paint(index, ROW_SELECTED)
        self.scroll_to(index)

    def hover(self, index, entering):
        self.last_touch = time.monotonic()
        if index != self.selected:
            self.paint(index, ROW_HOVER if entering else BG)

    # ---- 位置(横の真ん中と、下の端で覚える) ----

    def place(self):
        """覚えている位置に出す。窓全体が、一番近いモニターの見える範囲(タスクバーを除く)に収まるよう寄せる
        (モニターを外した・解像度を変えた・候補が長くて窓が広い、などで、はみ出さないように)"""
        top = self.top
        w, h = top.winfo_reqwidth(), top.winfo_reqheight()
        cx, bottom = config.get("candidates_x"), config.get("candidates_y")
        if cx is None or bottom is None or not _on_screen(cx, bottom - 10):
            cx = top.winfo_screenwidth() // 2
            bottom = top.winfo_screenheight() - BOTTOM_MARGIN
        left, upper, right, lower = _work_area(cx, bottom - 10)
        x = min(max(cx - w // 2, left + EDGE_MARGIN), right - w - EDGE_MARGIN)
        y = min(max(bottom - h, upper + EDGE_MARGIN), lower - h - EDGE_MARGIN)
        top.geometry(f"+{max(x, left)}+{max(y, upper)}")

    def bind_drag(self, widget):
        widget.bind("<ButtonPress-1>", self.on_press)
        widget.bind("<B1-Motion>", self.on_drag)
        widget.bind("<ButtonRelease-1>", self.on_release)

    def on_press(self, event):
        self.drag_offset = (event.x_root - self.top.winfo_x(), event.y_root - self.top.winfo_y())
        self.last_touch = time.monotonic()

    def on_drag(self, event):
        if self.drag_offset is None:
            return
        dx, dy = self.drag_offset
        self.top.geometry(f"+{event.x_root - dx}+{event.y_root - dy}")
        self.last_touch = time.monotonic()

    def on_release(self, event):
        if self.drag_offset is None:
            return
        self.drag_offset = None
        x, y = self.top.winfo_x(), self.top.winfo_y()
        try:
            config.update({"candidates_x": x + self.top.winfo_width() // 2, "candidates_y": y + self.top.winfo_height()})
        except Exception as e:
            print(f"候補の窓の位置の保存に失敗: {e}")
