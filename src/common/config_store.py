"""
設定(config.json)の保管係
本体と設定画面の両方から使う。初期値・選択肢・範囲はすべてここで持つ。

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

VOLUME_THRESHOLD_MIN = 100
VOLUME_THRESHOLD_MAX = 10000

SILENCE_DURATION_MIN = 0.3
SILENCE_DURATION_MAX = 5.0
SILENCE_DURATION_STEP = 0.1

# サンプルレート(MME固定)
SAMPLE_RATE = 16000

DEFAULT_DEVICE_LABEL = "既定のデバイスに自動接続"

# 形式: [(保存値, 表示ラベル), ...]
MODEL_CHOICES_CPU = [
    ("tiny", "tiny: 最速・軽量(精度は低め)"),
    ("base", "base: バランス型(速度と精度の中間)"),
    ("small", "small: 高精度(処理はやや重い)"),
]
MODEL_CHOICES_GPU = [
    ("small", "small: 高速・軽量"),
    ("medium", "medium: バランス型(推奨)"),
    ("large-v3", "large-v3: 最高精度(処理はやや重い)"),
]
MODEL_DEFAULT_CPU = "base"
MODEL_DEFAULT_GPU = "medium"

LANGUAGE_CHOICES = [
    ("ja", "日本語"),
    ("en", "English"),
]
LANGUAGE_DEFAULT = "ja"

SHORTCUT_DEFAULT = "f9"


class ConfigError(Exception):
    """config.json が読めないときの例外"""
    pass


def model_choices():
    """現在の edition で選べるモデル"""
    return MODEL_CHOICES_CPU if EDITION == "cpu" else MODEL_CHOICES_GPU


def defaults():
    """初期値の一覧"""
    return {
        "volume_threshold": 1700,
        "silence_duration": 1.3,
        "audio_device_index": None,
        "audio_device_name": DEFAULT_DEVICE_LABEL,
        "audio_device_sample_rate": SAMPLE_RATE,
        "shortcut_key": SHORTCUT_DEFAULT,
        "language": LANGUAGE_DEFAULT,
        "model_size": MODEL_DEFAULT_CPU if EDITION == "cpu" else MODEL_DEFAULT_GPU,
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


def _fix_silence(v, default):
    if not _is_number(v):
        return default
    v = max(SILENCE_DURATION_MIN, min(SILENCE_DURATION_MAX, float(v)))
    return round(v, 1)


def _fix_choice(v, choices, default):
    valid = [tag for tag, _ in choices]
    return v if v in valid else default


def _fix_device_index(v):
    # None は「既定のデバイス」
    if isinstance(v, int) and not isinstance(v, bool) and v >= 0:
        return v
    return None


def _fix_positive_int(v, default):
    if isinstance(v, int) and not isinstance(v, bool) and v > 0:
        return v
    return default


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
        "language": _fix_choice(merged["language"], LANGUAGE_CHOICES, d["language"]),
        "model_size": _fix_choice(merged["model_size"], model_choices(), d["model_size"]),
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
