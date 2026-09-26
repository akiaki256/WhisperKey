"""
edition(cpu / gpu)の判定
- ビルド時: build.bat が生成する _edition_build.py を読む(Git管理外、ビルド後に削除)
- 開発中: 環境変数 WHISPERKEY_EDITION を読む(未設定なら gpu)
"""

import os

try:
    from _edition_build import EDITION
except ImportError:
    EDITION = os.environ.get("WHISPERKEY_EDITION", "gpu")
