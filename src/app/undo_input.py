"""
直前の入力を取り消す

- 貼り付けた文章を remember() で覚えておき、undo() でその文字数ぶん Backspace を送る
  (カーソルを動かしたり自分で打ったりしていなければ、貼り付けた分だけが消える)
- 取り消せるのは一回だけ。続けて押しても、その前の入力までは消さない
- 音声実行が動いたら forget() で忘れる(直前がコマンドだったのに、その前の入力を消さないように)
- 入力履歴からは消さない(聞き間違いを音声辞書に登録するときに、履歴から拾えるように)

注意: 文字数は Python の len で数える。絵文字の一部(肌の色つきなど)は、1回の Backspace で消える単位と
数がずれることがある
"""

import ctypes
import threading
import time
import winsound

import keyboard

_user32 = ctypes.WinDLL("user32")
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short

# Shift / Ctrl / Alt / 左右の Windows キー
_MODIFIER_VKS = [0x10, 0x11, 0x12, 0x5B, 0x5C]

_last = None
_lock = threading.Lock()


def remember(text):
    global _last
    with _lock:
        _last = text


def forget():
    remember(None)


def _wait_for_modifiers_released(timeout=2.0):
    """
    修飾キーが離されるのを待つ。取り消しのキーを押したまま Backspace を送ると組み合わさってしまうため
    (Shift+F9 なら Shift+Backspace、Ctrl を含むキーなら Ctrl+Backspace = 単語ごと消す、になる)
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not any(_user32.GetAsyncKeyState(vk) & 0x8000 for vk in _MODIFIER_VKS):
            return
        time.sleep(0.02)


def undo():
    """直前に貼り付けた文章を消す。取り消すものが無ければ、低い音で知らせるだけ"""
    global _last
    with _lock:
        text, _last = _last, None

    if not text:
        print("取り消し：取り消せる入力がありません")
        winsound.Beep(400, 80)  # Hz, ms
        return

    _wait_for_modifiers_released()
    for _ in range(len(text)):
        keyboard.send("backspace")
    print(f"取り消し：{len(text)} 文字")
