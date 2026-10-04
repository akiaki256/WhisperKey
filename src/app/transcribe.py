import os
import re
import time
import traceback
from datetime import datetime

import audio
import candidates
import config
import config_store
import convert_dict
import command
import history
import homophone
import llm_correct
import llm_vocab
import undo_input
import model
import paste
import punctuate
import vocab_match
from key_shortcut import MainStateManager

state_manager = MainStateManager()


LANGUAGE = config_store.LANGUAGE   # 日本語だけ

# ハルシネーションフレーズリスト
HALLUCINATION_PHRASES = [
        "Thank you for waiting",
        "Thanks for watching!",
        "Thanks for waiting.",
        "Thanks for watching.",
        "Thank you for watching.",
        "Thanks",
        "Thank you", 
        "Waiting",
        "ご視聴ありがとうございました!",
        "ご視聴ありがとうございました",
        "ご視聴ありがとうございました。",
        "ありがとうございました",
        "ありがとうございました。",
]

NBEST_BEAM = 5   # Whisper の 2〜5 位を何通り取るか(ビームサーチの幅)

# Whisper によく使う言葉のヒントを渡すモデル
HINT_MODELS = {"large-v3", "large-v3-turbo"}

TRANSCRIBE_OPTIONS = dict(language=LANGUAGE,
                          beam_size=1,           # デフォルト5→1で高速化
                          best_of=1,             # デフォルト5→1で高速化
                          temperature=0,         # 安定した出力
                          vad_filter=True,       # 音声検出フィルター
                          vad_parameters=dict(min_silence_duration_ms=500,  # 無音判定時間
                                              speech_pad_ms=200))           # 音声前後の余白


def transcribe_text(filepath, hotwords=None):
    """文字起こしした文(区切りごとの文をつないだもの)。hotwords: Whisper に渡すヒント(無ければ None)"""
    segments, _ = model.get_model().transcribe(filepath, hotwords=hotwords, **TRANSCRIBE_OPTIONS)
    # 日本語だけなので、区切りの間に空白は入れない。英字どうしが並ぶときだけ空白でつなぐ
    return join_segments([segment.text for segment in segments])


def whisper_nbest(filepath, hotwords=None):
    """Whisper の 2〜5 位(ビームサーチの 1〜NBEST_BEAM 位の文)。入力補正の「同音異義語の確かめ」で使う
    faster-whisper の transcribe() は 1 位しか返さないので、中の generate を直接呼ぶ。VAD は通さず、頭の 30 秒を 1 枠で
    (kotoba で +0.2 秒くらい。取れなかったら空で、確かめは辞書の候補だけになる)
    hotwords: Whisper に渡すヒント(文字起こしと同じもの。無ければ None)"""
    try:
        from faster_whisper.audio import decode_audio, pad_or_trim
        from faster_whisper.tokenizer import Tokenizer
        whisper = model.get_model()
        fe = whisper.feature_extractor
        segment = pad_or_trim(fe(decode_audio(filepath, sampling_rate=fe.sampling_rate))[:, : fe.nb_max_frames])
        tokenizer = Tokenizer(whisper.hf_tokenizer, whisper.model.is_multilingual, task="transcribe",
                              language=LANGUAGE)
        prompt = whisper.get_prompt(tokenizer, [], without_timestamps=True, hotwords=hotwords)
        # 長さはヒントの前置きも込みで数える(ヒントで枠を使い切って、本文が空にならないように)
        result = whisper.model.generate(whisper.encode(segment), [prompt], beam_size=NBEST_BEAM,
                                        num_hypotheses=NBEST_BEAM, max_length=min(448, len(prompt) + 224),
                                        suppress_blank=True, suppress_tokens=[-1])[0]
        hyps = [tokenizer.decode([t for t in ids if t < tokenizer.eot]).strip() for ids in result.sequences_ids]
        print(f"Whisper の 2〜5 位: {' / '.join(dict.fromkeys(hyps))}")   # 同じ文は一つにまとめて出す
        return hyps
    except Exception as e:
        print(f"Whisper の 2〜5 位を取れませんでした(同音異義語の確かめは辞書の候補だけで): {e}")
        return []


