"""
本体のウィンドウ(pywebview)

- 画面は src/ui の HTML/CSS/JS。JS からは window.pywebview.api.<メソッド名>() で Api クラスを呼べる
- ヘッダーは HTML で自作する。ボタンを「最小化」と「×」の2つだけにするため、枠なしの窓にしている
  (枠ありで最大化だけを消すことはできず、灰色のボタンが残ってしまう)
- ×はアプリごと終了する。起動中はモデルが VRAM を占有し続けるので、トレイに隠れる方式にはしない
- start() はメインスレッドで呼ぶ(窓が閉じられるまで戻らない)
- ほかのスレッド(トレイなど)から窓を操作するときは show() を使う
"""

import base64
import json
import os
import threading
import winreg

import pyperclip
import webview

import audio
import audio_devices
import autostart
import command
import config
import config_store
import convert_dict
import history
import key_shortcut
import llm_correct
import llm_vocab
import model
import model_store
import paths
import sounds
import tray_icon
from edition import EDITION
from version import VERSION

_state_manager = key_shortcut.MainStateManager()


_window = None
_model_loading = False  # 起動したあとにモデルを読み込んでいる途中か(ダウンロードが終わったあとなど)
_shortcut_errors = {}  # 起動時にショートカットキーを登録できなかった {役割: 理由("taken" など)}。登録できたら消す
_downloading = None    # ダウンロード中のモデルの名前(一度に一つだけ)

# ショートカットの役割ごとの、config の項目名と画面での名前(key_shortcut.ACTIONS と合わせる)
# 「候補を出す」は GPU版だけ(入力補正の同音異義語の確かめから候補を作るため)
SHORTCUT_CONFIG_KEYS = {"toggle": "shortcut_key", "mode": "mode_key", "undo": "undo_key"}
SHORTCUT_LABELS = {"toggle": "音声入力", "mode": "入力モード切り替え", "undo": "直前の入力を取り消す"}
if EDITION == "gpu":
    SHORTCUT_CONFIG_KEYS["candidates"] = "candidates_key"
    SHORTCUT_LABELS["candidates"] = "候補を出す"

# 画面から変えてよい項目(インジケーターの位置などは画面から変えない)
EDITABLE_KEYS = {
    "volume_threshold", "silence_duration", "audio_device_name", "language", "model_size", "theme",
    "history_enabled", "push_to_talk", "remove_periods", "indicator_mode",
    "sound_startup", "sound_on", "sound_off", "sound_padding", "clipboard_private",
    "llm_correction", "llm_timeout", "llm_punctuation",
}

# 窓の下地の色(画面の読み込みが終わるまでの一瞬に見える色)。style.css の --bg と合わせる
BG_LIGHT = "#F3F3F3"
BG_DARK = "#202020"


def _model_list():
    """モデルの一覧 [{"value", "name", "desc", "size", "downloaded", "downloading"}, ...](モデルタブのカード用)"""
    return [
        {
            "value": value,
            "name": name,
            "desc": desc,
            "size": model_store.MODELS[value]["size"],
            "downloaded": model_store.local_path(value) is not None,
            "downloading": value == _downloading,
        }
        for value, name, desc in config_store.model_choices()
    ]


def _llm_model():
    """入力補正のモデル(入力補正タブのカード用。形はモデルタブのカードと同じ)"""
    name = model_store.LLM_MODEL
    return {
        "value": name,
        "name": name,
        "size": model_store.MODELS[name]["size"],
        "downloaded": model_store.local_path(name) is not None,
        "downloading": name == _downloading,
    }


def _restart_needed(values):
    """モデルを切り替えたので再起動が必要か(まだ何も読み込まれていないときは、再起動しなくても読み込む)"""
    return model.is_ready() and values["model_size"] != model.loaded_name()


