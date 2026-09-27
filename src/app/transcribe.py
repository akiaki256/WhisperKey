import os
import pyperclip
import keyboard
import config
import convert_dict
import command
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
def whisper_function(model, wav_queue):
    """
    言語は、画面で変えたらすぐ効くように、毎回 config から読む

    model: WhisperModelのインスタンス
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

            segments, info = model.transcribe(filepath,
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
            
            elif result:  # 空文字でない場合のみ貼り付け
                pyperclip.copy(result)
                keyboard.send('ctrl+v')
                print(f"入力: {result[:30]}...") # 最初の30文字を表示

            # 処理済みファイルを削除
            os.remove(filepath)
            print(f"削除: {filepath}")
        finally:
            # 途中でエラーが起きても、残りの数は必ず減らす(黄色が消えなくなるのを防ぐ)
            state_manager.finish_pending()