def hinted_transcription(filepath, text, nbest, vocabulary):
    """Whisper によく使う言葉のヒントを渡して、もう一回文字起こしする(HINT_MODELS のときだけ)
    一回目の文と 2〜5 位の読みに近いよく使う言葉を選んで渡し、ヒントに当たる変化だけを使う
    (文, 2〜5 位, 渡したヒント) を返す。ヒントが無ければ一回目のまま
    思わぬエラーのときも一回目のまま(入力は止めない)"""
    if config.get("model_size") not in HINT_MODELS or not vocabulary or not homophone.is_ready():
        return text, nbest, []
    try:
        picked = vocab_match.select_hints(homophone.tagger(), [text] + list(nbest), vocabulary)
        if not picked:
            return text, nbest, []
        hints = [k for k, _ in picked]
        hotwords = "、".join(hints)
        second = transcribe_text(filepath, hotwords)
        merged = vocab_match.merge_hinted(text, second, hints)
        print(f"Whisper のヒント: {hotwords} → {second}" + (f"(使ったのは {merged})" if merged != second else ""))
        return merged, whisper_nbest(filepath, hotwords) or nbest, hints
    except Exception as e:
        print(f"Whisper のヒント: エラー(一回目の文のまま): {e}")
        return text, nbest, []


PERIODS = "。．"   # 「。」を消すときに消すもの
COMMAS = "、，"    # 「、」を消すときに消すもの
CLOSING_BRACKETS = "」』）)］]】"   # この前の「。」は、スペースにせずに消すだけ(「はい。」→「はい」)


def finish_text(text):
    """入力する直前の仕上げ
    設定で「「、」を消す」がオンなら、「、」を全部消す(スペースにはしない)
    設定で「「。」を消す」がオンなら、文の最後の「。」は消して、文と文の間の「。」は半角スペースにする(「はい。行きます。」→「はい 行きます」)"""
    if config.get("remove_commas"):
        text = re.sub(f"[{COMMAS}]", "", text)
    if config.get("remove_periods"):
        text = text.rstrip().rstrip(PERIODS + " 　").rstrip()
        text = re.sub(f"[{PERIODS}]+\\s*(?=[{re.escape(CLOSING_BRACKETS)}])", "", text)
        text = re.sub(f"[{PERIODS}]+\\s*", " ", text)
    return text


def print_timings(recorded, started, steps):
    """入力ごとに、どこで何秒かかったかを一行で出す(速さを測るため)
    合計は、録音を区切ってから入力するまで(文字起こしの順番待ちを含む)
    無音と判定するまでに待った時間(無音時間の設定で決まる)は、合計の外に別に出す
    recorded: audio.recorded の一件(無ければ、文字起こしを始めたところから数える)"""
    parts = []
    origin = started
    head = ""
    if recorded:
        origin = recorded["queued"]   # 録音を区切ったところ
        head = f"声 {recorded['voice']:.1f}秒 | 無音の判定 {recorded['silence']:.2f}秒 | "
        parts.append(f"待ち {started - recorded['queued']:.2f}")
    parts += [f"{name} {sec:.2f}" for name, sec in steps]
    print(f"時間: {head}{' → '.join(parts)} | 合計 {time.monotonic() - origin:.2f}秒")


def join_segments(texts):
    """Whisper の区切りごとの文をつなぐ。日本語なので空白は入れず、英数字どうしが並ぶときだけ空白を一つ入れる
    (前は空白でつないでいて、二文以上話すと「文。 文。」の空白が候補の窓で違いとして引っかかった)"""
    out = ""
    for t in texts:
        t = t.strip()
        if not t:
            continue
        if out and out[-1].isascii() and out[-1].isalnum() and t[0].isascii() and t[0].isalnum():
            out += " "
        out += t
    return out


def filter_hallucination(text):
    cleaned_text = text.strip()  # 前後の空白を除去して完全一致をチェック
    if cleaned_text in HALLUCINATION_PHRASES:# ハルシネーションフレーズと完全一致したら空文字を返す
        print(f"ハルシネーション検出: '{cleaned_text}' -> 削除")
        return ""
    return text

