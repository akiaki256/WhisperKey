"""
コマンド追加・編集ダイアログ
仕様書§7.3
種類ドロップダウンによりパス欄のラベルと「参照」ボタンが動的に変化する。
"""

import customtkinter as ctk
from tkinter import filedialog
from CTkMessagebox import CTkMessagebox

import constants as C


class CommandEditDialog(ctk.CTkToplevel):
    """
    コマンドの追加・編集ダイアログ。
    
    使い方:
        dialog = CommandEditDialog(parent, keyword="", tag="url", path="")
        parent.wait_window(dialog)
        if dialog.result is not None:
            kw = dialog.result["keyword"]
            tag = dialog.result["tag"]
            path = dialog.result["path"]
    """
    
    def __init__(self, parent, keyword="", tag="url", path="", title="コマンドの編集"):
        super().__init__(parent)
        
        self.result = None
        
        # ウィンドウ設定
        self.title(title)
        self.geometry("440x220")
        self.resizable(False, False)
        
        # モーダル化
        self.transient(parent)
        self.grab_set()
        
        self._center_on_parent(parent)
        self._build_ui(keyword, tag, path)
        
        # 種類に応じて初期表示を切り替え
        self._update_path_row()
        
        # キーバインド
        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        
        self.entry_keyword.focus_set()
    
    def _center_on_parent(self, parent):
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        sw = self.winfo_width()
        sh = self.winfo_height()
        x = px + (pw - sw) // 2
        y = py + (ph - sh) // 2
        self.geometry(f"+{x}+{y}")
    
    def _build_ui(self, keyword, tag, path):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=15)
        frame.grid_columnconfigure(1, weight=1)
        
        # キーワード
        ctk.CTkLabel(frame, text="キーワード:", anchor="w").grid(row=0, column=0, sticky="w", pady=5)
        self.entry_keyword = ctk.CTkEntry(frame)
        self.entry_keyword.grid(row=0, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=5)
        self.entry_keyword.insert(0, keyword)
        
        # 種類
        ctk.CTkLabel(frame, text="種類:", anchor="w").grid(row=1, column=0, sticky="w", pady=5)
        type_labels = [label for _, label in C.COMMAND_TYPES]
        self.combo_type = ctk.CTkComboBox(
            frame,
            values=type_labels,
            state="readonly",
            command=lambda _: self._update_path_row(),
        )
        self.combo_type.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(10, 0), pady=5)
        # 初期値を設定
        initial_label = C.COMMAND_TAG_TO_LABEL.get(tag, type_labels[0])
        self.combo_type.set(initial_label)
        
        # パス欄(ラベルは _update_path_row で切り替え)
        self.label_path = ctk.CTkLabel(frame, text="URL:", anchor="w")
        self.label_path.grid(row=2, column=0, sticky="w", pady=5)
        
        self.entry_path = ctk.CTkEntry(frame)
        self.entry_path.grid(row=2, column=1, sticky="ew", padx=(10, 5), pady=5)
        self.entry_path.insert(0, path)
        
        self.btn_browse = ctk.CTkButton(frame, text="参照", width=60, command=self._on_browse)
        self.btn_browse.grid(row=2, column=2, pady=5)
        
        # ボタンフレーム
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        ctk.CTkButton(btn_frame, text="キャンセル", width=100, command=self._on_cancel).pack(side="right", padx=(5, 0))
        ctk.CTkButton(btn_frame, text="OK", width=100, command=self._on_ok).pack(side="right")
    
    def _get_current_tag(self):
        """ドロップダウンの現在値から tag を得る"""
        label = self.combo_type.get()
        return C.COMMAND_LABEL_TO_TAG.get(label, "url")
    
    def _update_path_row(self):
        """種類に応じてパス欄のラベルと参照ボタンの表示を切り替え"""
        tag = self._get_current_tag()
        if tag == "url":
            self.label_path.configure(text="URL:")
            # 参照ボタンを非表示
            self.btn_browse.grid_remove()
            # パス欄を全幅に伸ばす
            self.entry_path.grid_configure(columnspan=2, padx=(10, 0))
        else:  # file
            self.label_path.configure(text="ファイル:")
            # 参照ボタンを表示
            self.btn_browse.grid()
            # パス欄を元の幅に戻す
            self.entry_path.grid_configure(columnspan=1, padx=(10, 5))
    
    def _on_browse(self):
        """ファイル選択ダイアログを開く"""
        path = filedialog.askopenfilename(
            parent=self,
            title="ファイルを選択",
        )
        if path:
            self.entry_path.delete(0, "end")
            self.entry_path.insert(0, path)
    
    def _on_ok(self):
        # 生の値(空白保持のためstrip()しない)
        keyword = self.entry_keyword.get()
        path = self.entry_path.get()
        tag = self._get_current_tag()
        
        # バリデーション: キーワードもパスも空白のみはエラー
        if not keyword.strip() or not path.strip():
            CTkMessagebox(
                master=self,
                title="入力エラー",
                message="キーワードとアクションを入力してください。",
                icon="warning",
                option_1="OK",
            )
            return
        
        self.result = {"keyword": keyword, "tag": tag, "path": path}
        self.destroy()
    
    def _on_cancel(self):
        self.result = None
        self.destroy()
