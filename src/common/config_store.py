"""
設定(config.json)の保管係
本体の各係と画面(設定タブなど)から使う。初期値・選択肢・範囲はすべてここで持つ。

- load(): ファイルを読み、初期値の上に重ね、おかしな値を直して返す
    ファイルが無ければ初期値で作る。書式が壊れていれば ConfigError
    → アップデートで項目が増えても、古い config.json で落ちない
- save(): 値を直してから、一時ファイル経由で書き込む
    → 書き込みの途中で落ちても、config.json が壊れない

値の直し方:
- 数値が範囲外なら、範囲の端に寄せる
- 型が違う、選択肢に無いなどで解釈できなければ、初期値に戻す
- 知らない項目は捨てる
"""

import json
import os

from edition import EDITION
from paths import CONFIG_JSON

# =====================================================
# 範囲・選択肢
# =====================================================

# 設定タブのレベルメーターの目盛りも、この範囲をそのまま使う(大きい声でも振り切らないよう、上は広めに)
VOLUME_THRESHOLD_MIN = 100
VOLUME_THRESHOLD_MAX = 15000

SILENCE_DURATION_MIN = 0.3
SILENCE_DURATION_MAX = 5.0
SILENCE_DURATION_STEP = 0.1

# 入力補正の時間切れ(秒)。LLM がテキストを受け取ってから、これを過ぎたら補正をあきらめて元の文を入力する
LLM_TIMEOUT_MIN = 1.0
LLM_TIMEOUT_MAX = 20.0
LLM_TIMEOUT_STEP = 0.5

# サンプルレート(MME固定)
SAMPLE_RATE = 16000

DEFAULT_DEVICE_LABEL = "既定のデバイスに自動接続"

# 選択肢の形式: [(保存値, 表示ラベル), ...]
# モデルだけは [(保存値, 名前, 説明), ...](モデルタブで名前を大きく、説明を下に小さく見せる)
# CPU版の medium と kotoba は実験的に選べるだけ。Ryzen 5 3600(6 スレッド)で 3 秒の声に medium 6 秒、kotoba 10 秒(2026/09/27)
MODEL_CHOICES_CPU = [
    ("tiny", "tiny", "最速・軽量(精度は低め)"),
    ("base", "base", "バランス型(速度と精度の中間)"),
    ("small", "small", "高精度(処理はやや重い)"),
    ("medium", "medium",
     "【実験的】とても重いモデルです。かなり高性能な CPU でないと、入力までに 5 秒以上かかります"),
    ("kotoba-whisper-v2.0", "kotoba-whisper-v2.0",
     "【実験的】日本語専用の高精度モデル。とても重く、かなり高性能な CPU でないと、入力までに 10 秒以上かかります"),
]
MODEL_CHOICES_GPU = [
    ("tiny", "tiny", "最速・最軽量(精度は低め)"),
    ("base", "base", "とても軽量(精度はやや低め)"),
    ("small", "small", "高速・軽量"),
    ("medium", "medium", "バランス型(推奨)"),
    ("kotoba-whisper-v2.0", "kotoba-whisper-v2.0", "日本語専用。large-v3 に近い精度で、より速い"),
    ("large-v3-turbo", "large-v3-turbo", "多言語対応。large-v3 に近い精度で、より速い"),
    ("large-v3", "large-v3", "最高精度(処理はやや重い)"),
]
MODEL_DEFAULT_CPU = "base"
MODEL_DEFAULT_GPU = "medium"

LANGUAGE_CHOICES = [
    ("ja", "日本語"),
    ("en", "English"),
]
LANGUAGE_DEFAULT = "ja"

SHORTCUT_DEFAULT = "f9"
UNDO_KEY_DEFAULT = "f10"  # 直前の入力を取り消す。"" なら割り当てない
MODE_KEY_DEFAULT = "shift+f9"  # 入力モード切り替え(通常 ⇔ プッシュトゥトーク)。"" なら割り当てない
CANDIDATES_KEY_DEFAULT = "f8"  # 候補を出す(GPU版)。"" なら割り当てない

# 本体の窓の見た目
THEME_CHOICES = [
    ("system", "システム設定に合わせる"),
    ("light", "ライト"),
    ("dark", "ダーク"),
]
THEME_DEFAULT = "system"

# インジケーターの表示方法
INDICATOR_MODE_CHOICES = [
    ("dot", "丸"),
    ("panel", "操作パネル"),
    ("hidden", "表示しない"),
]
INDICATOR_MODE_DEFAULT = "dot"

