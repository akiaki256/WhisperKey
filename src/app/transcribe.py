import os
import config
import convert_dict
import command
import history
import llm_correct
import undo_input
import model
import paste
from key_shortcut import MainStateManager

state_manager = MainStateManager()


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
            print(f"処理開始: {filepath}")

            segments, info = model.get_model().transcribe(filepath,
                                                language=config.get("language"),
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

            elif result:  # 空文字でない場合のみ貼り付け
                # 入力補正(GPU版、オンのとき)。音声実行の判定は直す前の文で済ませてある
                # (LLM が合言葉を言い換えて、実行されなくなるのを防ぐ)
                fixed = llm_correct.correct(result)
                paste.paste(fixed)  # Win + V の履歴に残さない印つきで貼り付ける(設定でオフにできる)
                print(f"入力: {fixed[:30]}...") # 最初の30文字を表示
                undo_input.remember(fixed)  # 取り消しのキーで消せるように
                history.add(fixed, raw=result)  # 入力した文章だけを残す(音声実行は残さない)

            # 処理済みファイルを削除
            os.remove(filepath)
            print(f"削除: {filepath}")
        finally:
            # 途中でエラーが起きても、残りの数は必ず減らす(黄色が消えなくなるのを防ぐ)
            state_manager.finish_pending()