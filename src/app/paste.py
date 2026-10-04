"""
貼り付け(音声入力の文字を、入力したいアプリに入れる)

- クリップボードに文字を入れて Ctrl+V を送る
- clipboard_private(初期値オン)のときは、「この中身は見張らないで」という印を一緒に付ける
  Win + V のクリップボード履歴・クラウド同期・ほかのクリップボード管理ソフトに、音声入力の文字が残らない
  (パスワード管理ソフトがパスワードをコピーするときと同じやり方)
  - ExcludeClipboardContentFromMonitorProcessing: 見張るもの全部に「見ないで」
  - CanIncludeInClipboardHistory = 0: Win + V の履歴に入れない
  - CanUploadToCloudClipboard = 0: ほかのパソコンへ同期しない
- クリップボードを空にはしない(待ち時間を決め打ちする必要があり、早すぎると貼り付けが失敗するため)
  今のクリップボードの中身は、音声入力の文字になる
"""

import struct
import time

import keyboard
import pyperclip
import pywintypes
import win32clipboard

import config

_EXCLUDE = win32clipboard.RegisterClipboardFormat("ExcludeClipboardContentFromMonitorProcessing")
_HISTORY = win32clipboard.RegisterClipboardFormat("CanIncludeInClipboardHistory")
_CLOUD = win32clipboard.RegisterClipboardFormat("CanUploadToCloudClipboard")
_DWORD_ZERO = struct.pack("<I", 0)  # 「しない」を表す 0(4バイト)


def _open_clipboard():
    """ほかのアプリがちょうど使っていると開けないので、少し待って何回か試す"""
    for _ in range(10):
        try:
            win32clipboard.OpenClipboard()
            return
        except pywintypes.error:
            time.sleep(0.02)
    raise RuntimeError("クリップボードを開けませんでした")


def set_clipboard(text, private):
    _open_clipboard()
    try:
        win32clipboard.EmptyClipboard()
        # 文字のまま渡すと、数字だけの文(「1447」など)を pywin32 がハンドルの番号として受け取り、落ちる
        # UTF-16 のバイト列(終わりの 0 つき)にして渡す
        win32clipboard.SetClipboardData(win32clipboard.CF_UNICODETEXT, text.encode("utf-16-le") + b"\0\0")
        if private:
            win32clipboard.SetClipboardData(_EXCLUDE, _DWORD_ZERO)  # 中身は何でもよく、印があること自体に意味がある
            win32clipboard.SetClipboardData(_HISTORY, _DWORD_ZERO)
            win32clipboard.SetClipboardData(_CLOUD, _DWORD_ZERO)
    finally:
        win32clipboard.CloseClipboard()


def paste(text):
    try:
        set_clipboard(text, config.get("clipboard_private"))
    except Exception as e:
        # 印は付けられないが、貼り付けは失敗させない
        print(f"クリップボードへの書き込みに失敗(印なしで貼り付けます): {e}")
        pyperclip.copy(text)
    keyboard.send('ctrl+v')
