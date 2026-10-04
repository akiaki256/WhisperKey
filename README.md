# WhisperKey

音声をキー入力に変換する、Windows用のローカル音声入力ツール。

ショートカットキーで録音をオン/オフし、話した内容を自動で文字起こしして、現在フォーカスしているアプリケーションに貼り付けます。音声認識は OpenAI の Whisper モデルをローカル実行します。GPU版では、聞き間違いをローカルの LLM で直してから入力することもできます。インターネット接続が必要なのは、初めて使うときのモデルのダウンロードだけで、そのあとはオフラインで動作します。

**日本語専用です**(v5.0.0 から。入力補正などの仕組みが日本語を前提にしているため、ほかの言語の認識には対応していません)。

---

## 特徴

- **通信は最小限**: インターネットにつなぐのは、音声認識や入力補正のモデルをダウンロードするとき(ダウンロードのボタンを押したとき)だけです。文字起こしも入力補正もすべてパソコンの中で行い、声や入力した文章を外部に送ることはありません。モデルをダウンロードしたあとは、インターネットにつながっていなくても使えます。
- **Windows 常駐型**: システムトレイに常駐し、ショートカットキー(初期設定 F9)で録音をオン/オフします。キーを押している間だけ録音するプッシュトゥトークにも切り替えられます。
- **辞書変換**: 頻出の誤認識や表記揺れをユーザー定義の辞書で補正できます。空文字への変換でハルシネーションのブロックも可能です。入力履歴でなぞった言葉を、そのまま辞書に登録できます。
- **コマンド機能**: 特定のキーワードを発話するとブラウザでURLを開く、ローカルファイルを起動するなどのアクションを実行できます。
- **入力補正(GPU版)**: 音声認識の聞き間違いや崩れた表記を、ローカルの LLM(gemma-4-E4B-it)で直してから入力します。直前の入力の話題も手がかりにします。LLM もパソコンの中で動くため、入力した文章は外部に送信されません。
    - **同音異義語の確かめ**: 「仕様 / 使用」「分 / 文」のように、それだけ見ると正しい言葉になる取り違えや聞き間違いを、候補の言葉を並べて LLM に選ばせることで直します。
    - **よく使う言葉**: 言葉と読み(カタカナ)を登録すると、補正の手がかりになります。
    - **候補を出す(初期設定 F8)**: 直前の入力のほかの候補を、IME の変換候補のように窓に並べます。選ぶと、入力した文章がその候補に入れ替わります。
    - **言い淀みを消す**: 「洗、洗濯物」の「洗、」のような言いかけの切れ端を消します(初期設定はオフ)。
    - **句読点補正**: 音声認識が付けた「、」「。」をいったん外して、LLM が付け直します。付いたり付かなかったりするのを防ぎます(初期設定はオフ)。
- **「。」「、」を消す**: 入力する文章の「。」や「、」を消せます。チャットなど、句読点を付けない場面向けです。
- **入力履歴と取り消し**: 最近の入力を一覧で確認・コピーでき、直前の入力はショートカットキー一つで取り消せます。
- **CPU版 / GPU版の2エディション**: 使用するハードウェアに応じて選択可能。GPU版(NVIDIA)では高精度モデルも実用的な速度で動作します。

---

## 動作環境

### CPU版

- Windows 10 / 11 (64bit)

※ 参考: Ryzen 5 3600(2019年の 6コア)で、約 3秒の声の文字起こしに base で 0.8秒、small で 2.3秒かかります。medium と kotoba-whisper-v2.0 は実験的な選択肢で、同じ CPU で 6〜10秒かかります。

※ 参考: Core i7-6700HQ(2015年の 4コアのノートパソコン)では、話し終わってから文字が出るまでに、tiny・base で約 2秒、small で約 5秒、medium で約 12秒、kotoba-whisper-v2.0 で約 19秒かかります。古いパソコンでは tiny か base がおすすめです。

### GPU版

