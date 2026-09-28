# WhisperKey

音声をキー入力に変換する、Windows用のローカル音声入力ツール。

ショートカットキーで録音をオン/オフし、話した内容を自動で文字起こしして、現在フォーカスしているアプリケーションに貼り付けます。音声認識は OpenAI の Whisper モデルをローカル実行します。GPU版では、聞き間違いをローカルの LLM で直してから入力することもできます。インターネット接続が必要なのは、初めて使うときのモデルのダウンロードだけで、そのあとはオフラインで動作します。

---

## 特徴

- **完全ローカル動作**: 音声データは外部に送信されません。インターネット接続なしで動作します。
- **Windows 常駐型**: システムトレイに常駐し、ショートカットキー(初期設定 F9)で録音をオン/オフします。キーを押している間だけ録音するプッシュトゥトークにも切り替えられます。
- **辞書変換**: 頻出の誤認識や表記揺れをユーザー定義の辞書で補正できます。空文字への変換でハルシネーションのブロックも可能です。入力履歴でなぞった言葉を、そのまま辞書に登録できます。
- **コマンド機能**: 特定のキーワードを発話するとブラウザでURLを開く、ローカルファイルを起動するなどのアクションを実行できます。
- **入力補正(GPU版)**: 音声認識の聞き間違いや崩れた表記を、ローカルの LLM(gemma-4-E4B-it)で直してから入力します。直前の入力の話題も手がかりにします。よく使う言葉をよみがなと一緒に登録すると、補正の判断材料になります。LLM もパソコンの中で動くため、入力した文章は外部に送信されません。
- **入力履歴と取り消し**: 最近の入力を一覧で確認・コピーでき、直前の入力はショートカットキー一つで取り消せます。
- **CPU版 / GPU版の2エディション**: 使用するハードウェアに応じて選択可能。GPU版(NVIDIA)では高精度モデルも実用的な速度で動作します。

---

## 動作環境

### CPU版

- Windows 10 / 11 (64bit)

※ 参考: Ryzen 5 3600(2019年の 6コア)で、約 3秒の声の文字起こしに base で 0.8秒、small で 2.3秒かかります。medium と kotoba-whisper-v2.0 は実験的な選択肢で、同じ CPU で 6〜10秒かかります。

### GPU版

- Windows 10 / 11 (64bit)
- NVIDIA GeForce GTX 10シリーズ以降 (Compute Capability 6.0以上)
- NVIDIA GPUドライバ バージョン 560 以上
- 必要な VRAM: tiny・base で 0.5GB、small で 1GB、medium・kotoba-whisper-v2.0・large-v3-turbo で 2.5GB、large-v3 で 4.5GB
- 入力補正も使うときに必要な VRAM: small で 4.5GB、medium・kotoba-whisper-v2.0・large-v3-turbo で 6GB、large-v3 で 8GB
- 入力補正のモデル(gemma-4-E4B-it)は約 5.3GB あり、入力補正タブからダウンロードします

※ 必要な VRAM は、WhisperKey を単体で動かしたときの目安です。ほかのアプリ(ブラウザ、ゲーム、配信ソフトなど)も VRAM を使うため、一緒に使うアプリに合わせて余裕を見てください。

---

## 販売情報

本ソフトウェアの実行ファイル版(インストーラー形式)は BOOTH にて販売しています。

