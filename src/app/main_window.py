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
import threading
import winreg

import webview

import audio_devices
import config
import config_store
import key_shortcut
import paths
import tray_icon

_state_manager = key_shortcut.MainStateManager()


_window = None
_loaded_model = None  # 起動時に読み込んだモデル。設定と違えば再起動が必要
_shortcut_error = None  # 起動時にショートカットキーを登録できなかった理由("taken" など)。登録できたら None

# 画面から変えてよい項目(インジケーターの位置などは画面から変えない)
EDITABLE_KEYS = {"volume_threshold", "silence_duration", "audio_device_name", "language", "model_size", "theme"}

# 窓の下地の色(画面の読み込みが終わるまでの一瞬に見える色)。style.css の --bg と合わせる
BG_LIGHT = "#F3F3F3"
BG_DARK = "#202020"


def _model_list():
    """モデルの一覧を、名前と説明に分けて返す

    config_store のラベルは "large-v3: 最高精度(処理はやや重い)" の形(今の設定画面がそのまま使うため)。
    Config.exe を外したら、config_store の側で名前と説明を分けて持つようにする
    """
    models = []
    for value, label in config_store.model_choices():
        name, _, desc = label.partition(": ")
        models.append({"value": value, "name": name, "desc": desc})
    return models


def _on_config_changed(changed):
    """設定が変わったら画面に知らせる(録音の係がマイクを「既定」に戻したときなど)"""
    if _window is None:
        return
    # evaluate_js は画面の読み込みが終わるまで待つことがある。
    # 呼んだ側(録音の係など)を止めないよう、別のスレッドで呼ぶ
    threading.Thread(
        target=_window.evaluate_js,
        args=(f"onSettingsChanged({json.dumps(changed)})",),
        daemon=True,
    ).start()


def _system_is_dark():
    """Windows のアプリのモードがダークか"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


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

    def get_settings(self):
        """設定タブを作るのに必要なものをまとめて返す(今の値・範囲・選択肢)"""
        values = config.get_all()
        return {
            "values": {key: values[key] for key in EDITABLE_KEYS},
            "shortcut_key": values["shortcut_key"],  # 変えるときは end_shortcut_capture から
            "shortcut_error": _shortcut_error,
            "volume": {"min": config_store.VOLUME_THRESHOLD_MIN, "max": config_store.VOLUME_THRESHOLD_MAX},
            "silence": {
                "min": config_store.SILENCE_DURATION_MIN,
                "max": config_store.SILENCE_DURATION_MAX,
                "step": config_store.SILENCE_DURATION_STEP,
            },
            "languages": config_store.LANGUAGE_CHOICES,
            "models": _model_list(),
            "themes": config_store.THEME_CHOICES,
            "mics": self.get_mics(),
            "restart_needed": values["model_size"] != _loaded_model,
        }

    def get_mics(self):
        """今つながっているマイクの一覧(名前)。先頭は「既定のデバイスに自動接続」。更新ボタンからも呼ばれる"""
        return audio_devices.get_device_name_list()

    def update_setting(self, key, value):
        """一つの項目を変えて保存する。直したあとの値を返す(画面はその値を表示し直す)"""
        if key not in EDITABLE_KEYS:
            return {"error": f"変更できない項目です: {key}"}

        try:
            values = config.update({key: value})
        except OSError as e:
            return {"error": f"設定の保存に失敗しました: {e}"}
        return {
            "value": values[key],
            "restart_needed": values["model_size"] != _loaded_model,
        }

    def restart(self):
        tray_icon.restart_app()

    # ---- ショートカットキー(キーを押して決める) ----
    # 始めるときに今のキーの登録を外し(今のキーも画面に届くように)、終わるときに登録し直す

    def begin_shortcut_capture(self):
        _state_manager.suspend_shortcut()

    def end_shortcut_capture(self, key_str):
        """key_str を登録して保存する。None なら取り消し。
        使えない・登録できなかったときは、元のキーを登録し直してエラーを返す"""
        global _shortcut_error
        old = config.get("shortcut_key")
        problem = None

        if key_str and key_str != old:
            problem = key_shortcut.check_new_shortcut(key_str)
            if problem is None:
                error = _state_manager.register_shortcut(key_str)
                if error is None:
                    _shortcut_error = None
                    try:
                        config.update({"shortcut_key": key_str})
                    except OSError as e:
                        return {"value": key_str, "error": f"設定の保存に失敗しました(このキーは次の起動まで有効です): {e}"}
                    return {"value": key_str}
                problem = "ほかのソフトが使用中です" if error[0] == "taken" else f"登録できませんでした: {error[1]}"

        if _state_manager.register_shortcut(old) is None:
            _shortcut_error = None  # 起動時に取られていたキーが、あとで空いた場合
        else:
            problem = (problem + "。" if problem else "") + "元のキーも登録できませんでした。別のキーを選んでください"
        return {"value": old, "error": problem}


def create(loaded_model, shortcut_error=None):
    """窓を作る(表示されるのは start() のあと)

    shortcut_error: 起動時にショートカットキーを登録できなかった理由。
    あれば画面はショートカットタブを開いて知らせる
    """
    global _window, _loaded_model, _shortcut_error
    _loaded_model = loaded_model
    _shortcut_error = shortcut_error
    config.add_listener(_on_config_changed)

    theme = config.get("theme")
    dark = theme == "dark" or (theme == "system" and _system_is_dark())

    _window = webview.create_window(
        "WhisperKey",
        url=os.path.join(paths.UI_DIR, "index.html"),
        js_api=Api(),
        width=820,
        height=560,
        background_color=BG_DARK if dark else BG_LIGHT,
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
