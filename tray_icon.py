"""
システムトレイアイコン
仕様:
- 右クリックメニュー: 「設定を開く」「再起動」「終了」の3項目
- ツールチップ: "WhisperKey"
- アイコン: items/stray_icon.png
- 「再起動」は restart.bat を起動してプロセス再起動
- 「終了」は os._exit(0) で即終了
"""

import os
import sys
import subprocess
import threading
import pystray
from PIL import Image


def _get_resource_path(relative_path):
    """
    リソースファイルのパスを取得(frozen/開発両対応)。
    exe化後は _MEIPASS から、開発中はカレントディレクトリから探す。
    """
    if getattr(sys, "frozen", False):
        # PyInstallerで展開された一時ディレクトリ
        base_path = sys._MEIPASS
    else:
        # 開発中: カレントディレクトリ基準
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# アイコンファイルパス(frozen対応で解決)
_ICON_PATH = _get_resource_path(os.path.join("items", "stray_icon.png"))

# 設定exeのファイル名 / 開発中の設定スクリプトパス
_CONFIG_EXE_NAME = "Config.exe"
_CONFIG_SCRIPT_PATH = os.path.join("WhisperKey_config", "main_config.py")

# 再起動用バッチファイル (Config.exe とも共有)
_RESTART_BAT_NAME = "restart.bat"


def _open_config(icon, item):
    """「設定を開く」: 設定exeまたは設定スクリプトを起動"""
    # コンソールウィンドウを出さないフラグ
    creation_flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    
    try:
        if getattr(sys, "frozen", False):
            # exe化後: 設定exeを起動
            # exeと同じディレクトリから相対パスで起動
            exe_dir = os.path.dirname(sys.executable)
            config_exe_path = os.path.join(exe_dir, _CONFIG_EXE_NAME)
            subprocess.Popen(
                [config_exe_path],
                creationflags=creation_flags,
                close_fds=True,
            )
        else:
            # 開発中: pythonで設定スクリプトを起動
            subprocess.Popen(
                [sys.executable, _CONFIG_SCRIPT_PATH],
                creationflags=creation_flags,
                close_fds=True,
            )
    except Exception as e:
        print(f"設定画面の起動に失敗: {e}")


def _restart(icon, item):
    """「再起動」: restart.bat を起動してプロセスを再起動する。
    
    ショートカットキーが効かなくなる症状への対処用。
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
        exe_dir = os.path.dirname(sys.executable)
        bat_path = os.path.join(exe_dir, _RESTART_BAT_NAME)
        subprocess.Popen(
            [bat_path],
            creationflags=subprocess.CREATE_NO_WINDOW,
            cwd=exe_dir,
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
    メインスレッドは tkinter の mainloop でブロックする想定なので、
    pystray を daemon スレッドで動かす。
    """
    icon = _build_icon()
    
    thread = threading.Thread(
        target=icon.run,
        daemon=True,  # メインプロセス終了時に自動終了
    )
    thread.start()
    
    return icon
