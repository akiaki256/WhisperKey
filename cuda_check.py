"""
GPU版の起動時CUDAチェック
仕様:
- NVIDIA GPUが認識されていて、CUDA DLLがロードでき、ドライバが対応バージョンかを確認
- 失敗時はWindows標準のMessageBoxでエラー表示して終了
- GPU版でのみ呼び出す(CPU版では呼ばない)
"""

import sys
import ctypes


def _show_error(title, message):
    """Windows標準MessageBoxでエラー表示"""
    try:
        # MB_OK (0x00) + MB_ICONERROR (0x10) = 0x10
        ctypes.windll.user32.MessageBoxW(0, message, title, 0x10)
    except Exception as e:
        print(f"{title}: {message}")
        print(f"(MessageBox表示失敗: {e})")


def ensure_cuda_available():
    """
    GPU版起動時に呼び出す。
    CUDA環境に問題があれば、エラーメッセージを表示して sys.exit(1) する。
    正常ならそのまま戻る。
    """
    try:
        import ctranslate2
    except ImportError as e:
        _show_error(
            "起動エラー",
            f"必要なライブラリの読み込みに失敗しました。\n\n"
            f"詳細: {e}\n\n"
            f"インストールが壊れている可能性があります。\n"
            f"再インストールをお試しください。"
        )
        sys.exit(1)
    
    try:
        cuda_count = ctranslate2.get_cuda_device_count()
    except Exception as e:
        # DLL読込失敗などの致命的なエラー
        _show_error(
            "CUDA初期化エラー",
            f"CUDAの初期化に失敗しました。\n\n"
            f"以下をご確認ください:\n"
            f"・NVIDIAのGPUドライバが最新版にアップデートされているか\n"
            f"  (バージョン560以上推奨)\n"
            f"・Windowsを再起動したか\n\n"
            f"詳細: {e}"
        )
        sys.exit(1)
    
    if cuda_count <= 0:
        # GPUが見つからない or 使用不可
        _show_error(
            "GPU未検出",
            "NVIDIA製GPUが検出されませんでした。\n\n"
            "以下をご確認ください:\n"
            "・NVIDIA製のグラフィックボードが搭載されているか\n"
            "・NVIDIAのGPUドライバがインストールされているか\n"
            "・ドライバが最新版にアップデートされているか\n"
            "  (バージョン560以上推奨)\n\n"
            "GPUを搭載していない場合は、CPU版をご利用ください。"
        )
        sys.exit(1)
    
    # 正常: GPU認識OK
    print(f"CUDA check: OK (detected {cuda_count} GPU(s))")
