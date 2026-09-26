"""
コマンドタブ
仕様書§6.4
- Treeviewで3列表示(キーワード / 種類 / アクション)
- 種類は内部tagを「URLを開く/ファイルを開く」に表示整形
- 追加 / 消去(選択時のみ有効)
- 行ダブルクリックで編集
- 下部に説明文
"""

import customtkinter as ctk
from tkinter import ttk

import constants as C
import csv_io
from dialog_command_edit import CommandEditDialog


class CommandTab(ctk.CTkFrame):
    """コマンドタブ"""
    
    def __init__(self, parent, config=None):
        super().__init__(parent, fg_color="transparent")
        
        rows = csv_io.load_command_dict()
        if rows is None:
            self._disabled = True
            self._initial_rows = []
        else:
            self._disabled = False
            self._initial_rows = rows
        
        self._build_ui()
    
    def _build_ui(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=15, pady=15)
        
        # Treeview
        tree_frame = ctk.CTkFrame(container, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True)
        
        style = ttk.Style()
        self._apply_treeview_style(style)
        
        self.tree = ttk.Treeview(
            tree_frame,
            columns=("keyword", "type", "action"),
            show="headings",
            selectmode="browse",
        )
        self.tree.heading("keyword", text="キーワード")
        self.tree.heading("type", text="種類")
        self.tree.heading("action", text="アクション")
        self.tree.column("keyword", width=110, anchor="w")
        self.tree.column("type", width=100, anchor="w")
        self.tree.column("action", width=220, anchor="w")
        
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        
        # 初期データ投入
        # Treeviewに表示するのは「表示用ラベル」だが、内部では tag も管理する必要がある。
        # tag の実値は Treeview の item() のタグ機能ではなく、別dict(self._row_tags)で管理する。
        # (Treeviewの組み込みタグ機能は別用途なので混ぜると分かりにくい)
        self._row_tags = {}  # item_id -> tag ("url" or "file")
        
        for row in self._initial_rows:
            self._insert_row(row["keyword"], row["tag"], row["path"])
        
        self.tree.bind("<<TreeviewSelect>>", self._on_selection_change)
        self.tree.bind("<Double-1>", self._on_double_click)
        
        # 説明文(ボタンの上)
        ctk.CTkLabel(
            container,
            text="音声入力中、キーワードが検知された時、\n設定されたアクションを実行します",
            text_color="gray",
            justify="left",
            anchor="w",
        ).pack(fill="x", pady=(15, 0))
        
        # ボタン行
        btn_row = ctk.CTkFrame(container, fg_color="transparent")
        btn_row.pack(fill="x", pady=(10, 0))
        
        self.btn_add = ctk.CTkButton(btn_row, text="追加", width=100, command=self._on_add)
        self.btn_add.pack(side="right", padx=(5, 0))
        
        self.btn_delete = ctk.CTkButton(btn_row, text="消去", width=100, command=self._on_delete, state="disabled")
        self.btn_delete.pack(side="right")
        
        if self._disabled:
            self.btn_add.configure(state="disabled")
    
    def _apply_treeview_style(self, style):
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
            pass
    
    def _insert_row(self, keyword, tag, path):
        """Treeviewに行を追加し、tag値を内部dictに保存"""
        label = C.COMMAND_TAG_TO_LABEL.get(tag, "URLを開く")
        item_id = self.tree.insert("", "end", values=(keyword, label, path))
        self._row_tags[item_id] = tag
    
    def _update_row(self, item_id, keyword, tag, path):
        label = C.COMMAND_TAG_TO_LABEL.get(tag, "URLを開く")
        self.tree.item(item_id, values=(keyword, label, path))
        self._row_tags[item_id] = tag
    
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
        dialog = CommandEditDialog(
            self.winfo_toplevel(),
            keyword="", tag="url", path="",
            title="コマンドの追加",
        )
        self.winfo_toplevel().wait_window(dialog)
        if dialog.result:
            r = dialog.result
            self._insert_row(r["keyword"], r["tag"], r["path"])
    
    def _on_delete(self):
        sel = self.tree.selection()
        if not sel:
            return
        for item in sel:
            self._row_tags.pop(item, None)
            self.tree.delete(item)
        self.btn_delete.configure(state="disabled")
    
    def _edit_row(self, item_id):
        values = self.tree.item(item_id, "values")
        keyword = values[0]
        path = values[2]
        tag = self._row_tags.get(item_id, "url")
        
        dialog = CommandEditDialog(
            self.winfo_toplevel(),
            keyword=keyword, tag=tag, path=path,
            title="コマンドの編集",
        )
        self.winfo_toplevel().wait_window(dialog)
        if dialog.result:
            r = dialog.result
            self._update_row(item_id, r["keyword"], r["tag"], r["path"])
    
    # =====================================================
    # 共通I/F
    # =====================================================
    
    def get_values(self):
        """
        Returns:
            list[dict]: [{"keyword": str, "tag": str, "path": str}, ...]
        """
        rows = []
        for item in self.tree.get_children():
            values = self.tree.item(item, "values")
            tag = self._row_tags.get(item, "url")
            rows.append({
                "keyword": values[0],
                "tag": tag,
                "path": values[2],
            })
        return rows
    
    def is_modified(self):
        if self._disabled:
            return False
        current = self.get_values()
        if len(current) != len(self._initial_rows):
            return True
        for c, i in zip(current, self._initial_rows):
            if c["keyword"] != i["keyword"] or c["tag"] != i["tag"] or c["path"] != i["path"]:
                return True
        return False
    
    def is_disabled(self):
        return self._disabled