#faster-whisperに送信してテキスト化して貼り付け
def whisper_function(wav_queue):
    """
    言語は、画面で変えたらすぐ効くように、毎回 config から読む

    モデルは毎回 model.get_model() から受け取る(選ばれているモデルが手元に無いまま起動したときは、
    ダウンロードして読み込まれるまで待つ)
    wav_queue: 音声ファイルのキュー
    """

    # CSVファイルからユーザー変換辞書とコマンドを作成する
    # どちらも画面から保存されたらすぐ効くように、毎回 get_current() から使う
    # (読み込みに失敗したときは空になり、変換・実行されないだけ)
    if convert_dict.load_convert_dict() is None:
        print("ユーザー変換辞書取得：失敗（辞書変換機能OFF）")
    else:
        print("ユーザー変換辞書取得：成功")

    if command.load_command_dict() is None:
        print("コマンド辞書取得：失敗（コマンド実行機能OFF）")
    else:
        print("コマンド辞書取得：成功")


    while True:
        print("Whisperスレッド：キュー待機中...")
        filepath = wav_queue.get()
        started = time.monotonic()
        recorded = audio.recorded.pop(filepath, None)   # 話し終わりの時刻など(かかった時間を出すため)
        steps = []   # [(名前, 秒)]。入力ごとに、どこで何秒かかったかを最後に一行で出す
        try:
            # 入力ひとつごとの区切り(ログを見て、どこからどこまでが一回の入力かわかるように)
            print(f"\n{'─' * 20} 入力 {datetime.now().strftime('%H:%M:%S')} {'─' * 20}")
            print(f"処理開始: {filepath}")

            t = time.monotonic()
            text = transcribe_text(filepath)
            steps.append(("文字起こし", time.monotonic() - t))

            ## ハルシネーションフレーズを除去
            filtered_text = filter_hallucination(text)

            ## ユーザー辞書適応
            result = convert_dict.convert_text(filtered_text, convert_dict.get_current())

            # コマンドキーワードが検知されたらコマンド実行、そうでなければ貼り付け
            # 辞書変換後の文字列で判定する(表記揺れを辞書側で吸収できるようにするため)
            command_executed = command.execute_command(result, command.get_current())

            if command_executed:
                print("コマンドを実行")
                undo_input.forget()  # 直前がコマンドなので、その前の入力は取り消させない
                candidates.forget()  # 「候補を出す」で、その前の入力を入れ替えさせない

            elif result:  # 空文字でない場合のみ貼り付け
                # 入力補正(GPU版、オンのとき)。音声実行の判定は直す前の文で済ませてある
                # (LLM が合言葉を言い換えて、実行されなくなるのを防ぐ)
                # 同音異義語の確かめのために、Whisper の 2〜5 位も渡す(補正が動くときだけ取る)
                # よく使う言葉に読みが近いところがあれば、Whisper にヒントを渡してもう一回文字起こしする
                nbest = []
                vocabulary = llm_vocab.get_current()
                to_check = result
                if llm_correct.will_correct():
                    t = time.monotonic()
                    nbest = whisper_nbest(filepath)
                    steps.append(("2〜5 位", time.monotonic() - t))
                    t = time.monotonic()
                    hinted, nbest, hints = hinted_transcription(filepath, filtered_text, nbest, vocabulary)
                    if hints:
                        steps.append(("ヒント", time.monotonic() - t))
                        if hinted != filtered_text:
                            filtered_text = hinted
                            result = convert_dict.convert_text(filtered_text, convert_dict.get_current())
                    # 言い淀みを消す(設定でオンのとき)。消す前の文は「候補を出す」の窓に出る(補正前として)
                    if config.get("remove_stutter"):
                        to_check = homophone.remove_stutter(result)
                        if to_check != result:
                            print(f"言い淀みを消す: {result} → {to_check}")
                fixed = llm_correct.correct(to_check, vocabulary, raw=filtered_text, nbest=nbest)
                steps += list(llm_correct.timings.items())   # 確かめ・句読点(動いたものだけ)
                # 「候補を出す」の候補(同音異義語の確かめの窓の文と、補正する前の文)
                # 句読点補正が動いたら、候補の句読点も入力する文とそろえる
                alternatives = [(t, p) for t, p, _ in homophone.take_alternatives()]
                before_correction = result
                if llm_correct.will_punctuate():
                    alternatives = [(punctuate.match(fixed, t), p) for t, p in alternatives]
                    before_correction = punctuate.match(fixed, result)
                fixed = finish_text(fixed)  # 「。」を消す(設定でオンのとき)
                t = time.monotonic()
                paste.paste(fixed)  # Win + V の履歴に残さない印つきで貼り付ける(設定でオフにできる)
                steps.append(("貼り付け", time.monotonic() - t))
                print_timings(recorded, started, steps)
                print(f"入力: {fixed[:30]}...") # 最初の30文字を表示
                undo_input.remember(fixed)  # 取り消しのキーで消せるように
                history.add(fixed, raw=result)  # 入力した文章だけを残す(音声実行は残さない)
                # 候補も入力と同じ仕上げをする(入力された文と、窓の 1 番がずれないように)
                candidates.set_last(fixed, finish_text(before_correction), [(finish_text(t), p) for t, p in alternatives])

            # 処理済みファイルを削除
            os.remove(filepath)
            print(f"削除: {filepath}")
        except Exception:
            # 思わぬエラーでも、この係は止めない(止まると、次からの入力が全部たまったままになる)
            print("文字起こし: エラー(この入力は飛ばして続けます)")
            traceback.print_exc()
        finally:
            # 途中でエラーが起きても、残りの数は必ず減らす(黄色が消えなくなるのを防ぐ)
            state_manager.finish_pending()