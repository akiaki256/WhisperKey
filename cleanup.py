import os
# tempファイル内にあるファイルを消去
def cleanup_temp():
    this_file = os.path.abspath(__file__)

    project_root = os.path.dirname(this_file)

    temp_dir = os.path.join(project_root, 'temp')
    
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
            except:
                print(f"{i}：削除に失敗")
    
    else:
        print("クリーンアップ：一時音声ファイルは見つかりませんでした")
        return