def _load_if_needed():
    """まだモデルが読み込まれておらず、選ばれているモデルが手元にあれば、別のスレッドで読み込む
    (選ばれているモデルが手元に無いまま起動し、あとでダウンロードしたとき・手元にあるモデルを選び直したとき)"""
    global _model_loading
    name = config.get("model_size")
    if model.is_ready() or _model_loading or model_store.local_path(name) is None:
        return
    _model_loading = True

    def load():
        global _model_loading
        _call_js("onModelLoading", name)
        try:
            model.set_model(model.load_model(name), name)
            _call_js("onModelReady", name)
        except model.ModelLoadError as e:
            print(f"モデルの読み込みに失敗: {name}: {e}")
            _call_js("onModelLoadFailed", {"name": name, "error": f"モデルを読み込めませんでした({e})"})
        finally:
            _model_loading = False

    threading.Thread(target=load, daemon=True).start()


def _download_in_background(name):
    """モデルを取りに行く(別のスレッドで)。進み具合と終わったことを画面に知らせる"""
    global _downloading
    try:
        model_store.download(name, on_progress=lambda p: _call_js("onModelProgress", {"name": name, "progress": p}))
        result = {"name": name, "ok": True}
        _load_if_needed()  # 選ばれているモデルがこれで手元にそろったなら、再起動せずに読み込む
    except Exception as e:
        print(f"モデルのダウンロードに失敗: {name}: {e}")
        result = {"name": name, "ok": False, "error": f"ダウンロードできませんでした。インターネットにつながっているか確かめてください({e})"}
    finally:
        _downloading = None
    _call_js("onModelDownloaded", result)


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


