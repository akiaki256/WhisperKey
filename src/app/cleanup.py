import os

from paths import TEMP_DIR

# tempファイル内にあるファイルを消去
def cleanup_temp():
    temp_dir = TEMP_DIR

    if not os.path.exists(temp_dir):
        print("tempファイルが見つかりませんでした")
        return
    
    files = os.listdir(temp_dir)

    # temp_*.wavだけ抽出
    audio_files = []
    for f in files:
        if f.startswith('temp_') and f.endswith('.wav'):
            audio_files.append(f)

    if len(audio_files) != 0 :
        for i in audio_files:
            rm_file_path = os.path.join(temp_dir, i)

            try:
                os.remove(rm_file_path)
                print(f"{i}：削除に成功")
            except Exception as e:
                print(f"{i}：削除に失敗")
                print(f"error: {e}")
    
    else:
        print("クリーンアップ：一時音声ファイルは見つかりませんでした")
        return