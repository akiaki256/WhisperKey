"""
定数定義モジュール
各モジュールから参照される設定値の集約

設定値の範囲・選択肢・初期値は common/config_store.py が持つ。
ここでは画面側で使う名前で参照できるようにしているだけ。
"""

import paths

# =====================================================
# 設定値の範囲・選択肢(config_store から)
# =====================================================
from config_store import (
    VOLUME_THRESHOLD_MIN,
    VOLUME_THRESHOLD_MAX,
    SILENCE_DURATION_MIN,
    SILENCE_DURATION_MAX,
    SILENCE_DURATION_STEP,
    SAMPLE_RATE,
    DEFAULT_DEVICE_LABEL,
    MODEL_CHOICES_CPU,
    MODEL_CHOICES_GPU,
    MODEL_DEFAULT_CPU,
    MODEL_DEFAULT_GPU,
    LANGUAGE_CHOICES,
    LANGUAGE_DEFAULT,
)

# =====================================================
# ショートカットキー選択肢
# =====================================================
MODIFIER_KEYS = ["なし", "Ctrl", "Alt", "Shift"]

MAIN_KEYS = (
    [f"F{i}" for i in range(1, 25)]
    + [chr(c) for c in range(ord("A"), ord("Z") + 1)]
    + [str(i) for i in range(10)]
    + ["Space", "Enter"]
)

# =====================================================
# コマンド種類
# =====================================================
from config_store import COMMAND_TYPES  # 本体と共通(common/config_store.py)

# tag → 表示名 の逆引き
COMMAND_TAG_TO_LABEL = {tag: label for tag, label in COMMAND_TYPES}
COMMAND_LABEL_TO_TAG = {label: tag for tag, label in COMMAND_TYPES}

# =====================================================
# Mutex名(多重起動防止)
# =====================================================
MUTEX_NAME_CONFIG = "Global\\WhisperKey_ConfigGUI"

# =====================================================
# ファイルパス
# =====================================================
CONFIG_JSON_PATH = paths.CONFIG_JSON
CONVERT_DICT_PATH = paths.CONVERT_DICT_CSV
COMMAND_DICT_PATH = paths.COMMAND_DICT_CSV
RESTART_BAT_PATH = paths.RESTART_BAT

# =====================================================
# ウィンドウ
# =====================================================
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 600
WINDOW_TITLE_BASE = "WhisperKey_設定"

EDITION_LABELS = {
    "cpu": "[CPU版]",
    "gpu": "[GPU版]",
}
EDITION_LABEL_UNKNOWN = "[不明]"
