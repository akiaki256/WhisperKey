"""
CPU版 / GPU版 の識別定数(中継ファイル)

このファイルの import 文を書き換えることで、ビルド対象のバージョンを切り替える。
- CPU版をビルドしたい時: from edition_cpu import EDITION
- GPU版をビルドしたい時: from edition_gpu import EDITION

この1行が「このプロジェクトがどちらのバージョンか」の真実のソース。
他のソースコードは常に `from edition import EDITION` とすればよい。
"""

from edition_gpu import EDITION
