"""
入力補正の「同音異義語の確かめ」(GPU版のみ。入力補正がオンのとき、LLM の補正のあとに動く)
LLM は、それだけ見ると正しい言葉になる同音異義語(仕様 / 使用、分 / 文)に気づけない。
でも候補を並べて「どれ?」と聞けば選べる。そこで、候補を出す・選ぶ・組み立てるを分ける。
やり方の決まりごとは実験の結果から(v5_LLM補正の実験/結果/正答率の流れ.md の段階 13)。

- 候補を出す(プログラム)
    1. 辞書: MeCab(fugashi + IPA 辞書)で単語に切り、読みが同じ言葉を索引(homophone_dict.json)から引く
       名詞、動詞・形容詞(同じ活用の形)、数字と助数詞(5時 → 誤字、産業 → 3行)。漢字を含む言葉だけ、同じ文字数のものだけ
    2. Whisper: n-best(2〜5 位の書き分け)と今の文を単語の並びで比べ、違うところの読みが同じときだけ候補にする
       (読みの違う聞き間違い「歯医者 → 会社」は入れない)。それまでに直したところ(Whisper の文と違うところ)と、
       よく使う言葉には触らない(LLM の補正が直した「ヒライ」を n-best の「平井」に戻さないため)
- 選ぶ(LLM): 一か所ずつ「【?】に入るのは A / B / C…?」と聞き、答えは書かせず記号の確率を読む(max_tokens 1、logprobs)
    並びを逆にしてもう一回聞き、平均する(先頭の選択肢が得をする癖を消す)。よく使う言葉も見せる
- 組み立てる(プログラム): 元の言葉以外の候補が THRESHOLD 以上で勝ったときだけ差し替える

- load(): 辞書を読む(時間がかかるので、入力補正の立ち上げと一緒に裏で呼ぶ)。読めなかったら確かめずに動く
- check(text, raw, nbest, context, vocabulary, deadline): 確かめた文を返す。時間切れ・エラーのときは、そこまでの文を返す
- take_alternatives(): 最後の check で確かめた場所から作った「一か所だけ変えた文」を、確率の高い順に返して忘れる
    [(文, 確率, (変えたところの始め, 長さ)), ...]。「候補を出す」の窓(candidate_window.py)で使う
    check が動かなかった入力では空(前の入力の分が残らないように、取り出したら忘れる)
"""

import json
import math
import os
import re
import threading
import time
import unicodedata
import urllib.request
import difflib

from paths import HOMOPHONE_DIR

THRESHOLD = 0.8        # 元の言葉以外が、この確率以上で勝ったら差し替える
MAX_CANDIDATES = 4     # 一か所に並べる候補の数(元の言葉のほかに)
ALT_MIN_PROB = 0.05    # 「候補を出す」の窓に並べる、一か所だけ変えた文の確率の下限
LETTERS = "ABCDEFGH"
TARGET_POS2 = {"一般", "サ変接続", "形容動詞語幹", "副詞可能", "ナイ形容詞語幹"}
KANJI = re.compile(r"[一-鿿々]")

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
VOCABULARY_HEAD = "この人がよく使う言葉(左のように聞こえたら、右の表記で書く)"

_tagger = None
_dict = None
_base_reading = {}
_lock = threading.Lock()
_records = []        # 今の check で確かめた場所 [{"pos": 今の文での位置, "chosen": 選んだ言葉, "probs": {言葉: 確率}}]
_alternatives = []   # 最後の check の「一か所だけ変えた文」(take_alternatives で取り出す)


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
            _base_reading = {(b, ct): r for r, v in data["verbs"]["by_reading"].items() for b, ct in v}
            _dict, _tagger = data, tagger
            print(f"同音異義語の確かめ: 辞書を読み込み({time.perf_counter() - t:.1f} 秒)")
            return True
        except Exception as e:
            print(f"同音異義語の確かめ: 辞書を読み込めませんでした(確かめずに動きます): {e}")
            return False


def is_ready():
    return _tagger is not None


# =====================================================
# 候補を出す(プログラム)
# =====================================================

def word_ends(text):
    """単語の終わりの位置(文の中の位置)。句読点補正(punctuate.py)で、句読点を入れてよい切れ目に使う"""
    return [pos + len(surface) for pos, surface, _ in _tokens(text)]


def _tokens(text):
    """[(文の中の位置, 表記, 品詞などの特徴)]"""
    out, pos = [], 0
    for w in _tagger(text):
        full = w.white_space + w.surface
        out.append((pos + len(full) - len(w.surface), w.surface, tuple(w.feature)))
        pos += len(full)
    return out


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