- Windows 10 / 11 (64bit)
- NVIDIA GeForce GTX 10シリーズ以降 (Compute Capability 6.0以上)
- NVIDIA GPUドライバ バージョン 560 以上
- 必要な VRAM: tiny・base で 0.5GB、small で 1GB、medium・kotoba-whisper-v2.0・large-v3-turbo で 2.5GB、large-v3 で 4.5GB
- 入力補正も使うときに必要な VRAM: small で 4.5GB、medium・kotoba-whisper-v2.0・large-v3-turbo で 6GB、large-v3 で 8GB
- 入力補正のモデル(gemma-4-E4B-it)は約 5.3GB あり、入力補正タブからダウンロードします

※ 必要な VRAM は、WhisperKey を単体で動かしたときの目安です。ほかのアプリ(ブラウザ、ゲーム、配信ソフトなど)も VRAM を使うため、一緒に使うアプリに合わせて余裕を見てください。

※ VRAM が足りないときも止まらずに動きますが、入りきらない分をメインメモリで補うため、とても遅くなります。たとえば GeForce GTX 1650 Ti(VRAM 4GB)では、話し終わってから文字が出るまでに、medium で約 4秒、入力補正をオンにすると約 10秒かかります。VRAM 4GB 程度の GPU では、入力補正はオフで使うのがおすすめです。

※ 参考: GeForce RTX 5060 Ti(VRAM 16GB)では、どのモデルでも入力補正なしで約 1秒、入力補正ありで約 2秒です(話し終わってから無音と判断するまでの 0.8秒を含みます)。

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
│   │   ├── llm_correct.py      # 入力補正(GPU版。llama-server の起動・停止と、補正の順番)
│   │   ├── llm_vocab.py        # 入力補正の「よく使う言葉」(llm_vocab.csv)
│   │   ├── homophone.py        # 入力補正の「同音異義語の確かめ」(MeCab と IPA 辞書などで候補を出し、LLM に選ばせる)
│   │   ├── vocab_match.py      # 読みの近さを測る部品(よく使う言葉を探す・音声認識に渡すヒントを選ぶ)
│   │   ├── punctuate.py        # 入力補正の「句読点補正」
│   │   ├── candidates.py       # 「候補を出す」の候補の並びと入れ替え
│   │   ├── candidate_window.py # 「候補を出す」の窓
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
│   │   ├── autostart.py        # Windows の起動時に立ち上げる(スタートアップの登録)
│   │   ├── cleanup.py          # 一時ファイル削除
│   │   ├── cuda_check.py       # GPU版の起動時CUDAチェック
│   │   └── error_dialog.py     # エラーダイアログ
│   ├── ui/                     # 本体のウィンドウの画面(HTML / CSS / JS)
│   └── common/                 # 共通モジュール
│       ├── paths.py            # ファイルの場所の集約
│       ├── config_store.py     # 設定(config.json)の初期値・範囲・読み書き
│       ├── audio_devices.py    # マイクの一覧
│       ├── edition.py          # CPU版 / GPU版の判定
│       └── version.py          # 版の番号
├── assets/                     # アイコン・効果音等のリソース
├── package/                    # 配布フォルダに同梱するファイル(空の辞書・restart.bat)
└── licenses/                   # サードパーティライセンス
```

---

## 技術スタック

- **音声認識**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) / [CTranslate2](https://github.com/OpenNMT/CTranslate2)
- **モデル**: OpenAI Whisper (tiny / base / small / medium / large-v3 / large-v3-turbo)、[kotoba-whisper-v2.0](https://huggingface.co/kotoba-tech/kotoba-whisper-v2.0)(日本語専用)
- **入力補正(GPU版)**: [llama.cpp](https://github.com/ggml-org/llama.cpp) の llama-server / [gemma-4-E4B-it](https://huggingface.co/google/gemma-4-E4B-it)(Google、GGUF 形式の Q4_K_M)
- **同音異義語の確かめ(GPU版)**: [MeCab](https://taku910.github.io/mecab/)([fugashi](https://github.com/polm/fugashi))/ IPA 辞書
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

GPU版は同音異義語の確かめのために、MeCab(BSD License で利用)と IPA 辞書を同梱しています。
