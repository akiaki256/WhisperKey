"""
入力補正の「同音異義語の確かめ」(GPU版のみ。入力補正がオンのとき、文字起こしのあとに動く)
候補を出す(プログラム)・選ぶ(LLM)・組み立てる(プログラム)を分ける。

- よく使う言葉: LLM には読みのカタカナで見せ、最後に登録した書き方に戻す。読みが同じところは、聞かずに置き換える
- 候補を出す: よく使う言葉・英字の混ざった言葉・Whisper の 2〜5 位・辞書・単語をまたいだ読み から出し、重なる場所を一つにまとめる
- 選ぶ: 一か所ずつ「【?】に入るのは A / B / C…?」と聞き、記号の確率を読む(max_tokens 1、logprobs)
- 組み立てる: 元の言葉以外の候補が THRESHOLD 以上で勝ったときだけ差し替える

- load(): 辞書を読む(時間がかかるので、入力補正の立ち上げと一緒に裏で呼ぶ)。読めなかったら確かめずに動く
- check(base_url, text, raw, nbest, context, vocabulary, deadline): 確かめた文を返す。時間切れ・エラーのときは、そこまでの文
- take_alternatives(): 最後の check の「候補を出す」の窓の文を、確率の高い順に返して忘れる [(文, 確率, (始め, 長さ)), ...]
- remove_stutter(text): 言い淀みの切れ端を消す(設定「言い淀みを消す」)
"""

import difflib
import json
import math
import os
import re
import threading
import time
import unicodedata
import urllib.request

import vocab_match as VM
from paths import HOMOPHONE_DIR

THRESHOLD = 0.8        # 元の言葉以外が、この確率以上で勝ったら差し替える
TIE = 0.10             # 一番が THRESHOLD 未満で、二番との差がこれ以内なら二つだけで聞き直す
MAX_SAME = 8           # 名詞・動詞の、同じ読みの候補の数
MAX_NEAR = 8           # 名詞・動詞の、近い読みの候補の数
ALT_MIN_PROB = 0.01    # 「候補を出す」の窓に並べる文の確率の下限
LETTERS = "ABCDEFGHIJKLMNOPQRST"   # 選択肢の記号(元の言葉を入れて 20 個まで。確率は上位 20 個まで返してもらう)
TARGET_POS2 = {"一般", "サ変接続", "形容動詞語幹", "副詞可能", "ナイ形容詞語幹"}
KANJI = re.compile(r"[一-鿿々]")
# 聞き分けにくい音の組(発音のカタカナ)。どちら向きにも、一つの言葉につき一か所だけ入れ替える
NEAR_PAIRS = [("オ", "ウ"), ("ヨ", "オ"), ("ダ", "ラ"), ("リ", "ディ"), ("ヤ", "ア"), ("ユ", "ウ"), ("タ", "サ"), ("ク", "ツ"),
              ("カ", "ガ"), ("キ", "ギ"), ("ク", "グ"), ("ケ", "ゲ"), ("コ", "ゴ"),
              ("サ", "ザ"), ("シ", "ジ"), ("ス", "ズ"), ("セ", "ゼ"), ("ソ", "ゾ"),
              ("タ", "ダ"), ("チ", "ヂ"), ("ツ", "ヅ"), ("テ", "デ"), ("ト", "ド"),
              ("ハ", "バ"), ("ヒ", "ビ"), ("フ", "ブ"), ("ヘ", "ベ"), ("ホ", "ボ"),
              ("ハ", "パ"), ("ヒ", "ピ"), ("フ", "プ"), ("ヘ", "ペ"), ("ホ", "ポ"),
              ("バ", "パ"), ("ビ", "ピ"), ("ブ", "プ"), ("ベ", "ペ"), ("ボ", "ポ"),
              ("マ", "バ"), ("ミ", "ビ"), ("ム", "ブ"), ("メ", "ベ"), ("モ", "ボ"),
              ("ネ", "メ"), ("ロ", "ド"), ("レ", "デ"), ("シ", "ヒ"), ("ゼ", "デ"), ("ツァ", "ザ"),
              ("ファ", "パ"), ("フィ", "ピ"), ("フェ", "ペ"), ("フォ", "ポ")]
DROPPABLE = ("ッ", "ン")   # 一か所だけ抜けても近い読みとみなす音
# Whisper の 2〜5 位の近い読みを使わない場所
NO_NEAR_POS = ("感動詞", "フィラー", "接続詞", "記号", "助詞", "助動詞")
MIXED = re.compile(r"[゠-ヿA-Za-zＡ-Ｚａ-ｚπΠ]+")   # 英字とカタカナのかたまり

