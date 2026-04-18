"""
辞書変換タブ
仕様書§6.3
- Treeviewで2列表示(変換前 / 変換後)
- 追加 / 消去(選択時のみ有効)
- 行ダブルクリックで編集
"""

import customtkinter as ctk
from tkinter import ttk

import csv_io
from dialog_dict_edit import DictEditDialog


class DictTab(ctk.CTkFrame):
    """辞書変換タブ"""
    
    def __init__(self, parent, config=None):
        """
        Args:
            parent: 親ウィジェット
            config: (未使用、I/F統一のため受け取るが辞書はCSVから読む)
        """
        super().__init__(parent, fg_color="transparent")
        
        # CSV読込
        rows = csv_io.load_convert_dict()
        if rows is None:
            # 書式不正時はタブを無効化(テーブルは空、ボタンも無効)
            self._disabled = True
            self._initial_rows = []
        else:
            self._disabled = False
            self._initial_rows = rows
        
        self._build_ui()
    
    def _build_ui(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Treeview(CustomTkinterには無いのでttkを使用)
        tree_frame = ctk.CTkFrame(container, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True)
        
        # ttk.Style でCTkと近い見た目に調整
        style = ttk.Style()
        # CTkのデフォルトテーマに合わせた色調整(ダークモード考慮)
        self._apply_treeview_style(style)
        
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("before", "after"),
            show="headings",
            selectmode="browse",  # 単一選択
        )
        self.tree.heading("before", text="変換前")
        self.tree.heading("after", text="変換後")
        self.tree.column("before", width=200, anchor="w")
        self.tree.column("after", width=200, anchor="w")
        
        # スクロールバー
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        
        # 初期データ投入
        for row in self._initial_rows:
            self.tree.insert("", "end", values=(row["before"], row["after"]))
        
        # 選択変更で「消去」ボタンの有効/無効切り替え
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_change)
        # ダブルクリックで編集
        self.tree.bind("<Double-1>", self._on_double_click)
        
        # ボタン行
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(10, 0))
        
        self.btn_add = ctk.CTkButton(btn_row, text="追加", width=100, command=self._on_add)
        self.btn_add.pack(side="right", padx=(5, 0))
        
        self.btn_delete = ctk.CTkButton(btn_row, text="消去", width=100, command=self._on_delete, state="disabled")
        self.btn_delete.pack(side="right")
        
        # 書式不正時は全て無効化
        if self._disabled:
            self.btn_add.configure(state="disabled")
    
    def _apply_treeview_style(self, style):
        """CustomTkinterのテーマに合わせてTreeviewの見た目を調整"""
        try:
            mode = ctk.get_appearance_mode()
            if mode == "Dark":
                bg = "#2b2b2b"
                fg = "#dce4ee"
                field_bg = "#2b2b2b"
                sel_bg = "#1f6aa5"
                heading_bg = "#333333"
            else:
                bg = "#ebebeb"
                fg = "#000000"
                field_bg = "#ffffff"
                sel_bg = "#3a7ebf"
                heading_bg = "#d0d0d0"
            
            style.theme_use("default")
            style.configure(
                "Treeview",
                background=field_bg,
                foreground=fg,
                fieldbackground=field_bg,
                rowheight=26,
                borderwidth=0,
            )
            style.configure(
                "Treeview.Heading",
                background=heading_bg,
                foreground=fg,
                borderwidth=0,
            )
            style.map("Treeview", background=[("selected", sel_bg)])
        except Exception:
            # スタイル適用失敗は無視(デフォルト見た目で動く)
            pass
    
    # =====================================================
    # イベント
    # =====================================================
    
    def _on_selection_change(self, event=None):
        if self._disabled:
            return
        sel = self.tree.selection()
        self.btn_delete.configure(state="normal" if sel else "disabled")
    
    def _on_double_click(self, event=None):
        if self._disabled:
            return
        sel = self.tree.selection()
        if not sel:
            return
        self._edit_row(sel[0])
    
    def _on_add(self):
        dialog = DictEditDialog(self.winfo_toplevel(), before="", after="", title="辞書項目の追加")
        self.winfo_toplevel().wait_window(dialog)
        if dialog.result:
            self.tree.insert("", "end", values=(dialog.result["before"], dialog.result["after"]))
    
    def _on_delete(self):
        sel = self.tree.selection()
        if not sel:
            return
        for item in sel:
            self.tree.delete(item)
        self.btn_delete.configure(state="disabled")
    
    def _edit_row(self, item_id):
        current = self.tree.item(item_id, "values")
        before, after = current[0], current[1]
        
        dialog = DictEditDialog(self.winfo_toplevel(), before=before, after=after, title="辞書項目の編集")
        self.winfo_toplevel().wait_window(dialog)
        if dialog.result:
            self.tree.item(item_id, values=(dialog.result["before"], dialog.result["after"]))
    
    # =====================================================
    # 共通I/F
    # =====================================================
    
    def get_values(self):
        """
        Treeviewの全行を返す。
        
        Returns:
            list[dict]: [{"before": str, "after": str}, ...]
        """
        rows = []
        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            rows.append({"before": values[0], "after": values[1]})
        return rows
    
    def is_modified(self):
        """初期値から変更があればTrue"""
        if self._disabled:
            return False
        current = self.get_values()
        if len(current) != len(self._initial_rows):
            return True
        for c, i in zip(current, self._initial_rows):
            if c["before"] != i["before"] or c["after"] != i["after"]:
                return True
        return False
    
    def is_disabled(self):
        """書式不正で無効化されているか"""
        return self._disabled
