"""
システムトレイアイコン
仕様:
- 右クリックメニュー: 「WhisperKey を開く」/ 区切り /「設定」「再起動」/ 区切り /「終了」
- アイコンを左クリックしても「WhisperKey を開く」(メニューでは太字)
- ツールチップ: "WhisperKey"
- アイコン: assets/stray_icon.png
- 「WhisperKey を開く」は本体の窓を前に出す(最小化されていれば元に戻す)。「設定」は設定タブで出す
- 「再起動」は restart.bat を起動してプロセス再起動
- 「終了」は os._exit(0) で即終了
- メニューの色は、本体の窓のテーマ(config の theme)に合わせる。変えたらその場で変わる
    「システム設定に合わせる」のときは起動時の Windows のモード(本体の窓の下地の色と同じ。Windows 側を切り替えたら、再起動のあとに合う)
    Windows 標準のメニューを暗くするには、uxtheme.dll の番号でしか呼べない関数を使う
    (SetPreferredAppMode = 135、FlushMenuThemes = 136。Windows 10 1903 以降。公式の説明は無いが、多くのアプリが使っている)
    呼べない Windows では何もしない(明るいメニューのまま動く)
"""

import ctypes
import os
import sys
import subprocess
import threading
import pystray
from PIL import Image

import config
import paths
import main_window


# アイコンファイルパス
_ICON_PATH = paths.asset("stray_icon.png")


# SetPreferredAppMode に渡す値
_FORCE_DARK = 2
_FORCE_LIGHT = 3


def _apply_menu_theme(theme):
    """メニューの色をテーマに合わせる。呼べない Windows では何もしない
    「システム設定に合わせる」は、Windows のモードを読んで暗い・明るいをはっきり決める
    (「Windows に従う」値は、メニューの持ち主の窓にも設定が要り、確実でないため。本体の窓の下地の色と同じ決め方)"""
    dark = theme == "dark" or (theme == "system" and main_window._system_is_dark())
    try:
        uxtheme = ctypes.WinDLL("uxtheme")
        set_preferred_app_mode = uxtheme[135]
        set_preferred_app_mode.argtypes = [ctypes.c_int]
        set_preferred_app_mode(_FORCE_DARK if dark else _FORCE_LIGHT)
        uxtheme[136]()   # FlushMenuThemes: 次に開くメニューから効かせる
    except (OSError, AttributeError) as e:
        print(f"メニューの色を変えられませんでした(明るいまま動きます): {e}")


def _on_config_changed(changed):
    if "theme" in changed:
        _apply_menu_theme(changed["theme"])


def _open_window(icon, item):
    """「WhisperKey を開く」: 本体の窓を前に出す(タブはそのまま)"""
    main_window.show()


def _open_config(icon, item):
    """「設定」: 本体の窓を設定タブで前に出す"""
    main_window.show("settings")


def _restart(icon, item):
    """「再起動」"""
    restart_app()


def restart_app():
    """restart.bat を起動してプロセスを再起動する。

    ショートカットキーが効かなくなる症状への対処用。
    モデルタブでモデルを変えたあとの再起動にも使う。
    restart.bat 側で taskkill → sleep → WhisperKey.exe 起動を実行するため、
    自プロセスは taskkill で強制終了される(os._exit は呼ばない)。
    
    開発中(frozen でない)の場合は restart.bat のパス解決が複雑なため、
    対症療法として終了のみ行う。
    """
    if not getattr(sys, "frozen", False):
        # 開発中は exe 構成ではないため、単に終了
        # (開発中に「再起動」ボタンを押す想定は薄い)
        print("開発中は再起動機能は無効です。手動で再起動してください。")
        return
    
    try:
        subprocess.Popen(
            [paths.RESTART_BAT],
            creationflags=subprocess.CREATE_NO_WINDOW,
            cwd=paths.APP_DIR,
            close_fds=True,
        )
        # restart.bat 側の taskkill で自プロセスは終了するため、
        # 明示的に os._exit は呼ばない
    except Exception as e:
        # バッチ起動に失敗した場合、プロセスは生き残る
        # ユーザーは手動で「終了」→再起動で対処可能
        print(f"再起動処理に失敗: {e}")


def _quit(icon, item):
    """「終了」: プロセスを即終了(os._exit)"""
    # システムトレイアイコンを先に停止
    try:
        icon.stop()
    except Exception:
        pass
    # プロセス全体を終了(全スレッドを強制終了)
    os._exit(0)


def _build_icon():
    """pystray.Iconインスタンスを構築して返す"""
    # アイコン画像の読込
    try:
        image = Image.open(_ICON_PATH)
    except Exception as e:
        print(f"アイコン画像の読込に失敗: {_ICON_PATH}: {e}")
        # フォールバック: 単色の小さな画像
        image = Image.new("RGB", (64, 64), color=(100, 100, 200))
    
    # 右クリックメニュー。default=True の項目は太字になり、アイコンの左クリックでも呼ばれる
    menu = pystray.Menu(
        pystray.MenuItem("WhisperKey を開く", _open_window, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("設定", _open_config),
        pystray.MenuItem("再起動", _restart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("終了", _quit),
    )
    
    # アイコン本体
    icon = pystray.Icon(
        name="WhisperKey",
        icon=image,
        title="WhisperKey",   # ツールチップ
        menu=menu,
    )
    
    return icon


def start_tray_in_background():
    """
    システムトレイを別スレッドで起動する。
    メインスレッドは本体の窓(pywebview)でブロックする想定なので、
    pystray を daemon スレッドで動かす。
    """
    _apply_menu_theme(config.get("theme"))
    config.add_listener(_on_config_changed)
    icon = _build_icon()

    thread = threading.Thread(
        target=icon.run,
        daemon=True,  # メインプロセス終了時に自動終了
    )
    thread.start()
    
    return icon
