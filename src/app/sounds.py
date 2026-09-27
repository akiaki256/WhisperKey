"""
効果音(assets/sounds の wav)

- 鳴らす場面は三つ: 起動したとき(sound_startup)、入力モードがオン(sound_on)、オフ(sound_off)
  config の値は wav のファイル名。"" なら鳴らさない
- 選べるのは assets/sounds にある wav。利用者が wav を足せば、そのまま一覧に出る(paths.SOUNDS_DIR)
- 鳴らすのは winsound.PlaySound で、待たずに次へ進む(以前の Beep は鳴り終わるまで止まっていた)
  録音は状態を変えた瞬間に始まっているので、効果音の長さは録音のタイミングに影響しない
  ファイルが無い・壊れているときは、何も鳴らさない(Windows の標準の音も鳴らさない)

ワイヤレスイヤホン対策(sound_padding):
- イヤホンは音が来てから起きるまでに時間がかかり、短い音の頭を取りこぼす
  鳴らすときに前後へ無音をつけて、無音のあいだにイヤホンを起こす
  前は聞こえるのが遅れるぶんシビアに、後ろは動作に影響しないのでたっぷり
- wav ファイルそのものは変えない(利用者が入れた wav にも効くように)。無音をつけた wav を
  一時フォルダ(temp/sounds)に作って鳴らす。メモリ上の音は「待たずに鳴らす」ができないため、ファイルにする
- 一度作ったものは使い回す。元の wav が変わったら作り直す
"""

import hashlib
import os
import wave
import winsound

import config
from paths import SOUNDS_DIR, TEMP_DIR

# 鳴らす場面と、config の項目名
SOUND_KEYS = {
    "startup": "sound_startup",
    "on": "sound_on",
    "off": "sound_off",
}

PAD_BEFORE = 0.2  # 秒。イヤホンが起きるまでの時間。長いほど、聞こえるのが遅れる
PAD_AFTER = 0.5   # 秒。音の終わりが切れないように。動作には影響しないので多めに

_PADDED_DIR = os.path.join(TEMP_DIR, "sounds")
_FLAGS = winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT


def list_sounds():
    """assets/sounds にある wav のファイル名(名前順)"""
    try:
        return sorted(name for name in os.listdir(SOUNDS_DIR) if name.lower().endswith(".wav"))
    except FileNotFoundError:
        return []


def _padded(path):
    """path の前後に無音をつけた wav のパス(無ければ作る)"""
    # 元のファイルの場所・更新日時・無音の長さから名前を決める。どれかが変われば別のファイルになる
    key = f"{path}|{os.path.getmtime(path)}|{PAD_BEFORE}|{PAD_AFTER}"
    padded_path = os.path.join(_PADDED_DIR, hashlib.sha1(key.encode("utf-8")).hexdigest() + ".wav")
    if os.path.exists(padded_path):
        return padded_path

    with wave.open(path, "rb") as src:
        params = src.getparams()
        frames = src.readframes(src.getnframes())
    # 無音の1コマ分。8ビットの wav は 128 が無音(0 だと「ブッ」と鳴る)、それ以外は 0
    zero = b"\x80" if params.sampwidth == 1 else b"\x00"
    frame_silence = zero * (params.sampwidth * params.nchannels)

    def silence(seconds):
        return frame_silence * int(params.framerate * seconds)

    os.makedirs(_PADDED_DIR, exist_ok=True)
    with wave.open(padded_path, "wb") as dst:
        dst.setparams(params)
        dst.writeframes(silence(PAD_BEFORE) + frames + silence(PAD_AFTER))
    return padded_path


def play_file(name):
    """wav を一つ鳴らす。"" なら何もしない"""
    if not name:
        return
    path = os.path.join(SOUNDS_DIR, name)
    if not os.path.exists(path):
        print(f"効果音が見つかりません: {path}")
        return
    try:
        if config.get("sound_padding"):
            path = _padded(path)
        winsound.PlaySound(path, _FLAGS)
    except (RuntimeError, OSError, wave.Error) as e:
        print(f"効果音を鳴らせませんでした: {path}: {e}")


def play(scene):
    """場面("startup" / "on" / "off")に選ばれている音を鳴らす"""
    play_file(config.get(SOUND_KEYS[scene]))
