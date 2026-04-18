"""
辞書追加・編集ダイアログ
仕様書§7.2
"""

import customtkinter as ctk
from CTkMessagebox import CTkMessagebox


class DictEditDialog(ctk.CTkToplevel):
    """
    辞書項目の追加・編集ダイアログ。
    
    使い方:
        dialog = DictEditDialog(parent, before="", after="")
        parent.wait_window(dialog)
        if dialog.result is not None:
            before, after = dialog.result["before"], dialog.result["after"]
    """
    
    def __init__(self, parent, before="", after="", title="辞書項目の編集"):
        super().__init__(parent)
        
        self.result = None  # None=キャンセル、dict=OK
        
        # ウィンドウ設定
        self.title(title)
        self.geometry("360x180")
        self.resizable(False, False)
        
        # モーダル化
        self.transient(parent)
        self.grab_set()
        
        # 親ウィンドウ中央に配置
        self._center_on_parent(parent)
        
        # UI構築
        self._build_ui(before, after)
        
        # Enterで OK、Escで キャンセル
        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())
        
        # 閉じるボタンをキャンセル扱いに
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        
        # 最初の入力欄にフォーカス
        self.entry_before.focus_set()
    
    def _center_on_parent(self, parent):
        """親ウィンドウの中央に配置"""
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
    
    def _build_ui(self, before, after):
        # 入力フレーム
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=15)
        
        # 変換前
        ctk.CTkLabel(frame, text="変換前:", anchor="w").grid(row=0, column=0, sticky="w", pady=5)
        self.entry_before = ctk.CTkEntry(frame, width=240)
        self.entry_before.grid(row=0, column=1, padx=(10, 0), pady=5)
        self.entry_before.insert(0, before)
        
        # 変換後
        ctk.CTkLabel(frame, text="変換後:", anchor="w").grid(row=1, column=0, sticky="w", pady=5)
        self.entry_after = ctk.CTkEntry(frame, width=240)
        self.entry_after.grid(row=1, column=1, padx=(10, 0), pady=5)
        self.entry_after.insert(0, after)
        
        # ボタンフレーム
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        # キャンセル | OK の順(Windows準拠)
        ctk.CTkButton(btn_frame, text="キャンセル", width=100, command=self._on_cancel).pack(side="right", padx=(5, 0))
        ctk.CTkButton(btn_frame, text="OK", width=100, command=self._on_ok).pack(side="right")
    
    def _on_ok(self):
        # 生の値(空白保持のためstrip()しない)
        before = self.entry_before.get()
        after = self.entry_after.get()
        
        # バリデーション:
        # - 変換前: 空白のみもエラー(Whisperは空白のみを出力しないので検知不可能)
        # - 変換後: 純粋な空文字のみエラー(空白だけに置換したいケースを許可)
        if not before.strip() or after == "":
            CTkMessagebox(
                master=self,
                title="入力エラー",
                message="変換前・変換後の両方を入力してください。\n(変換前は空白のみの入力はできません)",
                icon="warning",
                option_1="OK",
            )
            return
        
        self.result = {"before": before, "after": after}
        self.destroy()
    
    def _on_cancel(self):
        self.result = None
        self.destroy()
