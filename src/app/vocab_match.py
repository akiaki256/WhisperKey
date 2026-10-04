"""
読みの近さを測る部品(入力補正の「同音異義語の確かめ」と、Whisper に渡すヒント選びで使う)

- norm_reading(s): 比べるための読み(音の単位の並び)
- distance(hyp, ref): 読みの重みつきの違い
- limit_for(ref): これ以下の違いなら「近い」とみなす
- find(tagger, text, words): 文の中で、よく使う言葉に読みが近いところ
- written_spans(text, word): よく使う言葉が、それだけで書かれているところ
- select_hints(tagger, texts, vocabulary): Whisper に渡すヒント(読みが近いよく使う言葉)を選ぶ
- merge_hinted(first, second, hints): ヒントなし・ありの文字起こしをまぜる
"""

import difflib
import re
import unicodedata

# ---- 音の表 ----

ROWS = {
    "ア": "アカガサザタダナハバパマヤラワァャヮ",
    "イ": "イキギシジチヂニヒビピミリィ",
    "ウ": "ウクグスズツヅヌフブプムユルゥュヴ",
    "エ": "エケゲセゼテデネヘベペメレェ",
    "オ": "オコゴソゾトドノホボポモヨロヲォョ",
}
VOWEL = {c: v for v, cs in ROWS.items() for c in cs}
SMALL = set("ァィゥェォャュョヮ")

# 近いとみなす音の組(入れ替えの重みが軽い)
KNOWN_PAIRS = [("オ", "ウ"), ("ヨ", "オ"), ("ダ", "ラ"), ("リ", "ディ"), ("ヤ", "ア"), ("ユ", "ウ"), ("タ", "サ"), ("ク", "ツ"),
               ("デ", "レ"), ("ド", "ロ"),
               ("カ", "ガ"), ("キ", "ギ"), ("ク", "グ"), ("ケ", "ゲ"), ("コ", "ゴ"),
               ("サ", "ザ"), ("シ", "ジ"), ("ス", "ズ"), ("セ", "ゼ"), ("ソ", "ゾ"),
               ("タ", "ダ"), ("テ", "デ"), ("ト", "ド"),
               ("ハ", "バ"), ("ヒ", "ビ"), ("フ", "ブ"), ("ヘ", "ベ"), ("ホ", "ボ"),
               ("バ", "パ"), ("ビ", "ピ"), ("ブ", "プ"), ("ベ", "ペ"), ("ボ", "ポ"), ("シ", "ヒ")]
KNOWN = {}
for _a, _b in KNOWN_PAIRS:
    KNOWN.setdefault(_a, set()).add(_b)
    KNOWN.setdefault(_b, set()).add(_a)

DIGIT_READINGS = {"0": "ゼロ", "1": "イチ", "2": "ニ", "3": "サン", "4": "ヨン", "5": "ゴ", "6": "ロク", "7": "ナナ",
                  "8": "ハチ", "9": "キュウ", "10": "ジュウ"}
LETTER_NAMES = dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                        ["エー", "ビー", "シー", "ディー", "イー", "エフ", "ジー", "エイチ", "アイ", "ジェー", "ケー", "エル", "エム",
                         "エヌ", "オー", "ピー", "キュー", "アール", "エス", "ティー", "ユー", "ブイ", "ダブリュー", "エックス",
                         "ワイ", "ゼット"]))
SYMBOL_READINGS = {"π": "パイ", "Π": "パイ"}

FUNCTION_POS = {"助詞", "助動詞", "記号"}
CONTENT_POS = {"名詞", "接頭詞"}   # 探すところには、名詞(辞書に無い言葉も名詞になる)か接頭詞を一つは含める
MAX_SPAN_TOKENS = 4               # 何語までまたいで読みをつなげるか

HINT_WIDTH = 1.5    # ヒント選びの近さの幅(探す係のしきい値の何倍まで)
HINT_MAX = 10       # 一文に渡すヒントの数の上限


def to_kata(s):
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)


def to_hira(s):
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def is_kata(c):
    return "゠" <= c <= "ヿ"


def letters_to_kata(s):
    """英字(と π)をカタカナの読みに(QL → キューエル、V → ブイ)"""
    out = []
    for c in unicodedata.normalize("NFKC", s):
        if c in SYMBOL_READINGS:
            out.append(SYMBOL_READINGS[c])
        elif c.isascii() and c.isalpha():
            out.append(LETTER_NAMES[c.upper()])
        else:
            out.append(c)
    return "".join(out)


def morae(s):
    out = []
    for c in s:
        if c in SMALL and out:
            out[-1] += c
        else:
            out.append(c)
    return out


def vowel_of(m):
    return VOWEL.get(m[-1]) if m else None