NUMBER_READINGS = {   # 数字 → 読み(詰まる形も)。0〜10 だけ扱う
    "0": ["ゼロ", "レイ"], "1": ["イチ", "イッ"], "2": ["ニ"], "3": ["サン"], "4": ["ヨン", "ヨ", "シ"],
    "5": ["ゴ"], "6": ["ロク", "ロッ"], "7": ["ナナ", "シチ"], "8": ["ハチ", "ハッ"], "9": ["キュウ", "ク"],
    "10": ["ジュウ", "ジュッ", "ジッ"],
}
KANJI_NUMBERS = {"〇": "0", "一": "1", "二": "2", "三": "3", "四": "4", "五": "5", "六": "6", "七": "7", "八": "8",
                 "九": "9", "十": "10"}

SYSTEM = ("あなたは音声入力の変換ミスを見つける係です。"
          "文の【?】の部分は、音声認識が漢字を選んだところです。同じ読みの言葉を並べるので、"
          "文の意味と前後のつながりに一番合うものを選び、記号を一文字だけ答えてください。")
VOCAB_NOTE = "選択肢の「{}」は、この人がよく使う言葉です。文に合うときだけ選んでください。"

_tagger = None
_dict = None
_base_reading = {}
_lock = threading.Lock()
_records = []        # 今の check で確かめた場所 [{"pos": 今の文での位置, "chosen": 選んだ言葉, "probs": {言葉: 確率}}]
_alternatives = []   # 最後の check の窓の文(take_alternatives で取り出す)
_vocab = []          # 今の check のよく使う言葉 [(読み, 言葉)]


# =====================================================
# 読み込み
# =====================================================

