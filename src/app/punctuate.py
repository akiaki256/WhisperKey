"""
入力補正の「句読点補正」(GPU版のみ。入力補正と句読点補正がオンのとき、同音異義語の確かめのあとに動く)
Whisper の句読点は、その場その場で付いたり付かなかったりする。そこで、いったん全部はがして、LLM に付け直させる。
やり方の決まりごとは実験の結果から(v5_LLM補正の実験/結果/句読点/)。

- はがす(プログラム): 「、」「。」を全部取る(「？」「！」は残す)
- 付ける(LLM): 句読点を付けた文を書かせる。llama-server の文法(GBNF)で縛るので、元の文字をこの順で書くことしかできない
    句読点を入れてよいのは MeCab の単語の切れ目だけ(英数字どうしの間、？！の前後、空白の後は除く)。最後は「。」だけ
- 絞る(プログラム): LLM が「、」を選んだ確率が COMMA_THRESHOLD より低ければ、その「、」は付けない
    (「次は、」「平均速度は、」のような付けすぎが消える。つなぎの「、」はほぼ 1.00 なので残る)
    足すことはしない。「。」は LLM が書いたまま

- run(base_url, text, deadline): 句読点を付け直した文。時間切れ・エラーのときは text をそのまま返す
- match(source, target): target の句読点を source と同じにする(「候補を出す」の候補を、入力した文とそろえるため)
"""

import difflib
import json
import math
import re
import time
import urllib.request

import homophone

COMMA_THRESHOLD = 0.8   # LLM が「、」を選んだ確率がこれより低ければ付けない
PUNCT = "、。，．"        # はがすもの(英数字の , . は触らない)
MARKS = "、。"           # 付けるもの
NO_AFTER = "？！?!、。"    # この後には句読点を入れない
NO_BEFORE = "？！?!"      # この前には句読点を入れない

SYSTEM = """あなたは音声入力の文に句読点を付ける係です。
渡された文を、「、」と「。」を付けてそのまま書き写してください。文字を足したり、消したり、言い換えたりはしません。

付け方:
- 文の終わりには「。」を付ける。「？」「！」で終わるときは付けない
- 話の途中で区切って入力することがある。「明後日の」「駅前で」「先生が」のように、文が言い切られずに途中で終わっているときは、最後に何も付けない
- 文が二つ以上続いているときは、それぞれの文の終わりに「。」を付ける
- 「、」は、読むときに息をつくところに付ける。目安:
  - 「〜て」「〜けど」「〜ので」「〜から」「〜たら」のように、文をつなぐ言葉の後
  - 長い主語や、「それと」「じゃあ」「あ」のような前置きの後(「今日は」「次は」のような短い主語の後には付けない)
  - 「と」「や」を使わずに物を並べているところの間
- 短い文や、ひとまとまりで読めるところには「、」を付けない"""

EXAMPLES = [
    ("昨日買った本まだ読めてないんだけど週末には読むつもり", "昨日買った本、まだ読めてないんだけど、週末には読むつもり。"),
    ("わかったじゃあ駅で待ってるね", "わかった。じゃあ、駅で待ってるね。"),
    ("牛乳と卵を買ってきて", "牛乳と卵を買ってきて。"),
    ("今日は朝から雨だった", "今日は朝から雨だった。"),
    ("明日の朝に", "明日の朝に"),
    ("ありがとう", "ありがとう。"),
]


def strip(text):
    return re.sub(f"[{PUNCT}]", "", text)


def _is_ascii_word(ch):
    return ch.isascii() and (ch.isalnum() or ch in "_./-:")


def _points(text):
    """句読点を入れてよい位置(その文字の前に入れる。最後 = len(text) も含む)"""
    ok = set()
    for p in homophone.word_ends(text):
        if p <= 0:
            continue
        before = text[p - 1]
        after = text[p] if p < len(text) else ""
        if before in NO_AFTER or before.isspace() or (after and after in NO_BEFORE):
            continue
        if after and _is_ascii_word(before) and _is_ascii_word(after):
            continue
        ok.add(p)
    return sorted(ok)


def _literal(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _grammar(text, points):
    """元の文字をこの順で書き、points のところにだけ「、」か「。」を一つ入れてよい文法(最後は「。」だけ)"""
    parts, last = [], 0
    for p in points:
        if p > last:
            parts.append(_literal(text[last:p]))
        parts.append('"。"?' if p == len(text) else "p?")
        last = p
    if last < len(text):
        parts.append(_literal(text[last:]))
    return "root ::= " + " ".join(parts) + '\np ::= "、" | "。"\n'


def run(base_url, text, deadline):
    started = time.monotonic()
    bare = strip(text).strip()
    if not bare or not homophone.is_ready():
        return text
    messages = [{"role": "system", "content": SYSTEM}]
    for q, a in EXAMPLES:
        messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    messages.append({"role": "user", "content": bare})
    try:
        body = {"temperature": 0, "max_tokens": len(bare) * 2 + 20, "messages": messages,
                "logprobs": True, "grammar": _grammar(bare, _points(bare))}
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            raise TimeoutError
        req = urllib.request.Request(base_url + "/v1/chat/completions", json.dumps(body).encode("utf-8"),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            choice = json.load(r)["choices"][0]
        out, dropped = "", []
        for c in choice["logprobs"]["content"]:
            if c["token"] == "、" and math.exp(c["logprob"]) < COMMA_THRESHOLD:
                dropped.append(f"{out[-6:]}|({math.exp(c['logprob']):.2f})")
                continue
            out += c["token"]
    except Exception as e:   # 時間切れ・つながらない・返事を読めない。入力は止めない
        print(f"句読点補正: 時間切れ・エラー(付け直さずに入力): {e}")
        return text
    if strip(out) != bare:   # 縛っているので起きないはず。念のため
        print(f"句読点補正: 元の文と文字が違うので捨てました: {out[:40]!r}")
        return text
    print(f"句読点補正: {time.monotonic() - started:.2f} 秒"
          + (f"(自信の低い「、」を付けない: {' '.join(dropped)})" if dropped else ""))
    if out != text:
        print(f"句読点補正: {text} → {out}")
    return out


def match(source, target):
    """target の句読点を source と同じにする。source と文字が同じところにだけ、source の句読点を入れる"""
    src_bare, marks = "", {}   # marks: 句読点をはがした source での位置 → その位置の前に入る句読点
    for ch in source:
        if ch in PUNCT:
            marks[len(src_bare)] = marks.get(len(src_bare), "") + ch
        else:
            src_bare += ch
    tgt_bare = strip(target)
    to_target = {}   # source の文字の位置 → 同じ文字の target での位置
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=src_bare, b=tgt_bare, autojunk=False).get_opcodes():
        if op == "equal":
            to_target.update({i1 + k: j1 + k for k in range(i2 - i1)})
    inserts = {}     # target の位置 → その位置の前に入れる句読点
    for p, mark in marks.items():
        if p == len(src_bare):
            j = len(tgt_bare)                 # 最後
        elif p in to_target:
            j = to_target[p]                  # 後ろの文字が同じなら、その前に
        elif p - 1 in to_target:
            j = to_target[p - 1] + 1          # 前の文字が同じなら、その後に
        else:
            continue                          # 前も後ろも変わったところは付けない
        inserts[j] = inserts.get(j, "") + mark
    return "".join(inserts.get(j, "") + ch for j, ch in enumerate(tgt_bare)) + inserts.get(len(tgt_bare), "")
