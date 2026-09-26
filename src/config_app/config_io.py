"""
config.json の読み書き
範囲外値は黙ってクランプする(仕様書§4.2)

edition は edition.py から取得する(config.json では扱わない)。
"""

import json
import sys
from CTkMessagebox import CTkMessagebox

import constants as C
from edition import EDITION


def _clamp(value, min_val, max_val):
    """値を範囲内にクランプ"""
    return max(min_val, min(max_val, value))


def _clamp_volume(value):
    """音量閾値をクランプ。数値化できないならデフォルト値"""
    try:
        v = int(value)
    except (ValueError, TypeError):
        v = C.VOLUME_THRESHOLD_MIN
    return _clamp(v, C.VOLUME_THRESHOLD_MIN, C.VOLUME_THRESHOLD_MAX)


def _clamp_silence(value):
    """無音時間をクランプ。0.1刻みに丸める"""
    try:
        v = float(value)
    except (ValueError, TypeError):
        v = C.SILENCE_DURATION_MIN
    v = _clamp(v, C.SILENCE_DURATION_MIN, C.SILENCE_DURATION_MAX)
    return round(v, 1)


def _clamp_language(value):
    """言語を選択肢内にクランプ"""
    valid = [tag for tag, _ in C.LANGUAGE_CHOICES]
    if value in valid:
        return value
    return C.LANGUAGE_DEFAULT


def _clamp_model(value):
    """モデルサイズを現在のedition別の選択肢内にクランプ"""
    if EDITION == "cpu":
        valid = [tag for tag, _ in C.MODEL_CHOICES_CPU]
        default = C.MODEL_DEFAULT_CPU
    else:  # gpu
        valid = [tag for tag, _ in C.MODEL_CHOICES_GPU]
        default = C.MODEL_DEFAULT_GPU
    
    if value in valid:
        return value
    return default


def load_config():
    """
    config.json を読み込み、範囲外値はクランプして返す。
    ファイル不在・書式不正は致命エラーでアプリ終了。
    
    戻り値には edition は含まれない(edition.py から直接取得すること)。
    """
    try:
        with open(C.CONFIG_JSON_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except FileNotFoundError:
        CTkMessagebox(
            title="設定ファイルエラー",
            message="config.jsonが見つかりません。\n終了します。",
            icon="cancel",
            option_1="OK",
        )
        sys.exit(1)
    except json.JSONDecodeError:
        CTkMessagebox(
            title="設定ファイルエラー",
            message="config.jsonの書式が不正です。\n終了します。",
            icon="cancel",
            option_1="OK",
        )
        sys.exit(1)
    
    # 各値をクランプ
    config = {
        "volume_threshold": _clamp_volume(raw.get("volume_threshold")),
        "silence_duration": _clamp_silence(raw.get("silence_duration")),
        "audio_device_index": raw.get("audio_device_index"),
        "audio_device_name": raw.get("audio_device_name", C.DEFAULT_DEVICE_LABEL),
        "audio_device_sample_rate": raw.get("audio_device_sample_rate", C.SAMPLE_RATE),
        "shortcut_key": raw.get("shortcut_key", "f9"),
        "language": _clamp_language(raw.get("language")),
        "model_size": _clamp_model(raw.get("model_size")),
    }
    
    return config


def save_config(config):
    """
    config.json に書き込み。
    書き込み失敗時は例外を投げる(呼び出し側で処理)。
    """
    with open(C.CONFIG_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