def load():
    """辞書と MeCab を読む。二回目からは何もしない。読めなかったら False(確かめずに動く)"""
    global _tagger, _dict, _base_reading
    with _lock:
        if _tagger is not None:
            return True
        try:
            import fugashi   # 読み込みに時間がかかるので、使うときに
            t = time.perf_counter()
            dicdir = os.path.join(HOMOPHONE_DIR, "dicdir")
            tagger = fugashi.GenericTagger(f'-r "{os.path.join(dicdir, "mecabrc")}" -d "{dicdir}"')
            with open(os.path.join(HOMOPHONE_DIR, "homophone_dict.json"), encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("kata_by_pron", {})
            _base_reading = {(b, ct): r for r, v in data["verbs"]["by_reading"].items() for b, ct in v}
            _dict, _tagger = data, tagger
            print(f"同音異義語の確かめ: 辞書を読み込み({time.perf_counter() - t:.1f} 秒)")
            return True
        except Exception as e:
            print(f"同音異義語の確かめ: 辞書を読み込めませんでした(確かめずに動きます): {e}")
            return False


def is_ready():
    return _tagger is not None


def tagger():
    """MeCab(load() のあと)。Whisper に渡すヒント選び(transcribe.py)でも使う"""
    return _tagger


# =====================================================
# 文の切り方と読み
# =====================================================

def word_ends(text):
    """[(単語の終わりの位置, 品詞などの特徴)]。句読点補正(punctuate.py)で、句読点を入れてよい切れ目を決めるのに使う"""
    return [(pos + len(surface), feat) for pos, surface, feat in _tokens(text)]


def _tokens(text):
    """[(文の中の位置, 表記, 品詞などの特徴)]"""
    return VM.tokens(_tagger, text)


def _reading(surface, feat):
    """読み(カタカナ)。辞書に読みが無いときは、かなならカタカナにする。句読点・空白は空。数字・英字などは None"""
    if len(feat) > 7 and feat[7] != "*":
        return feat[7]
    s = unicodedata.normalize("NFKC", surface)
    if s and all("ぁ" <= c <= "ゟ" or VM.is_kata(c) for c in s):
        return VM.to_kata(s)
    if s and all(unicodedata.category(c).startswith(("P", "Z")) for c in s):
        return ""
    return None


def _normalize(text):
    text = unicodedata.normalize("NFKC", text).lower()
    return "".join(c for c in text if not unicodedata.category(c).startswith(("P", "Z", "S")))


def _is_kana(s):
    return bool(s) and all("ぁ" <= c <= "ゟ" or VM.is_kata(c) for c in s)


def _overlaps(start, end, spans):
    return any(start < e and s < end for s, e in spans)


# =====================================================
# 言い淀み
# =====================================================

def _stutter_spans(text):
    """言い淀みの残りの範囲 [(始め, 終わり)]。すぐ後ろの言葉(記号・空白は飛ばす)が、同じ字か同じ読みで始まるもの。
    助詞・助動詞は、間に記号か空白があるときだけ(は、早く は言い淀み、は早く は違う)"""
    toks = _tokens(text)
    out = []
    for i, (start, surface, feat) in enumerate(toks):
        if feat[0] == "記号":
            continue
        j = i + 1
        while j < len(toks) and toks[j][2][0] == "記号":
            j += 1
        if j >= len(toks):
            continue
        separated = j > i + 1 or toks[j][0] > start + len(surface)   # 間に記号か空白がある
        if not separated and feat[0] in ("助詞", "助動詞"):
            continue
        nxt_surface, nxt_feat = toks[j][1], toks[j][2]
        r, nr = _reading(surface, feat), _reading(nxt_surface, nxt_feat)
        if (len(nxt_surface) > len(surface) and nxt_surface.startswith(surface)) or (
                r and nr and len(nr) > len(r) and nr.startswith(r)):
            out.append((start, start + len(surface)))
    return out


def _is_word(text, s, e):
    """切れ端 text[s:e] を消さずに残すべきか。
    - 前の言葉にくっついた助詞・助動詞(パンと、とうもろこし の「と」)。文の頭や読点のすぐあとなら助詞ではありえない
    - 数字(1、10、100 / 第二日曜日)
    - それだけで一つの言葉として成り立つ(辞書に読みのある 2 文字以上の一語: パン、メール、東京、ゆう)"""
    fragment = text[s:e]
    ctx = [f for st, _, f in _tokens(text) if s <= st < e]
    attached = s > 0 and text[s - 1] not in "、。,，…・ 　.!?！？"
    if ctx and attached and ctx[0][0] in ("助詞", "助動詞"):
        return True
    if any(f[:2] == ("名詞", "数") for f in ctx) or fragment.strip().isdigit():
        return True
    toks = _tokens(fragment)
    return (len(toks) == 1 and len(fragment) >= 2 and len(toks[0][2]) > 7 and toks[0][2][7] != "*"
            and toks[0][2][0] not in ("助詞", "助動詞"))


def remove_stutter(text):
    """言い淀みの切れ端を消す(洗、洗濯物 → 洗濯物、ケスト、ケストリオン → ケストリオン)。
    切れ端がそれだけで言葉として成り立つもの・助詞・数字は消さない。切れ端のあとの読点・空白・…も消す。
    辞書を読めていなければ、そのまま返す。思わぬエラーのときも、そのまま返す(入力は止めない)"""
    if not is_ready() or not text:
        return text
    out = text
    try:
        for s, e in sorted(_stutter_spans(text), reverse=True):
            if _is_word(text, s, e):
                continue
            j = e
            while j < len(out) and out[j] in "、,，…・ 　.":
                j += 1
            out = out[:s] + out[j:]
    except Exception as e:
        print(f"言い淀みを消す: エラー(消さずに入力): {e}")
        return text
    return out


# =====================================================
# よく使う言葉(カタカナ方式)
# =====================================================

def _kata_of(reading):
    """よく使う言葉の読み → 見せるカタカナ(ひらがなはカタカナに)"""
    return VM.to_kata(unicodedata.normalize("NFKC", reading)).replace(" ", "")


def _vocab_spans(text, words):
    """よく使う言葉(登録した書き方・カタカナ)が、それだけで書かれているところ"""
    return [sp for w in words for sp in VM.written_spans(text, w)]


def _kata_spans(text):
    """文の中の、よく使う言葉のカタカナ(前後がカタカナに続いていないところ) [(始め, 終わり, カタカナ)]"""
    out = []
    for r, _ in _vocab:
        k = _kata_of(r)
        for s, e in VM.written_spans(text, k):
            out.append((s, e, k))
    return out


def to_registered(text):
    """よく使う言葉のカタカナを、登録した書き方に戻す(長いものから)"""
    word = {_kata_of(r): w for r, w in _vocab}
    picked = []
    for s, e, k in sorted(_kata_spans(text), key=lambda x: (-(x[1] - x[0]), x[0])):
        if all(e <= ps or pe <= s for ps, pe, _ in picked):
            picked.append((s, e, k))
    for s, e, k in sorted(picked, key=lambda x: -x[0]):
        text = text[:s] + word[k] + text[e:]
    return text


def _to_kata_words(text):
    """文の中の、よく使う言葉の登録した書き方をカタカナに直す(Whisper の 2〜5 位に Garmin と出たとき)"""
    for r, w in sorted(_vocab, key=lambda x: -len(x[1])):
        if w and w in text:
            text = text.replace(w, _kata_of(r))
    return text


def _vocab_places(text):
    """よく使う言葉の場所。読みが同じところは、聞かずにカタカナに置き換える。
    近いだけのところは聞く場所 [(位置, 元の言葉, [カタカナ…], 出どころ)] にする。(置き換えた文, 聞く場所)"""
    kata = {w: _kata_of(r) for r, w in _vocab}
    stutter = _stutter_spans(text)
    asks, shift = [], 0
    for start, end, orig, hits in VM.find(_tagger, text, [{"word": w, "reading": r} for r, w in _vocab]):
        if _overlaps(start, end, stutter):   # 言い淀みの残り(クロ、クロノヴェイル の「クロ」)は見ない
            continue
        words = list(dict.fromkeys(w for w, _ in hits))
        s = start + shift
        same = [w for w in words if VM.pron_of(_tagger, orig) == VM.norm_reading(kata[w])]
        if same:
            k = kata[same[0]]
            text = text[:s] + k + text[s + len(orig):]
            for r in _records:
                if r["pos"] > s:
                    r["pos"] += len(k) - len(orig)
            _records.append({"pos": s, "chosen": k, "probs": {k: 1.0, orig: 0.99}})   # 窓に元の言葉が並ぶように
            print(f"同音異義語の確かめ(よく使う言葉): {orig} → {k}(読みが同じ)")
            shift += len(k) - len(orig)
        else:
            alts = list(dict.fromkeys(kata[w] for w in words if kata[w] != orig))
            if alts:
                asks.append((s, orig, alts, {a: "よく使う言葉" for a in alts}))
    return text, asks


# =====================================================
# 候補を出す(プログラム)
# =====================================================

def _number_key(surface):
    s = unicodedata.normalize("NFKC", surface)
    return KANJI_NUMBERS.get(s, s)


def _number_alts(num, counter):
    """数字 + 助数詞(5時)→ 同じ読みの名詞(誤字)と、同じ読みの別の助数詞(5字)"""
    counters, nouns = _dict["counters"], _dict["nouns"]
    alts = []
    for nr in NUMBER_READINGS.get(_number_key(num), []):
        for cr in counters["by_surface"].get(counter, []):
            for s in nouns.get(nr + cr, []):
                if s not in alts:
                    alts.append(s)
            for c in counters["by_reading"].get(cr, []):
                if c != counter and num + c not in alts:
                    alts.append(num + c)
    return [a for a in alts if len(a) == len(num + counter)]


def _counter_alts(reading, length):
    """名詞の読み(サンギョウ)を 数字 + 助数詞 に分けられたら、その書き方(3行)"""
    out = []
    for key, readings in NUMBER_READINGS.items():
        for nr in readings:
            if reading.startswith(nr):
                for c in _dict["counters"]["by_reading"].get(reading[len(nr):], []):
                    s = key + c
                    if len(s) == length and s not in out:
                        out.append(s)
    return out


def _prefix_alts(surface, feat, nxt, start):
    """同じ読みの接頭詞(同じ文字数、よく使う順)。surface が名詞か接頭詞で、すぐ後ろに名詞が続くときだけ"""
    if (feat[0] not in ("名詞", "接頭詞") or not nxt or nxt[0] != start + len(surface) or nxt[2][0] != "名詞"
            or "prefixes" not in _dict):
        return []
    return [s for s in _dict["prefixes"].get(feat[7], []) if s != surface and len(s) == len(surface)]


def _near_variants(pron):
    """{近い発音: 組}。伸ばす音は抜いて比べる。一か所だけ入れ替え、または ッ・ン を一か所だけ抜く"""
    ms = VM.morae(pron.replace("ー", ""))
    out = {}
    for i, m in enumerate(ms):
        for a, b in NEAR_PAIRS:
            for x, y in ((a, b), (b, a)):
                if m == x:
                    out.setdefault("".join(ms[:i] + [y] + ms[i + 1:]), f"{a}/{b}")
        if m in DROPPABLE:
            out.setdefault("".join(ms[:i] + ms[i + 1:]), f"{m}抜け")
    out.pop("".join(ms), None)
    return out


def _noun_candidates(surface, reading, pron, kata=False):
    """同じ読み・近い読みの名詞(字数は問わない)。(同じ読み, 近い読み)。kata: カタカナの名詞を先に入れる"""
    nouns, by_pron, kata_pron = _dict["nouns"], _dict["nouns_by_pron"], _dict["kata_by_pron"]

    def by(key):
        return (kata_pron.get(key, []) if kata else []) + by_pron.get(key, [])

    same = []
    for s in nouns.get(reading, []) + (by(pron.replace("ー", "")) if pron and pron != "*" else []):
        if s != surface and s not in same:
            same.append(s)
    near = []
    if pron and pron != "*":
        found = []
        for v in _near_variants(pron):
            found += [(i, s) for i, s in enumerate(by(v)) if s != surface and s not in same]
        for _, s in sorted(found):   # それぞれの発音の中でよく使う順
            if s not in near:
                near.append(s)
    return same, near


def _dictionary_places(text, keep):
    """辞書の候補 [(位置, 元の言葉, [候補…])]。名詞、カタカナ・ひらがなの言葉、動詞・形容詞、数字と助数詞、接頭詞
    keep: 確かめない範囲"""
    out, toks, skip = [], _tokens(text), False
    for i, (start, surface, feat) in enumerate(toks):
        if skip:   # 前の数字と一緒に見た助数詞
            skip = False
            continue
        if _overlaps(start, start + len(surface), keep):
            continue
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if (feat[:2] == ("名詞", "数") and nxt and nxt[0] == start + len(surface)
                and nxt[2][:3] == ("名詞", "接尾", "助数詞") and _number_key(surface) in NUMBER_READINGS):
            alts = _number_alts(surface, nxt[1])
            if alts:
                out.append((start, surface + nxt[1], alts[:MAX_SAME]))
            skip = True
            continue
        pron = feat[8] if len(feat) > 8 else "*"
        if not KANJI.search(surface) or len(feat) < 8:
            # 漢字を含まない言葉(名詞・辞書に無い言葉)も、同じ発音・近い発音の名詞を候補に(ツーラー → クーラー)
            if _is_kana(surface) and len(surface) >= 2 and (len(feat) < 8 or feat[0] == "名詞"):
                p = pron if pron != "*" else VM.to_kata(surface)
                same, near = _noun_candidates(surface, VM.to_kata(surface), p, kata=True)
                kana = {VM.to_kata(surface), VM.to_hira(surface)}
                alts = [a for a in same[:MAX_SAME] + near[:MAX_NEAR] if a not in kana]
                if alts:
                    out.append((start, surface, alts))
            continue
        prefix_alts = _prefix_alts(surface, feat, nxt, start)
        alts = []
        if feat[0] == "名詞" and feat[1] in TARGET_POS2:
            same, near = _noun_candidates(surface, feat[7], pron)
            same = prefix_alts + [s for s in same if s not in prefix_alts]
            counter_alts = _counter_alts(feat[7], len(surface))[:1]
            if counter_alts:   # 数字と助数詞の書き方があるときだけ、名詞の候補を 1 つ減らして足す(産業 → 3行)
                same = same[:MAX_SAME - 1] + counter_alts
            alts = same[:MAX_SAME] + near[:MAX_NEAR]
        elif feat[0] in ("動詞", "形容詞") and feat[1] == "自立":
            ctype, cform, base = feat[4], feat[5], feat[6]
            reading = _base_reading.get((base, ctype))
            readings = [reading] + list(_near_variants(reading)) if reading else []
            for r in readings:
                for other, t in _dict["verbs"]["by_reading"].get(r, []):
                    if other == base or t != ctype:   # 活用の種類が同じもの(撮る・取る は どちらも 五段・ラ行)
                        continue
                    s = _dict["verbs"]["forms"].get(f"{other}\t{t}\t{cform}")
                    if s and s != surface and s not in alts:
                        alts.append(s)
            alts = alts[:MAX_SAME + MAX_NEAR]
        elif feat[0] in ("名詞", "接頭詞"):   # 上の名詞に入らない名詞(数など)と接頭詞は、接頭詞の候補だけ
            alts = prefix_alts
        if alts:
            out.append((start, surface, alts[:len(LETTERS) - 1]))
    return out


def _span_places(text, keep):
    """2〜3 語をまたいだ読みの名詞 [(位置, 元の言葉, [候補…])](歯医者 / 配車)。
    助詞・助動詞・記号で始まる・終わるところ、空白をはさむところは見ない。重なったら長いほう"""
    toks = _tokens(text)
    found = []
    for i in range(len(toks)):
        for j in range(i + 2, min(len(toks), i + 3) + 1):
            first, last = toks[i][2], toks[j - 1][2]
            if first[0] in ("助詞", "助動詞", "記号") or last[0] in ("助詞", "助動詞", "記号"):
                continue
            if any(t[0] + len(t[1]) != toks[k + 1][0] for k, t in enumerate(toks[i:j - 1], i)):
                continue
            reads = [_reading(s, f) for _, s, f in toks[i:j]]
            if None in reads or not all(reads):
                continue
            start = toks[i][0]
            orig = text[start:toks[j - 1][0] + len(toks[j - 1][1])]
            if _overlaps(start, start + len(orig), keep):
                continue
            same, near = _noun_candidates(orig, "".join(reads), "".join(reads))
            alts = [a for a in same[:MAX_SAME] + near[:MAX_NEAR] if a != orig]
            if alts:
                found.append((start, orig, alts[:len(LETTERS) - 1]))
    out = []
    for f in sorted(found, key=lambda x: (-len(x[1]), x[0])):
        if all(f[0] + len(f[1]) <= g[0] or g[0] + len(g[1]) <= f[0] for g in out):
            out.append(f)
    return sorted(out)


def protected_spans(raw, text, words):
    """今の文(text)の中で、Whisper の 2〜5 位で触らない範囲 [(始め, 終わり)]
    - 音声辞書などで変わったところ: Whisper の文(raw)と比べて違うところ。消えたところは、その前後の 1 文字
    - よく使う言葉(登録した書き方・カタカナ)が書かれているところ"""
    spans = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=raw, b=text, autojunk=False).get_opcodes():
        if op != "equal":
            spans.append((max(j1 - 1, 0), j2 + 1) if j1 == j2 else (j1, j2))
    return spans + _vocab_spans(text, words)