# 音声実行(command_dict.csv)の種類
COMMAND_TYPES = [
    ("url", "URLを開く"),
    ("file", "ファイルを開く"),
]


class ConfigError(Exception):
    """config.json が読めないときの例外"""
    pass


def model_choices():
    """現在の edition で選べるモデル"""
    return MODEL_CHOICES_CPU if EDITION == "cpu" else MODEL_CHOICES_GPU


def defaults():
    """初期値の一覧"""
    return {
        "volume_threshold": 500,
        "silence_duration": 1.3,
        "audio_device_index": None,
        "audio_device_name": DEFAULT_DEVICE_LABEL,
        "audio_device_sample_rate": SAMPLE_RATE,
        "shortcut_key": SHORTCUT_DEFAULT,
        "undo_key": UNDO_KEY_DEFAULT,
        "mode_key": MODE_KEY_DEFAULT,
        "candidates_key": CANDIDATES_KEY_DEFAULT,
        # True なら音声入力のキーを押している間だけ録音する(False は押すたびにオン/オフ)
        "push_to_talk": False,
        # True なら、入力する直前に「。」を消す(最後は消し、文と文の間は半角スペースにする)
        "remove_periods": False,
        # True なら、入力する直前に「、」を全部消す
        "remove_commas": False,
        # 効果音(assets/sounds の wav のファイル名)。"" なら鳴らさない
        "sound_startup": "起動(デフォルト).wav",
        "sound_on": "開始(デフォルト).wav",
        "sound_off": "停止(デフォルト).wav",
        # 効果音の前後に無音をつける(ワイヤレスイヤホンが音の頭を取りこぼさないように)
        "sound_padding": True,
        # 貼り付けた音声入力の文字を、Win + V の履歴・クラウド同期に残さない
        "clipboard_private": True,
        "language": LANGUAGE_DEFAULT,
        "model_size": MODEL_DEFAULT_CPU if EDITION == "cpu" else MODEL_DEFAULT_GPU,
        # インジケーターの表示方法と位置(画面の左上からのピクセル。丸と操作パネルで共通)。つまんで動かすと保存される
        "indicator_mode": INDICATOR_MODE_DEFAULT,
        "indicator_x": 5,
        "indicator_y": 20,
        # 「候補を出す」の窓の位置(横の真ん中と下の端のピクセル)。None なら画面の中央下。つまんで動かすと保存される
        "candidates_x": None,
        "candidates_y": None,
        "theme": THEME_DEFAULT,
        # 入力履歴(history.json)。オフでも今ある履歴には触らない。件数は history.LIMIT で決まっている
        "history_enabled": True,
        # 入力補正(GPU版のみ)。音声認識の結果をローカル LLM で直す。直前の入力を入力履歴から取るので、履歴のオンが要る
        "llm_correction": False,
        "llm_timeout": 3.0,
        # 句読点補正(入力補正がオンのときだけ動く)。Whisper の句読点をはがして、LLM に「、」「。」を付け直させる
        "llm_punctuation": True,
    }


# =====================================================
# 値の直し方
# =====================================================

def _is_number(v):
    # True/False も int の仲間なので除外する
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _fix_int_in_range(v, min_val, max_val, default):
    if not _is_number(v):
        return default
    return max(min_val, min(max_val, int(v)))


def _fix_int(v, default):
    # 画面の位置など、負の値もありうる整数(メインより左や上にあるモニター)
    if not _is_number(v):
        return default
    return int(v)


def _fix_optional_int(v):
    # 整数か None(「まだ決まっていない」)。それ以外は None
    return int(v) if _is_number(v) else None


def _fix_silence(v, default):
    if not _is_number(v):
        return default
    v = max(SILENCE_DURATION_MIN, min(SILENCE_DURATION_MAX, float(v)))
    return round(v, 1)


def _fix_choice(v, choices, default):
    valid = [choice[0] for choice in choices]  # 先頭が保存値(モデルは説明つきの3つ組なので)
    return v if v in valid else default


def _fix_llm_timeout(v, default):
    # 範囲の端に寄せて、刻み(0.5 秒)にそろえる
    if not _is_number(v):
        return default
    v = max(LLM_TIMEOUT_MIN, min(LLM_TIMEOUT_MAX, float(v)))
    return round(v / LLM_TIMEOUT_STEP) * LLM_TIMEOUT_STEP


def _fix_device_index(v):
    # None は「既定のデバイス」
    if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
        return v
    return None


