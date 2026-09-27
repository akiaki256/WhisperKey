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

import pyperclip
import webview

import audio
import audio_devices
import command
import config
import config_store
import convert_dict
import history
import key_shortcut
import paths
import sounds
import tray_icon

_state_manager = key_shortcut.MainStateManager()


_window = None
_loaded_model = None  # 起動時に読み込んだモデル。設定と違えば再起動が必要
_shortcut_errors = {}  # 起動時にショートカットキーを登録できなかった {役割: 理由("taken" など)}。登録できたら消す

# ショートカットの役割ごとの、config の項目名と画面での名前(key_shortcut.ACTIONS と合わせる)
SHORTCUT_CONFIG_KEYS = {"toggle": "shortcut_key", "mode": "mode_key", "undo": "undo_key"}
SHORTCUT_LABELS = {"toggle": "音声入力", "mode": "入力モード切り替え", "undo": "直前の入力を取り消す"}

# 画面から変えてよい項目(インジケーターの位置などは画面から変えない)
EDITABLE_KEYS = {
    "volume_threshold", "silence_duration", "audio_device_name", "language", "model_size", "theme",
    "history_enabled", "history_limit", "push_to_talk", "indicator_mode",
    "sound_startup", "sound_on", "sound_off", "sound_padding", "clipboard_private",
}

# 窓の下地の色(画面の読み込みが終わるまでの一瞬に見える色)。style.css の --bg と合わせる
BG_LIGHT = "#F3F3F3"
BG_DARK = "#202020"


def _model_list():
    """モデルの一覧 [{"value", "name", "desc"}, ...](モデルタブのカード用)"""
    return [
        {"value": value, "name": name, "desc": desc}
        for value, name, desc in config_store.model_choices()
    ]


def _call_js(function_name, value):
    """画面の JS の関数を呼ぶ。value は JSON にして渡す"""
    if _window is None:
        return
    # evaluate_js は画面の読み込みが終わるまで待つことがある。
    # 呼んだ側(録音や文字起こしの係など)を止めないよう、別のスレッドで呼ぶ
    threading.Thread(
        target=_window.evaluate_js,
        args=(f"{function_name}({json.dumps(value)})",),
        daemon=True,
    ).start()


def _on_config_changed(changed):
    """設定が変わったら画面に知らせる(録音の係がマイクを「既定」に戻したときなど)"""
    _call_js("onSettingsChanged", changed)


