"""
マイクデバイス一覧取得(MMEホスト絞り込み)
仕様書§11

本体(マイクを名前で探して開く・設定タブの一覧)で使う。

v1の処理を踏襲:
- MMEホストのみ対象(faster-Whisperとの相性のため16kHz固定)
- Microsoft Sound Mapper (マッパー/Mapper) を除外
- "繝槭う繧ｯ" → "マイク" の文字化け復元(UTF-8→CP932誤解釈の逆変換)
- 同名デバイスの重複除去(出現順で先頭のみ残す)
- ソートはせず pyaudio の返す順を維持
"""

import ctypes
from ctypes import wintypes

import pyaudio

from config_store import SAMPLE_RATE, DEFAULT_DEVICE_LABEL


# 文字化け復元テーブル
# UTF-8バイト列をCP932として誤解釈した結果の文字列 → 正しい文字列
MOJIBAKE_REPLACEMENTS = [
    ("繝槭う繧ｯ", "マイク"),
]


def _fix_mojibake(name):
    """既知の文字化けパターンを復元"""
    for bad, good in MOJIBAKE_REPLACEMENTS:
        if bad in name:
            name = name.replace(bad, good)
    return name


def _is_sound_mapper(name):
    """Microsoft Sound Mapper 系のデバイスか判定"""
    return "マッパー" in name or "Mapper" in name


def get_mme_input_devices(p=None):
    """
    MMEホストのマイク入力デバイス一覧を返す。
    p: 使う PyAudio。渡さなければ、ここで作って終わらせる
       (PyAudio は作った瞬間の一覧を覚え続けるので、一覧は作り直した PyAudio で取ること)
    - Sound Mapper は除外
    - 文字化けは復元
    - 同名重複は先頭のみ残す
    - サンプルレートは16kHz固定(MMEは16kHz対応)
    
    Returns:
        list[dict]: [{"index": int, "name": str, "sample_rate": int}, ...]
        取得失敗時は空リスト。
    """
    own = p is None
    if own:
        try:
            p = pyaudio.PyAudio()
        except Exception as e:
            print(f"pyaudio init failed: {e}")
            return []
    
    devices = []
    seen_names = set()
    
    try:
        for i in range(p.get_device_count()):
            try:
                info = p.get_device_info_by_index(i)
                
                # 入力チャンネルがないものはスキップ
                if info.get("maxInputChannels", 0) <= 0:
                    continue
                
                # MMEホスト以外はスキップ
                host_api_info = p.get_host_api_info_by_index(info["hostApi"])
                if "MME" not in host_api_info.get("name", ""):
                    continue
                
                # デバイス名の取得(bytesなら変換)
                device_name = info.get("name", "")
                if isinstance(device_name, bytes):
                    try:
                        device_name = device_name.decode("utf-8")
                    except UnicodeDecodeError:
                        device_name = device_name.decode("cp932", errors="ignore")
                
                # 文字化け復元
                device_name = _fix_mojibake(device_name)
                
                # Sound Mapper 除外
                if _is_sound_mapper(device_name):
                    continue
                
                # 重複除去
                if device_name in seen_names:
                    continue
                seen_names.add(device_name)
                
                # サンプルレートは16kHz固定
                devices.append({
                    "index": int(info["index"]),
                    "name": device_name,
                    "sample_rate": SAMPLE_RATE,
                })
            except Exception:
                # 個別デバイスの取得失敗はスキップ
                continue
    finally:
        if own:
            p.terminate()
    
    return devices


class _WAVEINCAPSW(ctypes.Structure):
    _fields_ = [
        ("wMid", wintypes.WORD),
        ("wPid", wintypes.WORD),
        ("vDriverVersion", wintypes.UINT),
        ("szPname", wintypes.WCHAR * 32),
        ("dwFormats", wintypes.DWORD),
        ("wChannels", wintypes.WORD),
        ("wReserved1", wintypes.WORD),
    ]


def get_live_input_names():
    """
    今つながっているマイクの名前を、Windows(MME)に直接聞いて返す。
    PyAudio は作った瞬間の一覧を覚え続けるため、起動中の抜き差しがわからない。
    こちらは聞くたびに今の状態を返す。名前は PyAudio(MME)と同じもの。
    """
    winmm = ctypes.windll.winmm
    names = []
    for i in range(winmm.waveInGetNumDevs()):
        caps = _WAVEINCAPSW()
        if winmm.waveInGetDevCapsW(i, ctypes.byref(caps), ctypes.sizeof(caps)) != 0:
            continue
        if caps.szPname not in names:
            names.append(caps.szPname)
    return names


def get_device_name_list():
    """
    UI表示用のデバイス名リストを返す(今つながっているもの)。
    先頭に「既定のデバイスに自動接続」を固定で追加する。
    
    Returns:
        list[str]: デバイス名の配列
    """
    return [DEFAULT_DEVICE_LABEL] + get_live_input_names()


def find_device_by_name(name, p=None):
    """
    デバイス名から該当するデバイス情報を返す。
    p: 探すのに使う PyAudio(get_mme_input_devices と同じ)
    「既定のデバイスに自動接続」の場合は None を返す(index=null扱い)。
    
    Returns:
        dict or None: {"index": int, "name": str, "sample_rate": int}
    """
    if name == DEFAULT_DEVICE_LABEL:
        return None
    
    devices = get_mme_input_devices(p)
    for d in devices:
        if d["name"] == name:
            return d
    return None