def _fix_positive_int(v, default):
    if isinstance(v, int) and not isinstance(v, bool) and v > 0:
        return v
    return default


def _fix_optional_text(v, default):
    # 空("")も正しい値として扱う(割り当てないキー、鳴らさない効果音など)。文字でなければ初期値に戻す
    return v.strip() if isinstance(v, str) else default


def _fix_bool(v, default):
    return v if isinstance(v, bool) else default


def _fix_text(v, default):
    return v if isinstance(v, str) and v.strip() else default


def normalize(raw):
    """初期値の上に raw を重ね、おかしな値を直した設定を返す"""
    d = defaults()
    merged = {**d, **{k: v for k, v in raw.items() if k in d}}

    return {
        "volume_threshold": _fix_int_in_range(
            merged["volume_threshold"], VOLUME_THRESHOLD_MIN, VOLUME_THRESHOLD_MAX, d["volume_threshold"]),
        "silence_duration": _fix_silence(merged["silence_duration"], d["silence_duration"]),
        "audio_device_index": _fix_device_index(merged["audio_device_index"]),
        "audio_device_name": _fix_text(merged["audio_device_name"], d["audio_device_name"]),
        "audio_device_sample_rate": _fix_positive_int(merged["audio_device_sample_rate"], d["audio_device_sample_rate"]),
        "shortcut_key": _fix_text(merged["shortcut_key"], d["shortcut_key"]),
        "undo_key": _fix_optional_text(merged["undo_key"], d["undo_key"]),
        "mode_key": _fix_optional_text(merged["mode_key"], d["mode_key"]),
        "candidates_key": _fix_optional_text(merged["candidates_key"], d["candidates_key"]),
        "push_to_talk": _fix_bool(merged["push_to_talk"], d["push_to_talk"]),
        "remove_periods": _fix_bool(merged["remove_periods"], d["remove_periods"]),
        "remove_commas": _fix_bool(merged["remove_commas"], d["remove_commas"]),
        "sound_startup": _fix_optional_text(merged["sound_startup"], d["sound_startup"]),
        "sound_on": _fix_optional_text(merged["sound_on"], d["sound_on"]),
        "sound_off": _fix_optional_text(merged["sound_off"], d["sound_off"]),
        "sound_padding": _fix_bool(merged["sound_padding"], d["sound_padding"]),
        "clipboard_private": _fix_bool(merged["clipboard_private"], d["clipboard_private"]),
        "language": _fix_choice(merged["language"], LANGUAGE_CHOICES, d["language"]),
        "model_size": _fix_choice(merged["model_size"], model_choices(), d["model_size"]),
        "indicator_mode": _fix_choice(merged["indicator_mode"], INDICATOR_MODE_CHOICES, d["indicator_mode"]),
        "indicator_x": _fix_int(merged["indicator_x"], d["indicator_x"]),
        "indicator_y": _fix_int(merged["indicator_y"], d["indicator_y"]),
        "candidates_x": _fix_optional_int(merged["candidates_x"]),
        "candidates_y": _fix_optional_int(merged["candidates_y"]),
        "theme": _fix_choice(merged["theme"], THEME_CHOICES, d["theme"]),
        "history_enabled": _fix_bool(merged["history_enabled"], d["history_enabled"]),
        "llm_correction": _fix_bool(merged["llm_correction"], d["llm_correction"]),
        "llm_timeout": _fix_llm_timeout(merged["llm_timeout"], d["llm_timeout"]),
        "llm_punctuation": _fix_bool(merged["llm_punctuation"], d["llm_punctuation"]),
    }


# =====================================================
# 読み書き
# =====================================================

def load():
    """config.json を読んで、直した設定を返す"""
    try:
        with open(CONFIG_JSON, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        config = defaults()
        try:
            save(config)
        except OSError as e:
            print(f"初期設定の書き込みに失敗(初期値のまま続行): {e}")
        return config
    except json.JSONDecodeError as e:
        raise ConfigError(f"config.json の書式が不正です({e})") from e

    if not isinstance(raw, dict):
        raise ConfigError("config.json の書式が不正です(中身が {...} の形になっていません)")

    return normalize(raw)


def save(config):
    """設定を直してから config.json に書き込む。失敗したら OSError"""
    data = normalize(config)
    os.makedirs(os.path.dirname(CONFIG_JSON), exist_ok=True)

    tmp_path = CONFIG_JSON + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, CONFIG_JSON)