def _whisper_places(text, nbest, protect):
    """Whisper の 2〜5 位と今の文を単語の並びで比べ、置き換わったところの読みが同じか近いものを候補にする
    [(位置, 元の言葉, [候補…])]。助詞・感動詞などだけの場所は近い読みを使わない。
    句読点・空白だけが違う候補は一つにまとめる。重なったら短いほう"""
    t_tok = _tokens(text)
    t_read = [_reading(s, f) for _, s, f in t_tok]
    found = {}
    for hyp in nbest:
        h_tok = _tokens(hyp)
        h_read = [_reading(s, f) for _, s, f in h_tok]
        sm = difflib.SequenceMatcher(a=[s for _, s, _ in t_tok], b=[s for _, s, _ in h_tok], autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op != "replace":
                continue
            ra, rb = t_read[i1:i2], h_read[j1:j2]
            if None in ra or None in rb or not "".join(ra):
                continue
            a, b = "".join(ra), "".join(rb)
            if a != b:
                na, nb = VM.norm_reading(a), VM.norm_reading(b)
                if not na or not nb or VM.distance(na, nb) > 1.0:
                    continue
                if all(f[0] in NO_NEAR_POS for _, _, f in t_tok[i1:i2]):
                    continue
            start = t_tok[i1][0]
            orig = text[start:t_tok[i2 - 1][0] + len(t_tok[i2 - 1][1])]
            if _overlaps(start, start + len(orig), protect):
                continue
            alt = _to_kata_words("".join(s for _, s, _ in h_tok[j1:j2]))
            if _normalize(alt) == _normalize(orig):
                continue
            alts = found.setdefault((start, orig), [])
            if all(_normalize(x) != _normalize(alt) for x in alts):
                alts.append(alt)
    out = []
    for (start, orig), alts in sorted(found.items(), key=lambda x: (len(x[0][1]), x[0][0])):
        if all(start + len(orig) <= s or s + len(o) <= start for s, o, _ in out):
            out.append((start, orig, alts[:len(LETTERS) - 1]))
    return sorted(out)


def _mixed_places(text):
    """英字とカタカナがくっついたところ [(位置, 元の言葉, [候補…])]。英字をカタカナにした形(ポストグレスQL →
    ポストグレスキューエル)と、その形でよく使う言葉に近いもの。英字が 4 文字以上続くもの(Windowsアップデート)は触らない"""
    out = []
    words = [{"word": w, "reading": r} for r, w in _vocab]
    reading_of = {w: r for r, w in _vocab}
    for m in MIXED.finditer(text):
        w = m.group(0)
        if not (any(VM.is_kata(c) for c in w) and any(not VM.is_kata(c) for c in w)):
            continue
        if any(len(run) > 3 for run in re.findall(r"[^゠-ヿ]+", w)):
            continue
        k = VM.letters_to_kata(w)
        alts = [k]
        for st, en, _, hits in VM.find(_tagger, k, words):
            if st == 0 and en == len(k):
                for vw, _ in hits:
                    kk = _kata_of(reading_of[vw])
                    if kk not in alts:
                        alts.append(kk)
        out.append((m.start(), w, alts))
    return out


def _places(text, raw, nbest, vocab_asks):
    """全部の出どころの候補を出して、重なる場所を一つにまとめる [(位置, 元の言葉, [候補…])]。
    いちばん広い範囲にそろえ(狭い範囲の候補は、まわりの字を今の文のまま足す)、出どころから一つずつ順番に取る"""
    words = [w for _, w in _vocab] + [_kata_of(r) for r, _ in _vocab]
    keep = _stutter_spans(text) + _vocab_spans(text, words)
    groups = [[(s, o, a) for s, o, a, _ in vocab_asks], _mixed_places(text)]   # この順に並べる
    if nbest:
        protect = protected_spans(raw, text, words) + _stutter_spans(text)
        groups.append(_whisper_places(text, nbest, protect))
    groups += [_dictionary_places(text, keep), _span_places(text, keep)]
    pieces = sorted(((s, s + len(o), a, rank) for rank, g in enumerate(groups) for s, o, a in g),
                    key=lambda x: (x[0], -x[1]))
    merged = []
    for p in pieces:
        if merged and p[0] < merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], p[1])
            merged[-1]["pieces"].append(p)
        else:
            merged.append({"start": p[0], "end": p[1], "pieces": [p]})
    out = []
    for m in merged:
        S, E = m["start"], m["end"]
        orig = text[S:E]
        lanes = [[text[S:s] + a + text[e:E] for a in alts] for s, e, alts, _ in sorted(m["pieces"], key=lambda x: x[3])]
        alts, seen = [], {_normalize(orig)}
        while any(lanes) and len(alts) < len(LETTERS) - 1:
            for lane in lanes:
                while lane:
                    full = lane.pop(0)
                    if _normalize(full) not in seen:
                        seen.add(_normalize(full))
                        alts.append(full)
                        break
                if len(alts) >= len(LETTERS) - 1:
                    break
        if alts:
            out.append((S, orig, alts))
    return out


