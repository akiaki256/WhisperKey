"""
ショートカットキー(グローバルホットキー)の管理

Windows の RegisterHotKey を使う。
以前は keyboard ライブラリ(低レベルフック)を使っていたが、何かの拍子に
ショートカットが効かなくなる不具合があったため置き換えた。
RegisterHotKey は Windows 自身がキーの組み合わせを判定して知らせてくれるので、
フックが外れたり、押されているキーの判定がずれたりすることがない。

注意: 登録したキーは WhisperKey が占有するため、ほかのソフトには届かなくなる。
"""

import ctypes
from ctypes import wintypes
import sys
import threading
import time
import winsound

from error_dialog import show_error

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_user32.GetMessageW.restype = wintypes.BOOL
_user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
_user32.PeekMessageW.restype = wintypes.BOOL
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000  # 押しっぱなしにしても連続で発火させない
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

_HOTKEY_ID = 1

_MODIFIER_FLAGS = {
    "ctrl": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
}

_SPECIAL_KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
}


def parse_shortcut(key_str):
    """
    "f9" や "ctrl+space" を (修飾キーのフラグ, 仮想キーコード) に変換する。
    解釈できなければ ValueError。
    """
    *modifiers, main = key_str.strip().lower().split("+")

    flags = 0
    for m in modifiers:
        if m not in _MODIFIER_FLAGS:
            raise ValueError(f"未対応の修飾キー: {m}")
        flags |= _MODIFIER_FLAGS[m]

    if main.startswith("f") and main[1:].isdigit() and 1 <= int(main[1:]) <= 24:
        vk = 0x70 + int(main[1:]) - 1  # VK_F1 = 0x70
    elif len(main) == 1 and ("a" <= main <= "z" or "0" <= main <= "9"):
        vk = ord(main.upper())
    elif main in _SPECIAL_KEYS:
        vk = _SPECIAL_KEYS[main]
    else:
        raise ValueError(f"未対応のキー: {main}")

    return flags, vk


def _wait_for_release(vk):
    """
    キーが離されるまで待ち、その間に届いたホットキーの通知を捨てる。

    MOD_NOREPEAT は押しっぱなしの連続発火を防ぐが、押しっぱなしの途中で
    別のキー入力(貼り付け時の Ctrl+V など)があると「押し直し」とみなされて
    もう一度通知が届く。一度の押下で切り替わるのを一回だけにするための処理。
    """
    while _user32.GetAsyncKeyState(vk) & 0x8000:
        time.sleep(0.02)

    msg = wintypes.MSG()
    while _user32.PeekMessageW(ctypes.byref(msg), None, WM_HOTKEY, WM_HOTKEY, PM_REMOVE):
        pass


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

    # ホットキー登録(stateの切り替えを実行する処理を付与)
    def start_listener(self, shortcut_key):
        """
        専用スレッドで RegisterHotKey を行い、そのスレッドで WM_HOTKEY を待ち受ける。
        (RegisterHotKey の通知は、登録したスレッドのメッセージキューに届くため)
        登録に失敗したらエラーを表示してソフトを終了する。
        """
        registered = threading.Event()
        result = {}

        def run():
            try:
                flags, vk = parse_shortcut(shortcut_key)
            except ValueError as e:
                result["error"] = "invalid"
                result["detail"] = e
                registered.set()
                return

            if not _user32.RegisterHotKey(None, _HOTKEY_ID, flags | MOD_NOREPEAT, vk):
                code = ctypes.get_last_error()
                result["error"] = "taken" if code == ERROR_HOTKEY_ALREADY_REGISTERED else "failed"
                result["detail"] = ctypes.WinError(code)
                registered.set()
                return

            registered.set()

            msg = wintypes.MSG()
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == _HOTKEY_ID:
                    try:
                        self.toggle_state()
                    except Exception as e:
                        # ここで例外が抜けると待ち受けが止まり、ショートカットが効かなくなるため握りつぶす
                        print(f"聞き取りモードの切り替えでエラー: {e}")
                    _wait_for_release(vk)

        threading.Thread(target=run, name="hotkey", daemon=True).start()
        registered.wait()

        if "error" in result:
            if result["error"] == "taken":
                message = (
                    f"ショートカットキー「{shortcut_key}」は、ほかのソフトが使用中です。\n"
                    "ソフトを終了します。\n\n"
                    "インストール先の Config.exe を起動して、別のキーに変更してください。"
                )
            elif result["error"] == "invalid":
                message = (
                    f"ショートカットキー「{shortcut_key}」を読み込めませんでした。\n"
                    "ソフトを終了します。\n\n"
                    "config.json の 'shortcut_key' の値を確認するか、\n"
                    "インストール先の Config.exe から設定し直してください。"
                )
            else:
                message = (
                    "ショートカットキーの登録に失敗したため、ソフトを終了します。\n\n"
                    f"詳細: {result['detail']}"
                )
            show_error("ショートカットキー登録エラー", message)
            print(f"error: {result['detail']}")
            sys.exit(1)

        print(f"ショートカットキー登録：完了 ({shortcut_key})")
        winsound.Beep(1200, 100)
        winsound.Beep(1600, 100)  # Hz, ms
