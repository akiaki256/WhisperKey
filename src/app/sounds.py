"""
効果音(assets/sounds の wav)

- 鳴らす場面は三つ: 起動したとき(sound_startup)、入力モードがオン(sound_on)、オフ(sound_off)
  config の値は wav のファイル名。"" なら鳴らさない
- 選べるのは assets/sounds にある wav。利用者が wav を足せば、そのまま一覧に出る(paths.SOUNDS_DIR)
- 鳴らすのは winsound.PlaySound で、待たずに次へ進む(以前の Beep は鳴り終わるまで止まっていた)
  ファイルが無い・壊れているときは、何も鳴らさない(Windows の標準の音も鳴らさない)
"""

import os
import winsound

import config
from paths import SOUNDS_DIR

# 鳴らす場面と、config の項目名
SOUND_KEYS = {
    "startup": "sound_startup",
    "on": "sound_on",
    "off": "sound_off",
}

_FLAGS = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT


def list_sounds():
    """assets/sounds にある wav のファイル名(名前順)"""
    try:
        return sorted(name for name in os.listdir(SOUNDS_DIR) if name.lower().endswith(".wav"))
    except FileNotFoundError:
        return []


def play_file(name):
    """wav を一つ鳴らす。"" なら何もしない"""
    if not name:
        return
    path = os.path.join(SOUNDS_DIR, name)
    if not os.path.exists(path):
        print(f"効果音が見つかりません: {path}")
        return
    try:
        winsound.PlaySound(path, _FLAGS)
    except RuntimeError as e:
        print(f"効果音を鳴らせませんでした: {path}: {e}")


def play(scene):
    """場面("startup" / "on" / "off")に選ばれている音を鳴らす"""
    play_file(config.get(SOUND_KEYS[scene]))