def dictionary_slots(text):
    """[(位置, 元の言葉, [候補…])]。名詞、動詞・形容詞、数字と助数詞"""
    out, toks, skip = [], _tokens(text), False
    for i, (start, surface, feat) in enumerate(toks):
        if skip:   # 前の数字と一緒に見た助数詞
            skip = False
            continue
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        if (feat[:2] == ("名詞", "数") and nxt and nxt[0] == start + len(surface)
                and nxt[2][:3] == ("名詞", "接尾", "助数詞") and _number_key(surface) in NUMBER_READINGS):
            alts = _number_alts(surface, nxt[1])
            if alts:
                out.append((start, surface + nxt[1], alts[:MAX_CANDIDATES]))
            skip = True
            continue
        if not KANJI.search(surface) or len(feat) < 8:
            continue
        alts = []
        if feat[0] == "名詞" and feat[1] in TARGET_POS2:
            # 同じ文字数のものだけ(「今日 → 饗」のような、字数の違う言葉に化けることはまず無い)
            alts = [s for s in _dict["nouns"].get(feat[7], []) if s != surface and len(s) == len(surface)]
            counter_alts = _counter_alts(feat[7], len(surface))[:1]
            if counter_alts:   # 数字と助数詞の書き方があるときだけ、名詞の候補を 1 つ減らして足す(産業 → 3行)
                alts = alts[:MAX_CANDIDATES - 1] + counter_alts
        elif feat[0] in ("動詞", "形容詞") and feat[1] == "自立":
            ctype, cform, base = feat[4], feat[5], feat[6]
            reading = _base_reading.get((base, ctype))
            for other, t in _dict["verbs"]["by_reading"].get(reading, []):
                if other == base or t != ctype:   # 活用の種類が同じもの(撮る・取る は どちらも 五段・ラ行)
                    continue
                s = _dict["verbs"]["forms"].get(f"{other}\t{t}\t{cform}")
                if s and s != surface and len(s) == len(surface) and s not in alts:
                    alts.append(s)
        if alts:
            out.append((start, surface, alts[:MAX_CANDIDATES]))
    return out


def _reading(surface, feat):
    """読み(カタカナ)。辞書に読みが無いときは、かなならカタカナにする。句読点・空白は空。数字・英字などは None"""
    if len(feat) > 7 and feat[7] != "*":
        return feat[7]
    s = unicodedata.normalize("NFKC", surface)
    if s and all("ぁ" <= c <= "ゟ" or "゠" <= c <= "ヿ" for c in s):
        return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)
    if s and all(unicodedata.category(c).startswith(("P", "Z")) for c in s):
        return ""
    return None


def _normalize(text):
    text = unicodedata.normalize("NFKC", text).lower()
    return "".join(c for c in text if not unicodedata.category(c).startswith(("P", "Z", "S")))


def protected_spans(raw, text, vocab_words):
    """今の文(text)の中で触らない範囲 [(始め, 終わり)]
    - それまでに直したところ: Whisper の文(raw)と比べて違うところ。消えたところは、その前後の 1 文字
    - よく使う言葉が出てくるところ"""
    spans = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=raw, b=text, autojunk=False).get_opcodes():
        if op != "equal":
            spans.append((max(j1 - 1, 0), j2 + 1) if j1 == j2 else (j1, j2))
    for w in vocab_words:
        i = text.find(w) if w else -1
        while i >= 0:
            spans.append((i, i + len(w)))
            i = text.find(w, i + 1)
    return spans


def whisper_slots(text, nbest, protect):
    """今の文と n-best の各文を単語の並びで比べ、置き換わったところの読みが同じなら候補にする。
    protect と少しでも重なる場所は候補にしない。重なった場所は短いほうを残す"""
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
            if None in ra or None in rb or "".join(ra) != "".join(rb) or not "".join(ra):
                continue
            start = t_tok[i1][0]
            orig = text[start:t_tok[i2 - 1][0] + len(t_tok[i2 - 1][1])]
            if any(start < e and s < start + len(orig) for s, e in protect):
                continue
            alt = "".join(s for _, s, _ in h_tok[j1:j2])
            if _normalize(alt) != _normalize(orig):
                found.setdefault((start, orig), [])
                if alt not in found[(start, orig)]:
                    found[(start, orig)].append(alt)
    out = []
    for (start, orig), alts in sorted(found.items(), key=lambda x: (len(x[0][1]), x[0][0])):
        if all(start + len(orig) <= s or s + len(o) <= start for s, o, _ in out):
            out.append((start, orig, alts[:MAX_CANDIDATES]))
    return sorted(out)


# =====================================================
# 選ぶ(LLM)と組み立てる(プログラム)
# =====================================================

def _system(vocab_lines):
    if not vocab_lines:
        return SYSTEM
    return SYSTEM + f"\n\n{VOCABULARY_HEAD}:\n" + "\n".join(f"- {v}" for v in vocab_lines)


