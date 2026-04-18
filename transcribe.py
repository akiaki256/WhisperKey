import os
import pyperclip
import pyautogui
from convert_dict import load_convert_dict, convert_text
from command import load_command_dict, execute_command


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
def whisper_function(model, language, wav_queue):
    """
    model: WhisperModelのインスタンス
    language: 言語設定
    wav_queue: 音声ファイルのキュー
    """

    # CSVファイルからユーザー変換辞書を作成する
    user_convert_dict_status = True
    command_dict_status = True

    user_convert_dict = load_convert_dict()
    if user_convert_dict is None:
        print("ユーザー変換辞書取得：失敗（辞書変換機能OFF）")
        user_convert_dict_status = False
    else:
        print("ユーザー変換辞書取得：成功")
        
    command_dict = load_command_dict()
    if command_dict is None:
        print("コマンド辞書取得：失敗（コマンド実行機能OFF）")
        command_dict_status = False
    else:
        print("コマンド辞書取得：成功")       
    

    while True:
        print("Whisperスレッド：キュー待機中...")
        filepath = wav_queue.get()
        print(f"処理開始: {filepath}")

        segments, info = model.transcribe(filepath,
                                            language=language,
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
        if user_convert_dict_status == True:
            original_text = filtered_text
            result = convert_text(filtered_text, user_convert_dict)
        else:
            original_text = filtered_text
            result = filtered_text

        # コマンドキーワードが検知されたらコマンド実行、そうでなければ貼り付け
        command_executed = False
        if command_dict_status == True:
            command_executed = execute_command(original_text, command_dict)

        if command_executed:
            print("コマンドを実行")
            
        elif result:  # 空文字でない場合のみ貼り付け
            pyperclip.copy(result)
            pyautogui.hotkey('ctrl', 'v')
            print(f"入力: {result[:30]}...") # 最初の30文字を表示

        # 処理済みファイルを削除
        os.remove(filepath)
        print(f"削除: {filepath}")