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
import threading
import time
import config
import sounds

_user32 = ctypes.WinDLL("user32", use_last_error=True)
_user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
_user32.RegisterHotKey.restype = wintypes.BOOL
_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_user32.GetMessageW.restype = wintypes.BOOL
_user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
_user32.PeekMessageW.restype = wintypes.BOOL
_user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
_user32.GetAsyncKeyState.restype = ctypes.c_short
_user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.UnregisterHotKey.restype = wintypes.BOOL
_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.PostThreadMessageW.restype = wintypes.BOOL

_kernel32 = ctypes.WinDLL("kernel32")
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000  # 押しっぱなしにしても連続で発火させない
WM_HOTKEY = 0x0312
PM_NOREMOVE = 0x0000
PM_REMOVE = 0x0001
WM_APP_COMMAND = 0x8000 + 1  # 待ち受けのスレッドへの「お願いがあるよ」の合図(WM_APP + 1)
ERROR_HOTKEY_ALREADY_REGISTERED = 1409

# ショートカットの役割と、Windows に登録するときの番号(役割が増えたらここに足す)
ACTIONS = {
    "toggle": 1,  # 入力モードの切り替え
    "undo": 2,    # 直前の入力を取り消す
}

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


def check_new_shortcut(key_str):
    """
    画面から新しく選ばれたキーを使ってよいか。よければ None、だめなら理由の文
    登録したキーは全部のソフトで使えなくなるので、ふだんの文字入力に使うキーは選ばせない
    - 修飾キーなし: F1〜F24 だけ(Space や A を取ると、その文字が打てなくなる)
    - Shift だけ: F1〜F24 だけ(Shift + A を取ると、大文字の A が打てなくなる)
    """
    try:
        flags, vk = parse_shortcut(key_str)
    except ValueError:
        return "このキーは使えません"

    is_function_key = 0x70 <= vk <= 0x87  # VK_F1 〜 VK_F24
    if not (flags & (MOD_CONTROL | MOD_ALT)) and not is_function_key:
        return "ふだんの文字入力に使うキーです。Ctrl か Alt と組み合わせるか、F1〜F24 を選んでください"
    return None


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
    """
    アプリの状態を持つ(どこから MainStateManager() を呼んでも同じもの)

    - state: 録音のオン("start")/オフ("stop")
    - 文字起こしが残っている数: キューに入れる直前に add_pending()、
      文字起こしが終わったら finish_pending() を呼ぶ。録音のオン/オフとは別に進む
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.state = "stop"
            cls._instance._pending = 0
            cls._instance._pending_lock = threading.Lock()
            # 役割のキーが押されたとき / 離されたときの処理
            cls._instance._handlers = {"toggle": cls._instance.press_toggle}
            cls._instance._release_handlers = {"toggle": cls._instance.release_toggle}
        return cls._instance

    def get_state(self):
        return self.state

    def add_pending(self):
        with self._pending_lock:
            self._pending += 1

    def finish_pending(self):
        with self._pending_lock:
            self._pending -= 1

    def is_transcribing(self):
        return self._pending > 0

    def set_state(self, new_state):
        """録音のオン("start")/オフ("stop")を変えて、効果音で知らせる。同じなら何もしない"""
        if new_state == self.state:
            return
        self.state = new_state
        if new_state == "start":
            print("聞き取りモード：スタート")
            sounds.play("on")
        else:
            print("聞き取りモード：ストップ")
            sounds.play("off")

    def toggle_state(self):
        self.set_state("start" if self.state == "stop" else "stop")
        return self.state

    # 入力モードの切り替えキー
    # 切り替えモード: 押すたびにオン/オフ
    # プッシュトゥトーク(push_to_talk): 押したらオン、離したらオフ
    #   離したところまでの音声は、録音の係(audio.py)がすぐ文字起こしに回す
    def press_toggle(self):
        if config.get("push_to_talk"):
            self.set_state("start")
        else:
            self.toggle_state()

    def release_toggle(self):
        if config.get("push_to_talk"):
            self.set_state("stop")

    def set_push_to_talk(self, enabled):
        """プッシュトゥトークを切り替えて保存する(画面の表示は config の知らせでそろう)
        オンにしたときは録音をオフにする(録音オンのまま切り替えても、ここから「押している間だけ」にそろえる)"""
        config.update({"push_to_talk": enabled})
        if enabled:
            self.set_state("stop")

    # ---- ショートカットキー(役割ごと) ----

    def set_handler(self, action, fn):
        """役割のキーが押されたときに呼ぶ処理を決める(toggle は press_toggle が最初から入っている)"""
        self._handlers[action] = fn

    def _call_handler(self, handlers, action):
        handler = handlers.get(action)
        try:
            if handler:
                handler()
        except Exception as e:
            # ここで例外が抜けると待ち受けが止まり、ショートカットが効かなくなるため握りつぶす
            print(f"ショートカット({action})の処理でエラー: {e}")

    def start_listener(self, keys):
        """
        専用スレッドで RegisterHotKey を行い、そのスレッドで WM_HOTKEY を待ち受ける。
        (RegisterHotKey の通知は、登録したスレッドのメッセージキューに届くため)

        keys: {役割: キー}。例 {"toggle": "f9", "undo": "shift+f9"}。キーが "" なら割り当てない

        登録に失敗しても終了しない。待ち受けはキーなしのまま続け、あとから画面で登録し直せるようにする。
        戻り値: 失敗した役割だけの {役割: (種類, 詳細)}。種類は "invalid" / "taken" / "failed"

        起動したあとの登録し直し(画面からキーを変えるとき)も、Windows の決まりで同じスレッドで行う。
        ほかのスレッドからは suspend_all_shortcuts() / register_shortcut() でお願いする。
        お願いは _command に置き、PostThreadMessageW で合図を送って、このスレッドの中で処理する。
        """
        registered = threading.Event()
        errors = {}
        self._command = None
        self._command_result = None
        self._command_done = threading.Event()
        self._command_lock = threading.Lock()
        vks = {}  # 登録中の {役割: 仮想キーコード}

        def unregister(action):
            if action in vks:
                _user32.UnregisterHotKey(None, ACTIONS[action])
                del vks[action]

        def register(action, key_str):
            """役割に key_str を登録し直す。成功(または "" で割り当てなし)なら None、失敗なら (種類, 詳細)"""
            unregister(action)
            if key_str == "":
                return None
            try:
                flags, vk = parse_shortcut(key_str)
            except ValueError as e:
                return "invalid", e
            if not _user32.RegisterHotKey(None, ACTIONS[action], flags | MOD_NOREPEAT, vk):
                code = ctypes.get_last_error()
                return ("taken" if code == ERROR_HOTKEY_ALREADY_REGISTERED else "failed"), ctypes.WinError(code)
            vks[action] = vk
            return None

        def run():
            self._thread_id = _kernel32.GetCurrentThreadId()
            # このスレッドにメッセージの受け口を作っておく(PostThreadMessageW の合図を受け取るため)
            msg = wintypes.MSG()
            _user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_NOREMOVE)

            for action, key_str in keys.items():
                error = register(action, key_str)
                if error:
                    errors[action] = error
            registered.set()

            actions_by_id = {hotkey_id: action for action, hotkey_id in ACTIONS.items()}
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    action = actions_by_id.get(msg.wParam)
                    if action not in vks:
                        continue
                    self._call_handler(self._handlers, action)
                    _wait_for_release(vks[action])
                    self._call_handler(self._release_handlers, action)

                elif msg.message == WM_APP_COMMAND:
                    command, action, key_str = self._command
                    if command == "suspend_all":
                        for registered_action in list(vks):
                            unregister(registered_action)
                        self._command_result = None
                    else:
                        self._command_result = register(action, key_str)
                    self._command_done.set()

        threading.Thread(target=run, name="hotkey", daemon=True).start()
        registered.wait()

        for action, key_str in keys.items():
            if action in errors:
                print(f"ショートカットキー登録：失敗 ({action}: {key_str}): {errors[action][1]}")
            else:
                print(f"ショートカットキー登録：完了 ({action}: {key_str or '割り当てなし'})")
        return errors

    def _send_command(self, command, action=None, key_str=None):
        """待ち受けのスレッドにお願いして、終わるまで待つ"""
        with self._command_lock:
            self._command = (command, action, key_str)
            self._command_done.clear()
            _user32.PostThreadMessageW(self._thread_id, WM_APP_COMMAND, 0, 0)
            if not self._command_done.wait(timeout=3):
                return "failed", "ショートカットキーの待ち受けが応答しません"
            return self._command_result

    def suspend_all_shortcuts(self):
        """全部の登録を一旦外す(画面でキーを押して決めるあいだ、どのキーも画面に届くように)"""
        self._send_command("suspend_all")

    def register_shortcut(self, action, key_str):
        """役割に key_str を登録し直す("" なら外すだけ)。成功なら None、失敗なら (種類, 詳細)
        失敗したときはその役割に何も登録されていないので、呼んだ側で元のキーを登録し直すこと"""
        return self._send_command("register", action, key_str)