def _on_correction_status(status):
    """入力補正の準備中・準備完了・失敗を、入力補正タブで知らせる"""
    _call_js("onCorrectionStatus", status)


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
            # モデルがまだ読み込まれていない(選ばれているモデルが手元に無い)。読み込み中なら "loading"
            "model_state": "ready" if model.is_ready() else "loading" if _model_loading else "missing",
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
            "mics": self.get_mics(),
            # 入力補正タブ(GPU版だけ見せる)
            "edition": EDITION,
            "llm_model": _llm_model() if EDITION == "gpu" else None,
            "llm_timeout": {
                "min": config_store.LLM_TIMEOUT_MIN,
                "max": config_store.LLM_TIMEOUT_MAX,
                "step": config_store.LLM_TIMEOUT_STEP,
            },
            "correction_status": llm_correct.status(),
            "restart_needed": _restart_needed(values),
            # Windows の起動時に立ち上げる(本当の値はレジストリ。開発中は使えない)
            "autostart": {"available": autostart.available(), "enabled": autostart.is_enabled()},
            # タイトルバー: アイコンと「WhisperKey GPU v5.0.0」
            "app_title": f"WhisperKey {EDITION.upper()} v{VERSION}",
            "app_icon": _app_icon_data_url(),
        }

    def set_autostart(self, on):
        """Windows の起動時に立ち上げるかを変える。{"value": 今の状態} か {"error": 理由}"""
        if not autostart.available():
            return {"error": "開発中(start.bat)では使えません", "value": autostart.is_enabled()}
        try:
            autostart.set_enabled(bool(on))
        except OSError as e:
            return {"error": f"Windows の設定を変えられませんでした: {e}", "value": autostart.is_enabled()}
        return {"value": autostart.is_enabled()}

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

        if key == "model_size" and model_store.local_path(value) is None:
            return {"error": "このモデルはまだダウンロードしていません。先にダウンロードしてください"}

        # 入力補正をオンにできるのは、GPU版で、入力履歴がオン(直前の入力を履歴から取る)で、モデルが手元にあるとき
        if key == "llm_correction" and value:
            if EDITION != "gpu":
                return {"error": "入力補正は GPU版だけの機能です"}
            if not config.get("history_enabled"):
                return {"error": "入力補正を使うには、先に入力履歴をオンにしてください(入力履歴タブの一番下)"}
            if model_store.local_path(model_store.LLM_MODEL) is None:
                return {"error": "入力補正のモデルがまだありません。先にダウンロードしてください"}

        changes = {key: value}
        # 入力履歴をオフにしたら、入力補正もオフにする(画面には onSettingsChanged で届く)
        if key == "history_enabled" and not value and config.get("llm_correction"):
            changes["llm_correction"] = False

        try:
            if key == "push_to_talk":
                _state_manager.set_push_to_talk(bool(value))  # オンにしたら録音をオフにそろえる処理も一緒に
            values = config.update(changes)
            if key == "model_size":
                _load_if_needed()
        except OSError as e:
            return {"error": f"設定の保存に失敗しました: {e}"}
        return {
            "value": values[key],
            "restart_needed": _restart_needed(values),
        }

    def reset_window_positions(self):
        """インジケーターと候補の窓の位置を初期値に戻す(画面の外に出て見つからなくなったときの逃げ道)
        インジケーターは config の変わったのを見て、その場で動く。候補の窓は次に開いたときから"""
        d = config_store.defaults()
        try:
            config.update({k: d[k] for k in ("indicator_x", "indicator_y", "candidates_x", "candidates_y")})
        except OSError as e:
            return {"error": f"設定の保存に失敗しました: {e}"}
        return {}

    def restart(self):
        tray_icon.restart_app()

    # ---- モデルのダウンロードと削除 ----

    def download_model(self, name):
        """ダウンロードを始める(終わるのを待たない)。進み具合は onModelProgress、終わったら onModelDownloaded で知らせる
        一度に取りに行くのは一つだけ"""
        global _downloading
        if name not in model_store.MODELS:
            return {"error": f"知らないモデルです: {name}"}
        if _downloading is not None:
            return {"error": "ほかのモデルをダウンロード中です。終わってからもう一度押してください"}
        _downloading = name
        threading.Thread(target=_download_in_background, args=(name,), daemon=True).start()
        return {}

    def delete_model(self, name):
        """手元のモデルを消す。選ばれているモデル・今使っているモデル・ダウンロード中のモデルは消せない"""
        if name not in model_store.MODELS:
            return {"error": f"知らないモデルです: {name}"}
        if name == config.get("model_size"):
            return {"error": "選ばれているモデルは削除できません。ほかのモデルを選んでから削除してください"}
        if name == model.loaded_name():
            return {"error": "このモデルは今使われています。再起動したあとに削除してください"}
        if name == _downloading:
            return {"error": "ダウンロード中のモデルは削除できません"}
        if name == model_store.LLM_MODEL and config.get("llm_correction"):
            return {"error": "入力補正がオンの間は削除できません。入力補正をオフにしてから削除してください"}
        try:
            model_store.delete(name)
        except OSError as e:
            return {"error": f"モデルの削除に失敗しました: {e}"}
        return {}

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

    # ---- 入力補正の「よく使う言葉」 ----

    def get_vocab(self):
        """[{"word": 言葉, "reading": よみがな}, ...]"""
        return llm_vocab.get_rows()

    def save_vocab(self, rows):
        """一覧をまるごと保存する"""
        try:
            llm_vocab.save_rows(rows)
        except OSError as e:
            return {"error": f"よく使う言葉の保存に失敗しました: {e}"}
        return {}

    def import_vocab_from_dict(self):
        """音声辞書の変換後のうち、前回取り込んだあとに増えたものを足す。足した数と、足したあとの一覧を返す"""
        afters = [group["after"] for group in convert_dict.get_groups()]
        try:
            added = llm_vocab.import_from_dict(afters)
        except OSError as e:
            return {"error": f"よく使う言葉の保存に失敗しました: {e}"}
        return {"added": added, "rows": llm_vocab.get_rows()}

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


def _app_icon_data_url():
    """タイトルバーのアイコン(assets/app_icon.png)を、画面にそのまま渡せる形で。読めなければ None(文字だけ出す)
    画面(src/ui)と assets は別の場所なので、絵を二重に持たずに済むよう、ここで読んで渡す"""
    try:
        with open(paths.asset("app_icon.png"), "rb") as f:
            return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    except OSError as e:
        print(f"タイトルバーのアイコンを読めませんでした: {e}")
        return None


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


def create(shortcut_errors=None):
    """窓を作る(表示されるのは start() のあと)
    選ばれているモデルが手元に無いかは、画面が get_settings の model_state で知る(モデルタブを開いて知らせる)

    shortcut_errors: 起動時にショートカットキーを登録できなかった役割と理由 {役割: "taken" など}。
    あれば画面はショートカットタブを開いて知らせる
    """
    global _window, _shortcut_errors
    _shortcut_errors = dict(shortcut_errors or {})
    config.add_listener(_on_config_changed)
    history.add_listener(_on_history_changed)
    llm_correct.add_listener(_on_correction_status)

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
