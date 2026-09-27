"""
システムトレイアイコン
仕様:
- 右クリックメニュー: 「設定を開く」「再起動」「終了」の3項目
- ツールチップ: "WhisperKey"
- アイコン: assets/stray_icon.png
- 「設定を開く」は本体の窓を設定タブで前に出す(最小化されていれば元に戻す)
- 「再起動」は restart.bat を起動してプロセス再起動
- 「終了」は os._exit(0) で即終了
"""

import os
import sys
import subprocess
import threading
import pystray
from PIL import Image

import paths
import main_window


# アイコンファイルパス
_ICON_PATH = paths.asset("stray_icon.png")


def _open_config(icon, item):
    """「設定を開く」: 本体の窓を設定タブで前に出す"""
    main_window.show("settings")


def open_config_app():
    """今の設定画面(設定exeまたは設定スクリプト)を起動する。設定タブの移植が終わるまでのつなぎ"""
    # コンソールウィンドウを出さないフラグ
    creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    
    try:
        if getattr(sys, "frozen", False):
            # exe化後: 設定exeを起動
            subprocess.Popen(
                [paths.CONFIG_EXE],
                creationflags=creation_flags,
                close_fds=True,
            )
        else:
            # 開発中: pythonで設定スクリプトを起動
            subprocess.Popen(
                [sys.executable, paths.CONFIG_SCRIPT],
                creationflags=creation_flags,
                close_fds=True,
            )
    except Exception as e:
        print(f"設定画面の起動に失敗: {e}")


def _restart(icon, item):
    """「再起動」"""
    restart_app()


def restart_app():
    """restart.bat を起動してプロセスを再起動する。

    ショートカットキーが効かなくなる症状への対処用。
    設定画面でモデルを変えたあとの再起動にも使う。
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
    
    # 右クリックメニュー
    menu = pystray.Menu(
        pystray.MenuItem("設定を開く", _open_config),
        pystray.MenuItem("再起動", _restart),
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
    icon = _build_icon()
    
    thread = threading.Thread(
        target=icon.run,
        daemon=True,  # メインプロセス終了時に自動終了
    )
    thread.start()
    
    return icon