def _on_history_changed(entries):
    """入力履歴が変わったら画面の一覧を更新する"""
    _call_js("onHistoryChanged", entries)


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

    def get_settings(self):
        """設定タブを作るのに必要なものをまとめて返す(今の値・範囲・選択肢)"""
        values = config.get_all()
        return {
            "values": {key: values[key] for key in EDITABLE_KEYS},
            # ショートカットは {役割: キー}。変えるときは end_shortcut_capture から
            "shortcuts": {action: values[key] for action, key in SHORTCUT_CONFIG_KEYS.items()},
            "shortcut_errors": _shortcut_errors,
            "shortcut_labels": SHORTCUT_LABELS,
            "volume": {"min": config_store.VOLUME_THRESHOLD_MIN, "max": config_store.VOLUME_THRESHOLD_MAX},
            "silence": {
                "min": config_store.SILENCE_DURATION_MIN,
                "max": config_store.SILENCE_DURATION_MAX,
                "step": config_store.SILENCE_DURATION_STEP,
            },
            "languages": config_store.LANGUAGE_CHOICES,
            "models": _model_list(),
            "themes": config_store.THEME_CHOICES,
            "indicator_modes": config_store.INDICATOR_MODE_CHOICES,
            "sounds": sounds.list_sounds(),
            "history_limits": config_store.HISTORY_LIMIT_CHOICES,
            "mics": self.get_mics(),
            "restart_needed": values["model_size"] != _loaded_model,
        }

    def get_level(self):
        """今の音量(しきい値と同じ物差し)。設定タブを開いているあいだ、画面が 50ms ごとに取りに来る"""
        return audio.get_level()

    def play_sound(self, name):
        """効果音の試し聞き"""
        sounds.play_file(name)

    def get_mics(self):
        """今つながっているマイクの一覧(名前)。先頭は「既定のデバイスに自動接続」。更新ボタンからも呼ばれる"""
        return audio_devices.get_device_name_list()

    def update_setting(self, key, value):
        """一つの項目を変えて保存する。直したあとの値を返す(画面はその値を表示し直す)"""
        if key not in EDITABLE_KEYS:
            return {"error": f"変更できない項目です: {key}"}

        try:
            if key == "push_to_talk":
                _state_manager.set_push_to_talk(bool(value))  # オンにしたら録音をオフにそろえる処理も一緒に
            values = config.update({key: value})
            if key == "history_limit":
                history.trim(values["history_limit"])  # あふれた古い履歴を消す(画面で確認済み)
        except OSError as e:
            return {"error": f"設定の保存に失敗しました: {e}"}
        return {
            "value": values[key],
            "restart_needed": values["model_size"] != _loaded_model,
        }

    def restart(self):
        tray_icon.restart_app()

    # ---- 入力履歴 ----

    def get_history(self):
        return history.get()

    def clear_history(self):
        try:
            history.clear()
        except OSError as e:
            return {"error": f"入力履歴の消去に失敗しました: {e}"}
        return {}

    def copy_text(self, text):
        """履歴の文章をクリップボードにコピーする"""
        pyperclip.copy(text)

    # ---- 音声実行 ----

    def get_commands(self):
        return {"rows": command.get_rows(), "types": config_store.COMMAND_TYPES}

    def save_commands(self, rows):
        """一覧をまるごと保存する"""
        try:
            command.save_rows(rows)
        except ValueError as e:
            return {"error": str(e)}
        except OSError as e:
            return {"error": f"音声実行の保存に失敗しました: {e}"}
        return {}

    def choose_file(self):
        """「参照」ボタン。選ばれたファイルのパス(やめたら None)"""
        paths_chosen = _window.create_file_dialog(webview.FileDialog.OPEN)
        return paths_chosen[0] if paths_chosen else None

    # ---- 音声辞書 ----

    def get_dict(self):
        """[{"after": 変換後, "befores": [変換前, ...]}, ...]"""
        return convert_dict.get_groups()

    def save_dict(self, groups):
        """辞書をまるごと保存する(数十行なので、一項目ずつではなく全体を書き直す)"""
        try:
            convert_dict.save_groups(groups)
        except ValueError as e:
            return {"error": str(e)}
        except OSError as e:
            return {"error": f"辞書の保存に失敗しました: {e}"}
        return {}

    # ---- ショートカットキー(キーを押して決める) ----
    # 始めるときに全部の役割の登録を外し(どのキーも画面に届くように)、終わるときに登録し直す

    def begin_shortcut_capture(self):
        _state_manager.suspend_all_shortcuts()

    def end_shortcut_capture(self, action, key_str):
        """役割 action に key_str を登録して保存する。None なら取り消し、"" なら割り当てない。
        使えない・登録できなかったときは、元のキーを登録し直してエラーを返す"""
        config_key = SHORTCUT_CONFIG_KEYS[action]
        old = config.get(config_key)
        value = old
        problem = None

        if key_str is not None and key_str != old:
            problem = _check_shortcut(action, key_str)
            if problem is None:
                error = _state_manager.register_shortcut(action, key_str)
                if error is None:
                    value = key_str
                else:
                    problem = "ほかのソフトが使用中です" if error[0] == "taken" else f"登録できませんでした: {error[1]}"

        if value == old:
            if _state_manager.register_shortcut(action, old) is None:
                _shortcut_errors.pop(action, None)  # 起動時に取られていたキーが、あとで空いた場合も
            else:
                problem = (problem + "。" if problem else "") + "元のキーも登録できませんでした。別のキーを選んでください"
        else:
            _shortcut_errors.pop(action, None)
            try:
                config.update({config_key: value})
            except OSError as e:
                problem = f"設定の保存に失敗しました(このキーは次の起動まで有効です): {e}"

        # キーを決めているあいだ外していた、ほかの役割を登録し直す
        for other, other_config_key in SHORTCUT_CONFIG_KEYS.items():
            if other != action and _state_manager.register_shortcut(other, config.get(other_config_key)) is None:
                _shortcut_errors.pop(other, None)

        return {"value": value, "error": problem}


def _check_shortcut(action, key_str):
    """画面で選ばれたキーを、その役割に使ってよいか。よければ None、だめなら理由の文"""
    if key_str == "":
        return "音声入力は、割り当てないにはできません" if action == "toggle" else None
    problem = key_shortcut.check_new_shortcut(key_str)
    if problem:
        return problem
    for other, other_config_key in SHORTCUT_CONFIG_KEYS.items():
        if other != action and config.get(other_config_key) == key_str:
            return f"「{SHORTCUT_LABELS[other]}」と同じキーです"
    return None


def create(loaded_model, shortcut_errors=None):
    """窓を作る(表示されるのは start() のあと)

    shortcut_errors: 起動時にショートカットキーを登録できなかった役割と理由 {役割: "taken" など}。
    あれば画面はショートカットタブを開いて知らせる
    """
    global _window, _loaded_model, _shortcut_errors
    _loaded_model = loaded_model
    _shortcut_errors = dict(shortcut_errors or {})
    config.add_listener(_on_config_changed)
    history.add_listener(_on_history_changed)

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
