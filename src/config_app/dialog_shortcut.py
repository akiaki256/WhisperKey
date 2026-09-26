"""
ショートカットキー設定ダイアログ
仕様書§7.1
修飾キー + メインキーの2つのドロップダウンで構成
"""

import customtkinter as ctk

import constants as C


class ShortcutDialog(ctk.CTkToplevel):
    """
    ショートカットキー設定ダイアログ。
    
    使い方:
        dialog = ShortcutDialog(parent, current_key="f9")
        parent.wait_window(dialog)
        if dialog.result is not None:
            new_key = dialog.result  # 例: "f9", "ctrl+space"
    """
    
    def __init__(self, parent, current_key="f9", title="ショートカットキー設定"):
        super().__init__(parent)
        
        self.result = None
        
        self.title(title)
        self.geometry("360x200")
        self.resizable(False, False)
        
        self.transient(parent)
        self.grab_set()
        
        self._center_on_parent(parent)
        self._build_ui(current_key)
        
        self.bind("<Return>", lambda e: self._on_ok())
        self.bind("<Escape>", lambda e: self._on_cancel())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
    
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
    
    def _build_ui(self, current_key):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(fill="both", expand=True, padx=20, pady=15)
        frame.grid_columnconfigure(1, weight=1)
        
        # 修飾キー
        ctk.CTkLabel(frame, text="修飾キー:", anchor="w").grid(row=0, column=0, sticky="w", pady=8)
        self.combo_modifier = ctk.CTkComboBox(
            frame,
            values=C.MODIFIER_KEYS,
            state="readonly",
        )
        self.combo_modifier.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=8)
        
        # メインキー
        ctk.CTkLabel(frame, text="メインキー:", anchor="w").grid(row=1, column=0, sticky="w", pady=8)
        self.combo_main = ctk.CTkComboBox(
            frame,
            values=C.MAIN_KEYS,
            state="readonly",
        )
        self.combo_main.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=8)
        
        # 現在値を初期セット
        modifier, main = self._parse_key(current_key)
        self.combo_modifier.set(modifier)
        self.combo_main.set(main)
        
        # ボタンフレーム
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 15))
        
        ctk.CTkButton(btn_frame, text="キャンセル", width=100, command=self._on_cancel).pack(side="right", padx=(5, 0))
        ctk.CTkButton(btn_frame, text="OK", width=100, command=self._on_ok).pack(side="right")
    
    def _parse_key(self, key_str):
        """
        "f9" や "ctrl+space" を (修飾キー表示名, メインキー表示名) に分解。
        解釈不能なら ("なし", "F9") をデフォルトで返す。
        """
        if not key_str:
            return ("なし", "F9")
        
        key_str = key_str.strip().lower()
        parts = key_str.split("+")
        
        if len(parts) == 1:
            main_raw = parts[0]
            modifier_raw = None
        elif len(parts) == 2:
            modifier_raw, main_raw = parts[0], parts[1]
        else:
            return ("なし", "F9")
        
        # 修飾キーのマッピング
        modifier_map = {
            "ctrl": "Ctrl",
            "alt": "Alt",
            "shift": "Shift",
        }
        modifier_label = modifier_map.get(modifier_raw, "なし") if modifier_raw else "なし"
        
        # メインキーのマッピング
        main_label = self._main_key_to_label(main_raw)
        
        return (modifier_label, main_label)
    
    def _main_key_to_label(self, raw):
        """保存形式 → 表示ラベル への変換"""
        if not raw:
            return "F9"
        
        # F1〜F24
        if raw.startswith("f") and raw[1:].isdigit():
            num = int(raw[1:])
            if 1 <= num <= 24:
                return f"F{num}"
        
        # A〜Z
        if len(raw) == 1 and raw.isalpha():
            return raw.upper()
        
        # 0〜9
        if len(raw) == 1 and raw.isdigit():
            return raw
        
        # 特殊キー
        special_map = {
            "space": "Space",
            "enter": "Enter",
            "return": "Enter",
        }
        if raw in special_map:
            return special_map[raw]
        
        # 該当なし
        return "F9"
    
    def _build_save_string(self, modifier_label, main_label):
        """表示ラベル → 保存形式 への変換"""
        main_save = main_label.lower()  # "F9" → "f9", "Space" → "space"
        
        if modifier_label == "なし":
            return main_save
        
        modifier_save = modifier_label.lower()  # "Ctrl" → "ctrl"
        return f"{modifier_save}+{main_save}"
    
    def _on_ok(self):
        modifier = self.combo_modifier.get()
        main = self.combo_main.get()
        self.result = self._build_save_string(modifier, main)
        self.destroy()
    
    def _on_cancel(self):
        self.result = None
        self.destroy()
