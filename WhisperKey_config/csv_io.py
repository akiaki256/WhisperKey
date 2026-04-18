"""
CSVファイルの読み書き
- convert_dict.csv: 辞書変換
- command_dict.csv: コマンド
仕様書§4.3、§8.2
"""

import csv
import os
from CTkMessagebox import CTkMessagebox

import constants as C


# =====================================================
# 辞書変換CSV
# =====================================================

def load_convert_dict():
    """
    convert_dict.csv を読み込む。
    
    Returns:
        list[dict]: [{"before": str, "after": str}, ...]
        ファイル不在時は空リスト。書式不正時はNone(呼び出し側でエラー処理)
    """
    if not os.path.exists(C.CONVERT_DICT_PATH):
        return []
    
    try:
        with open(C.CONVERT_DICT_PATH, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            # ヘッダチェック
            if reader.fieldnames is None or "before" not in reader.fieldnames or "after" not in reader.fieldnames:
                CTkMessagebox(
                    title="設定ファイルエラー",
                    message="convert_dict.csvの書式が不正です。\n該当タブの機能は無効化されます。",
                    icon="warning",
                    option_1="OK",
                )
                return None
            
            rows = []
            for row in reader:
                before = row.get("before") or ""
                after = row.get("after") or ""
                # 両方空文字の行はスキップ(空白のみは保持)
                if before == "" and after == "":
                    continue
                rows.append({"before": before, "after": after})
            return rows
    except Exception as e:
        CTkMessagebox(
            title="設定ファイルエラー",
            message=f"convert_dict.csvの読み込みに失敗しました。\n{e}",
            icon="warning",
            option_1="OK",
        )
        return None


def save_convert_dict(rows):
    """
    convert_dict.csv に書き込む。
    
    Args:
        rows: list[dict] [{"before": str, "after": str}, ...]
    """
    with open(C.CONVERT_DICT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["before", "after"])
        writer.writeheader()
        for row in rows:
            writer.writerow({"before": row["before"], "after": row["after"]})


# =====================================================
# コマンドCSV
# =====================================================

def load_command_dict():
    """
    command_dict.csv を読み込む。
    
    Returns:
        list[dict]: [{"keyword": str, "tag": str, "path": str}, ...]
        ファイル不在時は空リスト。書式不正時はNone
    """
    if not os.path.exists(C.COMMAND_DICT_PATH):
        return []
    
    try:
        with open(C.COMMAND_DICT_PATH, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            required = {"keyword", "tag", "path"}
            if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
                CTkMessagebox(
                    title="設定ファイルエラー",
                    message="command_dict.csvの書式が不正です。\n該当タブの機能は無効化されます。",
                    icon="warning",
                    option_1="OK",
                )
                return None
            
            rows = []
            for row in reader:
                keyword = row.get("keyword") or ""
                tag = (row.get("tag") or "").strip()  # tagは "url"/"file" の固定値なのでstripしておく
                path = row.get("path") or ""
                # 全部空文字の行はスキップ
                if keyword == "" and tag == "" and path == "":
                    continue
                # 不明なtagは "url" にフォールバック(保守的に動かす)
                if tag not in ("url", "file"):
                    tag = "url"
                rows.append({"keyword": keyword, "tag": tag, "path": path})
            return rows
    except Exception as e:
        CTkMessagebox(
            title="設定ファイルエラー",
            message=f"command_dict.csvの読み込みに失敗しました。\n{e}",
            icon="warning",
            option_1="OK",
        )
        return None


def save_command_dict(rows):
    """
    command_dict.csv に書き込む。
    
    Args:
        rows: list[dict] [{"keyword": str, "tag": str, "path": str}, ...]
    """
    with open(C.COMMAND_DICT_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["keyword", "tag", "path"])
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "keyword": row["keyword"],
                "tag": row["tag"],
                "path": row["path"],
            })
