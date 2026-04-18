"""
多重起動防止(名前付きMutex)
仕様書§5.4

Tkinterルートウィンドウを作る前に呼ばれる処理なので、
メッセージ表示は Windows 標準の MessageBox (ctypes経由) を使う。
CTkMessagebox は内部でTkルートを要求するため、ここでは使えない。
"""

import sys
import ctypes

# pywin32関連は import 失敗しうる(開発環境によって)ため try で囲む
try:
    import win32event
    import win32api
    import winerror
    _PYWIN32_AVAILABLE = True
except ImportError:
    _PYWIN32_AVAILABLE = False

import constants as C


# GCで解放されないようグローバルでハンドルを保持
_mutex_handle = None


def _show_message(title, message):
    """
    Windows標準のMessageBoxを表示。
    Tkinterルートウィンドウに依存しない。
    
    MB_OK (0x00) + MB_ICONWARNING (0x30) = 0x30
    """
    try:
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x30)
    except Exception as e:
        # MessageBox表示にも失敗した場合はコンソールに出すだけ
        print(f"{title}: {message}")
        print(f"(MessageBox表示失敗: {e})")


def ensure_single_instance(mutex_name=None):
    """
    名前付きMutexで多重起動を防止する。
    すでに起動中ならメッセージを出して sys.exit(0) する。
    
    Args:
        mutex_name: Mutex名。省略時は constants の値を使用。
    """
    global _mutex_handle
    
    if not _PYWIN32_AVAILABLE:
        # pywin32が使えない環境では警告のみ出して続行
        # (本番のWindows環境では必ず入っている前提)
        print("warning: pywin32 is not available. multi-instance check is skipped.")
        return
    
    if mutex_name is None:
        mutex_name = C.MUTEX_NAME_CONFIG
    
    _mutex_handle = win32event.CreateMutex(None, False, mutex_name)
    last_error = win32api.GetLastError()
    
    if last_error == winerror.ERROR_ALREADY_EXISTS:
        _show_message(
            "起動エラー",
            "すでに設定画面が起動しています。",
        )
        sys.exit(0)
