"""
本体のウィンドウ(pywebview)

- 画面は src/ui の HTML/CSS/JS。JS からは window.pywebview.api.<メソッド名>() で Api クラスを呼べる
- ヘッダーは HTML で自作する。ボタンを「最小化」と「×」の2つだけにするため、枠なしの窓にしている
  (枠ありで最大化だけを消すことはできず、灰色のボタンが残ってしまう)
- ×はアプリごと終了する。起動中はモデルが VRAM を占有し続けるので、トレイに隠れる方式にはしない
- start() はメインスレッドで呼ぶ(窓が閉じられるまで戻らない)
- ほかのスレッド(トレイなど)から窓を操作するときは show() を使う
"""

import json
import os

import webview

import paths
import tray_icon


_window = None


class Api:
    """JS から呼ばれる窓口。

    窓(_window)は属性に持たない。pywebview は js_api の属性を
    たどって JS に公開しようとするため、モジュールの変数から参照する。
    """

    def minimize(self):
        _window.minimize()

    def close(self):
        _window.destroy()

    def open_legacy_config(self):
        """今の設定画面(Config.exe)を開く。設定タブの移植が終わるまでのつなぎ"""
        tray_icon.open_config_app()


def create():
    """窓を作る(表示されるのは start() のあと)"""
    global _window
    _window = webview.create_window(
        "WhisperKey",
        url=os.path.join(paths.UI_DIR, "index.html"),
        js_api=Api(),
        width=720,
        height=480,
        resizable=False,
        frameless=True,
        easy_drag=False,  # 窓全体ではなく、ヘッダーの pywebview-drag-region だけでつまめるようにする
    )
    return _window


def show(tab=None):
    """窓を前に出す。最小化されていれば元に戻す。tab を渡すとそのタブを開く"""
    if _window is None:
        return
    _window.restore()
    _window.show()
    if tab:
        _window.evaluate_js(f"showTab({json.dumps(tab)})")


def start():
    """窓を表示して、閉じられるまで待つ"""
    webview.start(gui="edgechromium")