def norm_reading(s):
    """比べるための読み: カタカナにして、伸ばす音・区切り・空白を抜き、長い母音(オウ・エイなど)を短くそろえる。
    ヴ と バ行 は同じ音として扱う(ヴェ → ベ)"""
    s = to_kata(unicodedata.normalize("NFKC", s))
    for a, b in (("ヴァ", "バ"), ("ヴィ", "ビ"), ("ヴェ", "ベ"), ("ヴォ", "ボ")):
        s = s.replace(a, b)
    s = s.replace("ヂ", "ジ").replace("ヅ", "ズ").replace("ヲ", "オ").replace("ヴ", "ブ")
    s = re.sub(r"[ー―‐\-・、。,.\s]", "", s)
    out = []
    for m in morae(s):
        if out and m == "ウ" and vowel_of(out[-1]) in ("ウ", "オ"):
            continue
        if out and m == "イ" and vowel_of(out[-1]) == "エ":
            continue
        out.append(m)
    return out


def _mora_cost(a, b):
    if a == b:
        return 0.0
    if b in KNOWN.get(a, ()):
        return 0.5
    return 1.0


def _extra_cost(seq, i):
    """seq[i] が余分なときの重さ。母音だけの音や、すぐ前と同じ音(言い淀みで足されやすい)は軽い"""
    m = seq[i]
    if m in "アイウエオ" or m in seq[max(0, i - 2):i] or m == "ン":
        return 0.5
    return 1.0


def distance(hyp, ref):
    """hyp(文の中の読み)と ref(よく使う言葉の読み)の重みつきの違い(音の単位)"""
    n, m = len(hyp), len(ref)
    d = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        d[i][0] = d[i - 1][0] + _extra_cost(hyp, i - 1)
    for j in range(1, m + 1):
        d[0][j] = d[0][j - 1] + 1.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + _extra_cost(hyp, i - 1),
                          d[i][j - 1] + 1.0,
                          d[i - 1][j - 1] + _mora_cost(hyp[i - 1], ref[j - 1]))
    return d[n][m]