- **[BOOTH ショップページ]**: (https://asaimo-eos.booth.pm/)

- **[CPU版]**: (https://asaimo-eos.booth.pm/items/7284686)
    2,300円

- **[GPU版]**: (https://asaimo-eos.booth.pm/items/8256368)
    2,800円

購入者は BOOTH のマイライブラリから最新版を無償でダウンロードできます。

noteにて紹介記事を公開しています:
- **[note紹介記事]**: (https://note.com/lucky_minnow8803/n/ne6bed7272cff)

ソフトの概要・使い方を YouTube にて公開しています: 

- **[ソフトの概要・使い方(YouTube)]**: (https://youtu.be/xYWT7ytiTmY)

---

## 本リポジトリについて

本リポジトリは、WhisperKey の **ソースコードを透明性のために公開する目的** で運用しています。

- 実行ファイルの配布は BOOTH で行っています
- 本リポジトリは「コードに不審な処理が含まれていないかを確認するため」の用途を想定しています
- 自力でのビルド・動作は公式サポートの対象外です(ビルドスクリプトもリポジトリには含まれません)

---

## プロジェクト構成

```
WhisperKey/
├── src/
│   ├── app/                    # 本体(WhisperKey.exe)
│   │   ├── main.py             # エントリーポイント
│   │   ├── main_window.py      # 本体のウィンドウ(pywebview)と、画面から呼ばれる窓口
│   │   ├── audio.py            # 録音処理(別スレッド)
│   │   ├── transcribe.py       # Whisperによる文字起こし(別スレッド)
│   │   ├── model.py            # Whisperモデルのロード
│   │   ├── model_store.py      # モデルの置き場所とダウンロード(初回のみ)
│   │   ├── llm_correct.py      # 入力補正(GPU版。llama-server の起動・停止と、LLM による補正)
│   │   ├── llm_vocab.py        # 入力補正の「よく使う言葉」(llm_vocab.csv)
│   │   ├── key_shortcut.py     # グローバルホットキー管理(RegisterHotKey)
│   │   ├── paste.py            # 文字起こしの結果を貼り付ける
│   │   ├── undo_input.py       # 直前の入力を取り消す
│   │   ├── history.py          # 入力履歴
│   │   ├── sounds.py           # 効果音
│   │   ├── gui_indicator.py    # 録音中を示すインジケーター(浮かぶ操作パネル)
│   │   ├── startup_indicator.py# 起動中インジケーター
│   │   ├── tray_icon.py        # システムトレイ
│   │   ├── command.py          # 音声実行(command_dict.csv)
│   │   ├── convert_dict.py     # 音声辞書(convert_dict.csv)
│   │   ├── config.py           # 起動中の「今の設定」(変えた瞬間に効かせる)
│   │   ├── cleanup.py          # 一時ファイル削除
│   │   ├── cuda_check.py       # GPU版の起動時CUDAチェック
│   │   └── error_dialog.py     # エラーダイアログ
│   ├── ui/                     # 本体のウィンドウの画面(HTML / CSS / JS)
│   └── common/                 # 共通モジュール
│       ├── paths.py            # ファイルの場所の集約
│       ├── config_store.py     # 設定(config.json)の初期値・範囲・読み書き
│       ├── audio_devices.py    # マイクの一覧
│       └── edition.py          # CPU版 / GPU版の判定
├── assets/                     # アイコン・効果音等のリソース
├── package/                    # 配布フォルダに同梱するファイル(空の辞書・restart.bat)
└── licenses/                   # サードパーティライセンス
```

---

## 技術スタック

- **音声認識**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) / [CTranslate2](https://github.com/OpenNMT/CTranslate2)
- **モデル**: OpenAI Whisper (tiny / base / small / medium / large-v3 / large-v3-turbo)、[kotoba-whisper-v2.0](https://huggingface.co/kotoba-tech/kotoba-whisper-v2.0)(日本語専用)
- **入力補正(GPU版)**: [llama.cpp](https://github.com/ggml-org/llama.cpp) の llama-server / [gemma-4-E4B-it](https://huggingface.co/google/gemma-4-E4B-it)(Google、GGUF 形式の Q4_K_M)
- **オーディオ入力**: PyAudio
- **GUI**: pywebview(本体のウィンドウ。画面は HTML / CSS / JS) / Tkinter(インジケーター)
- **ショートカットキー**: Windows の RegisterHotKey
- **貼り付け**: keyboard ライブラリ
- **システムトレイ**: pystray
- **exe化**: PyInstaller
- **インストーラー**: Inno Setup

---

## ライセンス

### 実行ファイル版(BOOTHで販売)のライセンス

BOOTHで販売される実行ファイル版には、商用ソフトウェアとしての使用許諾契約が適用されます。詳細は同梱の `LICENSE.txt` および `THIRD_PARTY_LICENSES.txt` をご参照ください。

### 本リポジトリのソースコードのライセンス

本リポジトリで公開されているソースコードは、透明性の確認および LGPL-3.0 ライセンスのライブラリ(pystray)の要件を満たすために公開しています。ソースコードの商用利用・再配布・改変配布については、別途著作権者の許諾が必要です。

### サードパーティライブラリ

本ソフトウェアは多数のオープンソースライブラリを利用しています。詳細は同梱の `THIRD_PARTY_LICENSES.txt` をご参照ください。

GPU版は NVIDIA CUDA および cuDNN のランタイムライブラリを同梱しています。GPU版の使用者は NVIDIA のライセンス条項にも同意する必要があります。

GPU版は入力補正のために llama.cpp の llama-server(MIT License)を同梱しています。入力補正のモデル(gemma-4-E4B-it、Apache License 2.0)は同梱せず、使うときにダウンロードします。