def _ask_once(base_url, before, after, options, context_lines, vocab_lines, deadline):
    lines = (["直前の入力(古い順):"] + context_lines + [""]) if context_lines else []
    lines += [f"文: {before}【?】{after}", "", "選択肢:"]
    lines += [f"{LETTERS[i]}: {before}{w}{after}" for i, w in enumerate(options)]
    lines += ["", "答え(記号だけ):"]
    body = {"temperature": 0, "max_tokens": 1, "logprobs": True, "top_logprobs": 20,
            "messages": [{"role": "system", "content": _system(vocab_lines)},
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


def _log_slot(label, orig, p, replaced):
    """一か所ぶんの結果をコンソールに出す(しきい値を考えるための材料。差し替えなかった場所も出す)
    例: 同音異義語の確かめ(辞書): 分 → 文 74% / 分 26% … そのまま(80% に届かず)"""
    ranked = sorted(p.items(), key=lambda x: x[1], reverse=True)
    top = " / ".join(f"{w} {v:.0%}" for w, v in ranked[:3])
    best = ranked[0][0]
    if replaced:
        result = "差し替え"
    elif best == orig:
        result = "そのまま"
    else:
        result = f"そのまま({THRESHOLD:.0%} に届かず)"
    print(f"同音異義語の確かめ({label}): {orig} → {top} … {result}")


def _check_slots(base_url, text, slot_list, context_lines, vocab_lines, deadline, label):
    """左から一か所ずつ聞いて、(差し替えた文, 最後まで確かめたか) を返す。slot_list の位置は元の文での位置(重ならないこと)
    時間切れ・エラーのときは、そこまでに差し替えた文を返す。label はログに出す候補の出どころ(辞書 / Whisper)"""
    shift = 0
    for start, orig, alts in sorted(slot_list):
        s = start + shift
        before, after = text[:s], text[s + len(orig):]
        words = [orig] + alts
        try:
            p1 = _ask_once(base_url, before, after, words, context_lines, vocab_lines, deadline)
            p2 = _ask_once(base_url, before, after, list(reversed(words)), context_lines, vocab_lines, deadline)
        except (TimeoutError, OSError) as e:   # 時間切れは socket.timeout(OSError の仲間)
            print(f"同音異義語の確かめ: 時間切れ・エラー(そこまでの文で入力): {e}")
            return text, False
        except (ValueError, KeyError, IndexError) as e:
            print(f"同音異義語の確かめ: 返事を読めませんでした(そこまでの文で入力): {e}")
            return text, False
        p = {w: (p1[w] + p2[w]) / 2 for w in words}
        best = max(p, key=p.get)
        replaced = best != orig and p[best] >= THRESHOLD
        _log_slot(label, orig, p, replaced)
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
    """今の文から一か所だけ変えた文を、その言葉の確率の高い順に [(文, 確率, (始め, 長さ))]"""
    alts = {}
    for r in _records:
        pos, chosen = r["pos"], r["chosen"]
        if text[pos:pos + len(chosen)] != chosen:
            continue   # 位置がずれていたら(念のため)並べない
        for w, p in r["probs"].items():
            if w == chosen or p < ALT_MIN_PROB:
                continue
            alt = text[:pos] + w + text[pos + len(chosen):]
            if alt != text and (alt not in alts or p > alts[alt][0]):
                alts[alt] = (p, (pos, len(w)))
    return [(t, p, span) for t, (p, span) in sorted(alts.items(), key=lambda x: -x[1][0])]


def take_alternatives():
    """最後の check の「一か所だけ変えた文」を返して忘れる"""
    global _alternatives
    alts, _alternatives = _alternatives, []
    return alts


def check(base_url, text, raw, nbest, context_lines, vocabulary, deadline):
    """辞書の候補 → Whisper の同じ読みの候補 の順に確かめた文を返す。
    raw: Whisper の文(音声辞書を通す前)。nbest: Whisper の 2〜5 位の書き分け(無ければ空)
    context_lines: 直前の入力(「[時:分:秒] 文」)。vocabulary: よく使う言葉 [(よみがな, 言葉), ...]
    時間切れ・エラーのときは、そこまでに確かめた文を返す"""
    global _alternatives
    _records.clear()
    _alternatives = []
    if not is_ready() or not text:
        return text
    vocab_lines = [f"{r} → {w}" for r, w in vocabulary]
    vocab_words = [w for _, w in vocabulary]
    started = time.monotonic()
    n_dict = n_whisper = 0
    try:
        slots = dictionary_slots(text)
        n_dict = len(slots)
        text, finished = _check_slots(base_url, text, slots, context_lines, vocab_lines, deadline, "辞書")
        if finished and nbest:
            protect = protected_spans(raw, text, vocab_words)
            slots = whisper_slots(text, nbest, protect)
            n_whisper = len(slots)
            text, _ = _check_slots(base_url, text, slots, context_lines, vocab_lines, deadline, "Whisper")
    except Exception as e:   # 候補を出すところ(MeCab など)の思わぬエラーでも、入力は止めない
        print(f"同音異義語の確かめ: エラー(そこまでの文で入力): {e}")
    print(f"同音異義語の確かめ: 辞書 {n_dict} か所・Whisper {n_whisper} か所を {time.monotonic() - started:.2f} 秒で確かめた")
    _alternatives = _make_alternatives(text)
    return text
