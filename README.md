# WhisperKey

音声をキー入力に変換する、Windows用のローカル音声入力ツール。

ショートカットキーで録音をオン/オフし、話した内容を自動で文字起こしして、現在フォーカスしているアプリケーションに貼り付けます。音声認識は OpenAI の Whisper モデルをローカル実行するため、インターネット接続不要で動作します。

---

## 特徴

- **完全ローカル動作**: 音声データは外部に送信されません。インターネット接続なしで動作します。
- **Windows 常駐型**: システムトレイに常駐し、ショートカットキー(初期設定 F9)で録音をオン/オフします。
- **辞書変換**: 頻出の誤認識や表記揺れをユーザー定義の辞書で補正できます。空文字への変換でハルシネーションのブロックも可能です。
- **コマンド機能**: 特定のキーワードを発話するとブラウザでURLを開く、ローカルファイルを起動するなどのアクションを実行できます。
- **CPU版 / GPU版の2エディション**: 使用するハードウェアに応じて選択可能。GPU版(NVIDIA)では高精度モデルも実用的な速度で動作します。

---

## 動作環境

### CPU版

- Windows 10 / 11 (64bit)

### GPU版

- Windows 10 / 11 (64bit)
- NVIDIA GeForce GTX 10シリーズ以降 (Compute Capability 6.0以上)
- NVIDIA GPUドライバ バージョン 560 以上
- VRAM: smallモデルで 2GB、mediumで 4GB、large-v3で 8GB 推奨

---

## 販売情報

本ソフトウェアの実行ファイル版(インストーラー形式)は BOOTH にて販売しています。

- **BOOTH ショップページ**: 

- **CPU版**: [(https://asaimo-eos.booth.pm/items/7284686)]
    2,300円

- **GPU版**: [https://asaimo-eos.booth.pm/items/8256368]
    2,800円


購入者は BOOTH のマイライブラリから最新版を無償でダウンロードできます。

ソフトの概要・使い方を YouTube にて公開しています:

- **ソフトの概要・使い方(YouTube)**: [(https://youtu.be/xYWT7ytiTmY)]

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
├── main.py              # エントリーポイント
├── audio.py             # 録音処理(別スレッド)
├── transcribe.py        # Whisperによる文字起こし(別スレッド)
├── model.py             # Whisperモデルのロード
├── key_shortcut.py      # グローバルホットキー管理
├── gui_indicator.py     # 録音中を示すインジケーター
├── startup_indicator.py # 起動中インジケーター
├── tray_icon.py         # システムトレイ
├── command.py           # コマンド実行機能
├── convert_dict.py      # 辞書変換機能
├── config.py            # 設定ファイル読込
├── cleanup.py           # 一時ファイル削除
├── cuda_check.py        # GPU版の起動時CUDAチェック
├── edition.py           # edition切り替えスイッチ
├── error_dialog.py      # エラーダイアログ
├── config.json          # ユーザー設定
├── WhisperKey_config/   # 設定GUIアプリ
├── items/               # アイコン等のリソース
└── restart.bat          # メイン再起動用
```

---

## 技術スタック

- **音声認識**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) / [CTranslate2](https://github.com/OpenNMT/CTranslate2)
- **モデル**: OpenAI Whisper (tiny / base / small / medium / large-v3)
- **オーディオ入力**: PyAudio
- **GUIフレームワーク**: Tkinter / CustomTkinter
- **キーボード入出力**: keyboard ライブラリ
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
