import os
import re
import traceback
from datetime import datetime

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

NBEST_BEAM = 5   # 書き分けを何通り取るか(ビームサーチの幅)


def whisper_nbest(filepath):
    """Whisper の書き分け(ビームサーチの 1〜NBEST_BEAM 位の文)。入力補正の「同音異義語の確かめ」で使う
    faster-whisper の transcribe() は 1 位しか返さないので、中の generate を直接呼ぶ。VAD は通さず、頭の 30 秒を 1 枠で
    (kotoba で +0.2 秒くらい。取れなかったら空で、確かめは辞書の候補だけになる)"""
    try:
        from faster_whisper.audio import decode_audio, pad_or_trim
        from faster_whisper.tokenizer import Tokenizer
        whisper = model.get_model()
        fe = whisper.feature_extractor
        segment = pad_or_trim(fe(decode_audio(filepath, sampling_rate=fe.sampling_rate))[:, : fe.nb_max_frames])
        tokenizer = Tokenizer(whisper.hf_tokenizer, whisper.model.is_multilingual, task="transcribe",
                              language=LANGUAGE)
        prompt = whisper.get_prompt(tokenizer, [], without_timestamps=True)
        result = whisper.model.generate(whisper.encode(segment), [prompt], beam_size=NBEST_BEAM,
                                        num_hypotheses=NBEST_BEAM, max_length=224,
                                        suppress_blank=True, suppress_tokens=[-1])[0]
        hyps = [tokenizer.decode([t for t in ids if t < tokenizer.eot]).strip() for ids in result.sequences_ids]
        print(f"Whisper の書き分け: {' / '.join(dict.fromkeys(hyps))}")   # 同じ文は一つにまとめて出す
        return hyps
    except Exception as e:
        print(f"Whisper の書き分けを取れませんでした(同音異義語の確かめは辞書の候補だけで): {e}")
        return []


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
        try:
            # 入力ひとつごとの区切り(ログを見て、どこからどこまでが一回の入力かわかるように)
            print(f"\n{'─' * 20} 入力 {datetime.now().strftime('%H:%M:%S')} {'─' * 20}")
            print(f"処理開始: {filepath}")

            segments, info = model.get_model().transcribe(filepath,
                                                language=LANGUAGE,
                                                beam_size=1,           # デフォルト5→1で高速化
                                                best_of=1,            # デフォルト5→1で高速化  
                                                temperature=0,        # 安定した出力
                                                vad_filter=True,      # 音声検出フィルター
                                                vad_parameters=dict(min_silence_duration_ms=500,  # 無音判定時間
                                                                    speech_pad_ms=200)            # 音声前後の余白
                                                )
        
            # テキストを結合
            text = " ".join([segment.text for segment in segments])

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
                # 同音異義語の確かめのために、Whisper の書き分けも渡す(補正が動くときだけ取る)
                nbest = whisper_nbest(filepath) if llm_correct.will_correct() else []
                fixed = llm_correct.correct(result, llm_vocab.get_current(), raw=filtered_text, nbest=nbest)
                # 「候補を出す」の候補(同音異義語の確かめの「一か所だけ変えた文」と、補正する前の文)
                # 句読点補正が動いたら、候補の句読点も入力する文とそろえる
                alternatives = [(t, p) for t, p, _ in homophone.take_alternatives()]
                before_correction = result
                if llm_correct.will_punctuate():
                    alternatives = [(punctuate.match(fixed, t), p) for t, p in alternatives]
                    before_correction = punctuate.match(fixed, result)
                fixed = finish_text(fixed)  # 「。」を消す(設定でオンのとき)
                paste.paste(fixed)  # Win + V の履歴に残さない印つきで貼り付ける(設定でオフにできる)
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