def _plain_distance(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def limit_for(ref):
    """これ以下の違いなら近いとみなす。短い言葉ほど厳しく(2 音以下は、近い組の入れ替え一つまで)"""
    return 0.5 if len(ref) <= 2 else max(1.0, 0.34 * len(ref))


def _letters_only(s):
    return re.sub(r"[^0-9a-z]", "", unicodedata.normalize("NFKC", s).lower())


# ---- 文を単語に切る ----

def tokens(tagger, text):
    """[(文の中の位置, 表記, 品詞などの特徴)]"""
    out, pos = [], 0
    for w in tagger(text):
        full = w.white_space + w.surface
        out.append((pos + len(full) - len(w.surface), w.surface, tuple(w.feature)))
        pos += len(full)
    return out


def token_reading(surface, feat):
    """発音(カタカナ)。辞書に無い言葉は、かなならそのまま。句読点・空白は空。英字・数字は読めるものだけ、ほかは None"""
    if len(feat) > 8 and feat[8] != "*":
        return feat[8]
    if len(feat) > 7 and feat[7] != "*":
        return feat[7]
    s = unicodedata.normalize("NFKC", surface)
    if s and all("ぁ" <= c <= "ゟ" or is_kata(c) for c in s):
        return to_kata(s)
    if s in DIGIT_READINGS:   # 5時 → ゴ + ジ
        return DIGIT_READINGS[s]
    if re.fullmatch(r"[A-Z]{1,5}", s):   # GPT → ジーピーティー、V → ブイ
        return "".join(LETTER_NAMES[c] for c in s)
    if s and all(unicodedata.category(c).startswith(("P", "Z")) for c in s):
        return ""
    return None


def pron_of(tagger, text):
    """文の一部の発音(比べるための形)。英字(と π)は読みに直してから(Vラム → ブイラム)"""
    out = []
    for w in tagger(letters_to_kata(text)):
        f = w.feature
        if len(f) > 8 and f[8] != "*":
            out.append(f[8])
        elif len(f) > 7 and f[7] != "*":
            out.append(f[7])
        else:
            out.append(to_kata(w.surface))
    return norm_reading("".join(out))


# ---- よく使う言葉を探す ----

def _continues(a, b):
    """a と b が、一つの言葉としてつながって見えるか(カタカナ・伸ばし棒どうし、英数字どうし)"""
    if not a or not b:
        return False
    alnum = lambda c: c.isascii() and c.isalnum()
    return (is_kata(a) and is_kata(b)) or (alnum(a) and alnum(b))


def written_spans(text, word):
    """その言葉が、それだけで正しく書かれているところ [(始め, 終わり)]。
    前後にカタカナ・伸ばし棒(または英数字)が続いていたら、別の言葉の一部なので数えない(チェスリー の中の チェスリ)"""
    out = []
    i = text.find(word) if word else -1
    while i >= 0:
        j = i + len(word)
        if (not _continues(text[i - 1] if i > 0 else "", word[0])
                and not _continues(word[-1], text[j] if j < len(text) else "")):
            out.append((i, j))
        i = text.find(word, i + 1)
    return out


def find(tagger, text, words):
    """文の中で、よく使う言葉に読みが近いところ [(始め, 終わり, 元の言葉, [(よく使う言葉, 違い), ...])]。
    words: [{"word", "reading"}]。重ならないように、違いの小さいものから取る"""
    toks = tokens(tagger, text)
    reads = [token_reading(s, f) for _, s, f in toks]
    refs = [(w, norm_reading(w["reading"])) for w in words]
    found = []
    for i in range(len(toks)):
        for j in range(i + 1, min(len(toks), i + MAX_SPAN_TOKENS) + 1):
            start = toks[i][0]
            end = toks[j - 1][0] + len(toks[j - 1][1])
            orig = text[start:end]
            if not orig.strip() or orig[0] in "・、 " or orig[-1] in "・、 ":
                continue
            # 助詞・助動詞で始まる・終わるところは見ない(「の → ノート」のような、短い言葉への引っかかりを防ぐ)
            if toks[i][2][0] in FUNCTION_POS or toks[j - 1][2][0] in FUNCTION_POS:
                continue
            hits = []
            if None not in reads[i:j] and any(t[2][0] in CONTENT_POS for t in toks[i:j]):
                hyp = norm_reading("".join(reads[i:j]))
                if len(hyp) >= 2:
                    for w, ref in refs:
                        if w["word"] == orig or any(a < end and start < b for a, b in written_spans(text, w["word"])):
                            continue
                        if len(hyp) < len(ref) - 1:   # 短すぎるところ(「潤」→ 潤平)は見ない
                            continue
                        dist = distance(hyp, ref)
                        if dist <= limit_for(ref):
                            hits.append((w["word"], dist))
            lo = _letters_only(orig)
            if lo and re.fullmatch(r"[0-9A-Za-z\s\-_.]+", unicodedata.normalize("NFKC", orig)):
                for w, _ in refs:
                    lw = _letters_only(w["word"])
                    if (lw and w["word"] != orig and not any(a < end and start < b for a, b in written_spans(text, w["word"]))
                            and (lo == lw or (len(lw) >= 5 and _plain_distance(lo, lw) <= 1))):
                        hits.append((w["word"], 0.0 if lo == lw else 1.0))
            if hits:
                hits.sort(key=lambda x: x[1])
                found.append((start, end, orig, hits))
    found.sort(key=lambda x: (x[3][0][1], -(x[1] - x[0])))
    picked = []
    for f in found:
        if all(f[1] <= p[0] or p[1] <= f[0] for p in picked):
            picked.append(f)
    return sorted(picked)


# ---- Whisper に渡すヒント ----

def select_hints(tagger, texts, vocabulary, width=HINT_WIDTH, max_words=HINT_MAX):
    """文字起こし(texts)の読みに近いよく使う言葉を、近い順に [(読みのカタカナ, 言葉)]。vocabulary: [(読み, 言葉)]
    近いものが無ければ空"""
    refs = [(r, w, norm_reading(r)) for r, w in vocabulary]
    best = {}
    for text in dict.fromkeys(t for t in texts if t):
        toks = tokens(tagger, text)
        reads = [token_reading(s, f) for _, s, f in toks]
        for i in range(len(toks)):
            for j in range(i + 1, min(len(toks), i + MAX_SPAN_TOKENS) + 1):
                if None in reads[i:j]:
                    continue
                if toks[i][2][0] in FUNCTION_POS or toks[j - 1][2][0] in FUNCTION_POS:
                    continue
                hyp = norm_reading("".join(reads[i:j]))
                if len(hyp) < 2:
                    continue
                for r, w, ref in refs:
                    if not ref or len(hyp) < len(ref) - 1:
                        continue
                    d = distance(hyp, ref)
                    if d <= limit_for(ref) * width:
                        score = d / len(ref)
                        if (r, w) not in best or score < best[(r, w)]:
                            best[(r, w)] = score
    return [(to_kata(r), w) for r, w in sorted(best, key=best.get)[:max_words]]


def merge_hinted(first, second, hints, width=HINT_WIDTH):
    """一回目(ヒントなし)と二回目(ヒントあり)の文をまぜる。二回目で変わったところのうち、ヒントの言葉に当たる変化だけ取り、
    ほかは一回目に戻す"""
    exact = []
    for h in hints:
        i = second.find(h) if h else -1
        while i >= 0:
            exact.append((i, i + len(h)))
            i = second.find(h, i + 1)
    refs = [norm_reading(h) for h in hints if h]

    def run_around(j1, j2):   # 変化を含むカタカナのかたまり
        a, b = j1, max(j2, j1)
        while a > 0 and is_kata(second[a - 1]):
            a -= 1
        while b < len(second) and is_kata(second[b]):
            b += 1
        return a, b

    def hits(j1, j2):
        if any(s < j2 and j1 < e for s, e in exact) or (j1 == j2 and any(s <= j1 <= e for s, e in exact)):
            return True
        a, b = run_around(j1, j2)
        if any(s < b and a < e for s, e in exact):
            return False
        run = second[a:b]
        if not run:
            return False
        hyp = norm_reading(run)
        return any(len(hyp) >= len(ref) - 1 and distance(hyp, ref) <= limit_for(ref) * width for ref in refs)

    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=first, b=second, autojunk=False).get_opcodes():
        if op == "equal":
            out.append(first[i1:i2])
        elif hits(j1, j2):
            out.append(second[j1:j2])
        else:
            out.append(first[i1:i2])
    return "".join(out)