# =====================================================
# 選ぶ(LLM)と組み立てる(プログラム)
# =====================================================

def _system(names):
    """names: 選択肢にあるよく使う言葉のカタカナ(あれば一言だけ伝える)"""
    if not names:
        return SYSTEM
    return SYSTEM + "\n\n" + VOCAB_NOTE.format("」「".join(names))


def _ask_once(base_url, before, after, options, context_lines, names, deadline):
    # 比べている場所の外は、よく使う言葉を登録した書き方で見せる
    before, after = to_registered(before), to_registered(after)
    lines = (["直前の入力(古い順):"] + context_lines + [""]) if context_lines else []
    lines += [f"文: {before}【?】{after}", "", "選択肢:"]
    lines += [f"{LETTERS[i]}: {before}{w}{after}" for i, w in enumerate(options)]
    lines += ["", "答え(記号だけ):"]
    body = {"temperature": 0, "max_tokens": 1, "logprobs": True, "top_logprobs": 20,
            "messages": [{"role": "system", "content": _system(names)},
                         {"role": "user", "content": "\n".join(lines)}]}
    timeout = deadline - time.monotonic()
    if timeout <= 0:
        raise TimeoutError
    req = urllib.request.Request(base_url + "/v1/chat/completions", json.dumps(body).encode("utf-8"),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        top = json.load(r)["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
    p = {L: 0.0 for L in LETTERS[:len(options)]}
    for item in top:
        tok = item["token"].strip()
        if tok in p:
            p[tok] += math.exp(item["logprob"])
    total = sum(p.values()) or 1.0
    return {options[LETTERS.index(L)]: v / total for L, v in p.items()}


def _ask(base_url, before, after, options, context_lines, names, deadline):
    """並びを逆にしてもう一回聞き、平均する(先頭の選択肢が得をする癖を消す)"""
    p1 = _ask_once(base_url, before, after, options, context_lines, names, deadline)
    p2 = _ask_once(base_url, before, after, list(reversed(options)), context_lines, names, deadline)
    return {w: (p1[w] + p2[w]) / 2 for w in options}


def _log_slot(orig, p, replaced):
    """一か所ぶんの結果をコンソールに出す(差し替えなかった場所も出す)"""
    ranked = sorted(p.items(), key=lambda x: x[1], reverse=True)
    top = " / ".join(f"{w} {v:.0%}" for w, v in ranked[:3])
    best = ranked[0][0]
    if replaced:
        result = "差し替え"
    elif best == orig:
        result = "そのまま"
    else:
        result = f"そのまま({THRESHOLD:.0%} に届かず)"
    print(f"同音異義語の確かめ: {orig} → {top} … {result}")


def _decide(base_url, before, after, orig, options, context_lines, names, deadline):
    """確率 {言葉: 確率}。読みが同じ候補を足し、同率なら二つだけで聞き直す"""
    words = [orig] + options
    p = _ask(base_url, before, after, words, context_lines, names, deadline)
    # 元の言葉と読みが違い、互いに読みが同じ候補(眼鏡 / メガネ)は確率を足して、一番の書き方に寄せる
    rd = {w: tuple(VM.pron_of(_tagger, w)) for w in words}
    groups = {}
    for w in words:
        groups.setdefault(rd[w], []).append(w)
    for key, g in groups.items():
        if len(g) > 1 and orig not in g and key != rd[orig]:
            top = max(g, key=p.get)
            p[top] = sum(p[w] for w in g)
    # 同率なら、一番と二番だけを並べて聞き直す。二択で言い切れたら、その言葉に確率を寄せる(窓の並びにも効く)
    ranked = sorted(p, key=p.get, reverse=True)
    if len(ranked) >= 2 and p[ranked[0]] < THRESHOLD and p[ranked[0]] - p[ranked[1]] <= TIE:
        q = _ask(base_url, before, after, ranked[:2], context_lines, names, deadline)
        best = max(q, key=q.get)
        if q[best] >= THRESHOLD:
            p[best] = max(p[best], q[best])
    return p


def _check_places(base_url, text, places, context_lines, deadline):
    """左から一か所ずつ聞いて、(差し替えた文, 最後まで確かめたか) を返す。places の位置は今の文での位置
    時間切れ・エラーのときは、そこまでに差し替えた文を返す"""
    katas = [_kata_of(r) for r, _ in _vocab]
    shift = 0
    for start, orig, options in sorted(places):
        s = start + shift
        if text[s:s + len(orig)] != orig:
            continue
        before, after = text[:s], text[s + len(orig):]
        names = [k for k in dict.fromkeys(katas) if k not in orig and any(k in o for o in options)]
        try:
            p = _decide(base_url, before, after, orig, options, context_lines, names, deadline)
        except (TimeoutError, OSError) as e:   # 時間切れは socket.timeout(OSError の仲間)
            print(f"同音異義語の確かめ: 時間切れ・エラー(そこまでの文で入力): {e}")
            return text, False
        except (ValueError, KeyError, IndexError) as e:
            print(f"同音異義語の確かめ: 返事を読めませんでした(そこまでの文で入力): {e}")
            return text, False
        best = max(p, key=p.get)
        replaced = best != orig and p[best] >= THRESHOLD
        _log_slot(orig, p, replaced)
        chosen = best if replaced else orig
        if replaced:
            text = before + best + after
            delta = len(best) - len(orig)
            shift += delta
            for r in _records:   # 後ろにある、前に確かめた場所の位置をずらす
                if r["pos"] > s:
                    r["pos"] += delta
        _records.append({"pos": s, "chosen": chosen, "probs": p})
    return text, True


def _make_alternatives(text):
    """窓の文。一か所だけ変えた文と、二か所を変えた文(確率はかけ算)を、確率の高い順に [(文, 確率, (始め, 長さ))]"""
    singles = []
    for r in _records:
        pos, chosen = r["pos"], r["chosen"]
        if text[pos:pos + len(chosen)] != chosen:
            continue   # 位置がずれていたら(念のため)並べない
        for w, p in r["probs"].items():
            if w != chosen and p >= ALT_MIN_PROB:
                singles.append((pos, chosen, w, p))
    alts = {}
    for pos, chosen, w, p in singles:
        t = text[:pos] + w + text[pos + len(chosen):]
        if t != text and p > alts.get(t, (0,))[0]:
            alts[t] = (p, (pos, len(w)))
    for i, (p1, c1, w1, r1) in enumerate(singles):
        for p2, c2, w2, r2 in singles[i + 1:]:
            if not (p1 + len(c1) <= p2 or p2 + len(c2) <= p1) or r1 * r2 < ALT_MIN_PROB:
                continue
            a, b = sorted([(p1, c1, w1), (p2, c2, w2)], key=lambda x: -x[0])   # 後ろから替える
            t = text[:a[0]] + a[2] + text[a[0] + len(a[1]):]
            t = t[:b[0]] + b[2] + t[b[0] + len(b[1]):]
            if t != text and r1 * r2 > alts.get(t, (0,))[0]:
                alts[t] = (r1 * r2, (min(p1, p2), 0))
    return [(t, p, span) for t, (p, span) in sorted(alts.items(), key=lambda x: -x[1][0])]


def take_alternatives():
    """最後の check の窓の文を返して忘れる"""
    global _alternatives
    alts, _alternatives = _alternatives, []
    return alts


def check(base_url, text, raw, nbest, context_lines, vocabulary, deadline):
    """確かめた文を返す。
    raw: Whisper の文(音声辞書を通す前)。nbest: Whisper の 2〜5 位(無ければ空)
    context_lines: 直前の入力(「[時:分:秒] 文」)。vocabulary: よく使う言葉 [(読み, 言葉), ...]
    時間切れ・エラーのときは、そこまでに確かめた文を返す"""
    global _alternatives, _vocab
    _records.clear()
    _alternatives = []
    if not is_ready() or not text:
        return text
    _vocab = [(r, w) for r, w in vocabulary if r and w]
    started = time.monotonic()
    n_places = 0
    try:
        text, asks = _vocab_places(text)
        places = _places(text, raw, nbest, asks)
        n_places = len(places)
        text, _ = _check_places(base_url, text, places, context_lines, deadline)
    except Exception as e:   # 候補を出すところ(MeCab など)の思わぬエラーでも、入力は止めない
        print(f"同音異義語の確かめ: エラー(そこまでの文で入力): {e}")
    print(f"同音異義語の確かめ: {n_places} か所を {time.monotonic() - started:.2f} 秒で確かめた")
    try:
        final = to_registered(text)
        window = [(to_registered(t), p, span) for t, p, span in _make_alternatives(text)]
        if final != text:
            window.insert(0, (text, 1.0, (0, 0)))   # 登録した書き方に戻す前の文(元の言葉が残ったもの)も窓に
    except Exception as e:   # ここでの思わぬエラーでも、入力は止めない(窓の候補は無し)
        print(f"同音異義語の確かめ: 仕上げでエラー(確かめた文のまま入力): {e}")
        final, window = text, []
    _alternatives = window
    return final
