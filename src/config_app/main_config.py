"""
WhisperKey設定GUI エントリポイント
仕様書§5, §7.4, §8, §9
"""

import sys
import os

# src/common を import できるようにする(exe化後は PyInstaller の --paths で同梱済み)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "common"))

import subprocess
import customtkinter as ctk
from CTkMessagebox import CTkMessagebox

import constants as C
import config_io
import csv_io
import single_instance
from edition import EDITION
from tab_basic import BasicTab
from tab_speech import SpeechTab
from tab_dict import DictTab
from tab_command import CommandTab


class ConfigApp(ctk.CTk):
    """設定GUIのメインウィンドウ"""
    
    def __init__(self, config):
        super().__init__()
        
        self.config_data = config
        
        # -------- ウィンドウ設定 --------
        edition_label = C.EDITION_LABELS.get(EDITION, C.EDITION_LABEL_UNKNOWN)
        self.title(f"{C.WINDOW_TITLE_BASE} {edition_label}")
        
        self.geometry(f"{C.WINDOW_WIDTH}x{C.WINDOW_HEIGHT}")
        self.resizable(False, False)
        
        # 最小化・最大化を無効化(×のみ)
        try:
            self.attributes("-toolwindow", False)  # ツールウィンドウ化はしない
        except Exception:
            pass
        
        # ×ボタンはキャンセル扱い
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        
        # -------- タブ群 --------
        self._build_tabs()
        
        # -------- 保存/キャンセルボタン --------
        self._build_bottom_buttons()
    
    def _build_tabs(self):
        # CTkTabviewを使用
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        
        # タブを追加
        self.tabview.add("基本設定")
        self.tabview.add("音声認識")
        self.tabview.add("辞書変換")
        self.tabview.add("コマンド")
        
        # 各タブの中身
        self.tab_basic = BasicTab(self.tabview.tab("基本設定"), self.config_data)
        self.tab_basic.pack(fill="both", expand=True)
        
        self.tab_speech = SpeechTab(self.tabview.tab("音声認識"), self.config_data)
        self.tab_speech.pack(fill="both", expand=True)
        
        self.tab_dict = DictTab(self.tabview.tab("辞書変換"), self.config_data)
        self.tab_dict.pack(fill="both", expand=True)
        
        self.tab_command = CommandTab(self.tabview.tab("コマンド"), self.config_data)
        self.tab_command.pack(fill="both", expand=True)
    
    def _build_bottom_buttons(self):
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(5, 10))
        
        # キャンセル | 保存(Windows準拠)
        # 保存: エメラルドグリーン / キャンセル: 赤
        ctk.CTkButton(
            btn_row,
            text="保存",
            width=100,
            fg_color="#10b981",
            hover_color="#059669",
            command=self._on_save,
        ).pack(side="right", padx=(5, 0))
        
        ctk.CTkButton(
            btn_row,
            text="キャンセル",
            width=100,
            fg_color="#ef4444",
            hover_color="#dc2626",
            command=self._on_cancel,
        ).pack(side="right")
    
    # =====================================================
    # 未保存判定
    # =====================================================
    
    def _is_modified(self):
        """いずれかのタブで変更があればTrue"""
        return (
            self.tab_basic.is_modified()
            or self.tab_speech.is_modified()
            or self.tab_dict.is_modified()
            or self.tab_command.is_modified()
        )
    
    # =====================================================
    # キャンセル処理(§7.4)
    # =====================================================
    
    def _on_cancel(self):
        """キャンセルボタン・×ボタン押下時"""
        if not self._is_modified():
            self.destroy()
            return
        
        # 未保存の変更あり → 確認ダイアログ(3択)
        box = CTkMessagebox(
            master=self,
            title="確認",
            message="保存されていない変更があります。\n保存しますか?",
            icon="question",
            option_1="キャンセル",
            option_2="破棄",
            option_3="保存",
        )
        answer = box.get()
        
        if answer == "保存":
            self._on_save()
        elif answer == "破棄":
            self.destroy()
        else:
            # キャンセル → 何もしない(ダイアログを閉じて設定画面に戻る)
            return
    
    # =====================================================
    # 保存処理(§8.3, §9)
    # =====================================================
    
    def _on_save(self):
        """保存ボタン押下時のフロー"""
        # 変更なしならGUIを閉じるだけ(再起動しない)
        if not self._is_modified():
            self.destroy()
            return
        
        # 1. 全タブの入力値を集約
        basic_values = self.tab_basic.get_values()
        speech_values = self.tab_speech.get_values()
        dict_rows = self.tab_dict.get_values()
        command_rows = self.tab_command.get_values()
        
        # 2. 重複チェック
        dup_before = self._find_duplicate_key(dict_rows, "before")
        if dup_before:
            CTkMessagebox(
                master=self,
                title="入力エラー",
                message=f"変換前の語『{dup_before}』が重複しています。\n修正してください。",
                icon="cancel",
                option_1="OK",
            )
            self.tabview.set("辞書変換")
            return
        
        dup_keyword = self._find_duplicate_key(command_rows, "keyword")
        if dup_keyword:
            CTkMessagebox(
                master=self,
                title="入力エラー",
                message=f"キーワード『{dup_keyword}』が重複しています。\n修正してください。",
                icon="cancel",
                option_1="OK",
            )
            self.tabview.set("コマンド")
            return
        
        # 3. config.json 用のdictを構築(editionは書き込まない)
        # 設定画面に無い項目(インジケーターの位置など)を消さないよう、今のファイルの上に重ねる
        new_config = {
            **config_io.load_config(),
            "volume_threshold": basic_values["volume_threshold"],
            "silence_duration": basic_values["silence_duration"],
            "audio_device_index": basic_values["audio_device_index"],
            "audio_device_name": basic_values["audio_device_name"],
            "audio_device_sample_rate": basic_values["audio_device_sample_rate"],
            "shortcut_key": basic_values["shortcut_key"],
            "language": speech_values["language"],
            "model_size": speech_values["model_size"],
        }
        
        # 4. ファイル書き込み
        try:
            config_io.save_config(new_config)
        except Exception as e:
            CTkMessagebox(
                master=self,
                title="保存エラー",
                message=f"config.jsonの保存に失敗しました:\n{e}",
                icon="cancel",
                option_1="OK",
            )
            return
        
        # 5. CSV書き込み(書式不正で無効化されていなければ)
        if not self.tab_dict.is_disabled():
            try:
                csv_io.save_convert_dict(dict_rows)
            except Exception as e:
                CTkMessagebox(
                    master=self,
                    title="保存エラー",
                    message=f"convert_dict.csvの保存に失敗しました:\n{e}",
                    icon="cancel",
                    option_1="OK",
                )
                return
        
        if not self.tab_command.is_disabled():
            try:
                csv_io.save_command_dict(command_rows)
            except Exception as e:
                CTkMessagebox(
                    master=self,
                    title="保存エラー",
                    message=f"command_dict.csvの保存に失敗しました:\n{e}",
                    icon="cancel",
                    option_1="OK",
                )
                return
        
        # 6. restart.bat を起動
        self._restart_main_process()
        
        # 7. 自プロセスを終了
        self.destroy()
    
    def _find_duplicate_key(self, rows, key):
        """listの中で同じkeyの値が重複していれば、その値を返す。なければNone"""
        seen = set()
        for row in rows:
            v = row.get(key)
            if v in seen:
                return v
            seen.add(v)
        return None
    
    def _restart_main_process(self):
        """restart.bat を非表示で起動"""
        if not getattr(sys, "frozen", False):
            # 開発中の本体は python で動いているため、restart.bat(WhisperKey.exe を再起動する)は使えない
            CTkMessagebox(
                master=self,
                title="保存しました",
                message="設定を保存しました。\n開発中は自動で再起動しないため、本体を手動で再起動してください。",
                icon="info",
                option_1="OK",
            )
            return

        if not os.path.exists(C.RESTART_BAT_PATH):
            CTkMessagebox(
                master=self,
                title="再起動エラー",
                message="restart.batが見つかりません。\nメインプロセスを手動で再起動してください。",
                icon="warning",
                option_1="OK",
            )
            return
        
        try:
            subprocess.Popen(
                [C.RESTART_BAT_PATH],
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=True,
                shell=False,
            )
        except Exception as e:
            CTkMessagebox(
                master=self,
                title="再起動エラー",
                message=f"メインプロセスの再起動に失敗しました:\n{e}\n\n手動で起動してください。",
                icon="warning",
                option_1="OK",
            )


# =====================================================
# エントリポイント
# =====================================================

def main():
    # 1. 多重起動チェック(最優先)
    single_instance.ensure_single_instance()
    
    # 2. CustomTkinterテーマ設定(好みに応じて)
    ctk.set_appearance_mode("system")  # "light" / "dark" / "system"
    ctk.set_default_color_theme("blue")
    
    # 3. config.json 読込
    config = config_io.load_config()
    
    # 4. アプリ起動
    app = ConfigApp(config)
    app.mainloop()


if __name__ == "__main__":
    main()
