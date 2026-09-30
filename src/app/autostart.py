"""
Windows の起動時に立ち上げる(自動起動)

インストーラーと同じ場所・同じ名前で、Windows の「サインインしたら動かすもの」の一覧
(レジストリの HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run)に書く・消す。
- 名前はインストーラーの MyAppName と同じ(WhisperKey CPU / WhisperKey GPU)。インストールのときに選んだ設定と、
  設定タブのスイッチが同じものを指すように
- 中身はインストーラーと同じく、exe の場所を "" で囲んだもの
- 本当の値はレジストリにある(config.json には持たない)。設定タブを開くたびにここを読む
- 開発中(start.bat。exe ではない)は使えない(登録する exe が無いため)
- アンインストールすると、インストーラーがこの値を消す(画面からオンにした場合も)

- available(): 使えるか(exe で動いているか)
- is_enabled(): 一覧に入っているか
- set_enabled(on): 入れる / 消す。失敗したら OSError
"""

import sys
import winreg

from edition import EDITION
from paths import FROZEN

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "WhisperKey GPU" if EDITION == "gpu" else "WhisperKey CPU"   # インストーラーの MyAppName と合わせる
# タスクマネージャーの「スタートアップ アプリ」で無効にすると、Run の値は残したまま、ここに「無効」の印が付く
# (値の先頭の 1 バイトが偶数なら有効、奇数なら無効)
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"


def available():
    return FROZEN


def _disabled_by_windows():
    """タスクマネージャーなどで無効にされているか"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY) as key:
            data, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(data) and data[0] % 2 == 1
    except (FileNotFoundError, TypeError, IndexError):
        return False


def is_enabled():
    """一覧に入っていて、タスクマネージャーなどで無効にされていなければ True"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return False
    return not _disabled_by_windows()


def set_enabled(on):
    """オンなら一覧に入れて、「無効」の印も外す(タスクマネージャーで無効にしたものも、ここから戻せるように)。オフなら消す"""
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if on:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, f'"{sys.executable}"')
        else:
            try:
                winreg.DeleteValue(key, VALUE_NAME)
            except FileNotFoundError:
                pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
    except FileNotFoundError:
        pass
