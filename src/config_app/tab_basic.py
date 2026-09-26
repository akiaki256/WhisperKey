"""
基本設定タブ
仕様書§6.1
- マイク選択(ドロップダウン)
- 音量閾値(スライダー + 手入力)
- 無音時間(スライダー + 手入力)
- ショートカットキー(表示ラベル + キー設定ボタン)
"""

import customtkinter as ctk
from CTkMessagebox import CTkMessagebox

import constants as C
import audio_devices
from dialog_shortcut import ShortcutDialog


class BasicTab(ctk.CTkFrame):
    """基本設定タブ"""
    
    def __init__(self, parent, config):
        super().__init__(parent, fg_color="transparent")
        
        # 初期値
        self._initial_device_name = config.get("audio_device_name", C.DEFAULT_DEVICE_LABEL)
        self._initial_volume = int(config.get("volume_threshold", 500))
        self._initial_silence = float(config.get("silence_duration", 1.3))
        self._initial_shortcut = config.get("shortcut_key", "f9")
        
        # 現在値(ショートカットはウィジェットではなく変数で保持)
        self._current_shortcut = self._initial_shortcut
        
        # スライダー連動中フラグ(再帰呼び出し防止)
        self._sync_lock = False
        
        self._build_ui()
    
    def _build_ui(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=10)
        
        # -------- マイク選択 --------
        ctk.CTkLabel(
            container,
            text="マイク選択:",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 5))
        
        device_names = audio_devices.get_device_name_list()
        self.combo_device = ctk.CTkComboBox(
            container,
            values=device_names,
            state="readonly",
            width=420,
        )
        self.combo_device.pack(fill="x", padx=5, pady=(0, 2))
        
        # 初期値を設定(リストにない場合は先頭=既定)
        if self._initial_device_name in device_names:
            self.combo_device.set(self._initial_device_name)
        else:
            self.combo_device.set(C.DEFAULT_DEVICE_LABEL)
        
        ctk.CTkLabel(
            container,
            text="使用するマイクを選択してください",
            text_color="gray",
            anchor="w",
        ).pack(fill="x", padx=5, pady=(0, 15))
        
        # -------- 音量閾値 --------
        ctk.CTkLabel(
            container,
            text="音量閾値:",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 5))
        
        vol_row = ctk.CTkFrame(container, fg_color="transparent")
        vol_row.pack(fill="x", padx=5)
        
        self.slider_volume = ctk.CTkSlider(
            vol_row,
            from_=C.VOLUME_THRESHOLD_MIN,
            to=C.VOLUME_THRESHOLD_MAX,
            number_of_steps=C.VOLUME_THRESHOLD_MAX - C.VOLUME_THRESHOLD_MIN,
            command=self._on_volume_slider,
        )
        self.slider_volume.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.slider_volume.set(self._initial_volume)
        
        self.entry_volume = ctk.CTkEntry(vol_row, width=70, justify="right")
        self.entry_volume.pack(side="left")
        self.entry_volume.insert(0, str(self._initial_volume))
        self.entry_volume.bind("<FocusOut>", self._on_volume_focus_out)
        self.entry_volume.bind("<Return>", self._on_volume_focus_out)
        
        ctk.CTkLabel(
            container,
            text="録音を開始する音量レベル(値を上げるほど静かな音を拾わなくなります)",
            text_color="gray",
            anchor="w",
        ).pack(fill="x", padx=5, pady=(2, 15))
        
        # -------- 無音時間 --------
        ctk.CTkLabel(
            container,
            text="無音時間:",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 5))
        
        sil_row = ctk.CTkFrame(container, fg_color="transparent")
        sil_row.pack(fill="x", padx=5)
        
        # 0.1刻み: (max - min) / step で number_of_steps を計算
        step_count = int(round((C.SILENCE_DURATION_MAX - C.SILENCE_DURATION_MIN) / C.SILENCE_DURATION_STEP))
        self.slider_silence = ctk.CTkSlider(
            sil_row,
            from_=C.SILENCE_DURATION_MIN,
            to=C.SILENCE_DURATION_MAX,
            number_of_steps=step_count,
            command=self._on_silence_slider,
        )
        self.slider_silence.pack(side="left", fill="x", expand=True, padx=(0, 10))
        self.slider_silence.set(self._initial_silence)
        
        self.entry_silence = ctk.CTkEntry(sil_row, width=50, justify="right")
        self.entry_silence.pack(side="left", padx=(0, 5))
        self.entry_silence.insert(0, f"{self._initial_silence:.1f}")
        self.entry_silence.bind("<FocusOut>", self._on_silence_focus_out)
        self.entry_silence.bind("<Return>", self._on_silence_focus_out)
        
        ctk.CTkLabel(sil_row, text="秒").pack(side="left")
        
        ctk.CTkLabel(
            container,
            text="話し終わってから変換を開始するまでの時間",
            text_color="gray",
            anchor="w",
        ).pack(fill="x", padx=5, pady=(2, 15))
        
        # -------- ショートカットキー --------
        ctk.CTkLabel(
            container,
            text="ショートカットキー:",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 5))
        
        sc_row = ctk.CTkFrame(container, fg_color="transparent")
        sc_row.pack(fill="x", padx=5)
        
        self.label_shortcut = ctk.CTkLabel(
            sc_row,
            text=self._format_shortcut_display(self._current_shortcut),
            width=120,
            anchor="w",
            fg_color=("gray90", "gray20"),
            corner_radius=5,
        )
        self.label_shortcut.pack(side="left", padx=(0, 10), ipady=4)
        
        ctk.CTkButton(
            sc_row,
            text="キー設定",
            width=100,
            command=self._on_shortcut_click,
        ).pack(side="left")
        
        ctk.CTkLabel(
            container,
            text="録音のオン/オフを切り替えるキー",
            text_color="gray",
            anchor="w",
        ).pack(fill="x", padx=5, pady=(2, 0))
    
    # =====================================================
    # スライダー・入力欄の連動
    # =====================================================
    
    def _on_volume_slider(self, value):
        """スライダーが動いたらEntryに反映"""
        if self._sync_lock:
            return
        self._sync_lock = True
        try:
            v = int(round(float(value)))
            self.entry_volume.delete(0, "end")
            self.entry_volume.insert(0, str(v))
        finally:
            self._sync_lock = False
    
    def _on_volume_focus_out(self, event=None):
        """Entryからフォーカスが外れたらバリデーション + スライダーに反映"""
        if self._sync_lock:
            return
        
        raw = self.entry_volume.get().strip()
        valid = self._validate_volume(raw)
        
        if valid is None:
            CTkMessagebox(
                master=self.winfo_toplevel(),
                title="入力エラー",
                message=f"音量閾値は{C.VOLUME_THRESHOLD_MIN}〜{C.VOLUME_THRESHOLD_MAX}の整数で入力してください。",
                icon="warning",
                option_1="OK",
            )
            # スライダー値で復元
            self._sync_lock = True
            try:
                current = int(round(self.slider_volume.get()))
                self.entry_volume.delete(0, "end")
                self.entry_volume.insert(0, str(current))
            finally:
                self._sync_lock = False
            return
        
        # 正常値。スライダーとEntry両方を揃える
        self._sync_lock = True
        try:
            self.slider_volume.set(valid)
            self.entry_volume.delete(0, "end")
            self.entry_volume.insert(0, str(valid))
        finally:
            self._sync_lock = False
    
    def _validate_volume(self, raw):
        """文字列を検証。有効ならint、無効ならNone"""
        if raw == "":
            return None
        try:
            v = int(raw)
        except ValueError:
            return None
        if v < C.VOLUME_THRESHOLD_MIN or v > C.VOLUME_THRESHOLD_MAX:
            return None
        return v
    
    def _on_silence_slider(self, value):
        if self._sync_lock:
            return
        self._sync_lock = True
        try:
            # 0.1刻みに丸める
            v = round(float(value) * 10) / 10
            self.entry_silence.delete(0, "end")
            self.entry_silence.insert(0, f"{v:.1f}")
        finally:
            self._sync_lock = False
    
    def _on_silence_focus_out(self, event=None):
        if self._sync_lock:
            return
        
        raw = self.entry_silence.get().strip()
        valid = self._validate_silence(raw)
        
        if valid is None:
            CTkMessagebox(
                master=self.winfo_toplevel(),
                title="入力エラー",
                message=f"無音時間は{C.SILENCE_DURATION_MIN}〜{C.SILENCE_DURATION_MAX}秒で入力してください。",
                icon="warning",
                option_1="OK",
            )
            self._sync_lock = True
            try:
                current = round(self.slider_silence.get() * 10) / 10
                self.entry_silence.delete(0, "end")
                self.entry_silence.insert(0, f"{current:.1f}")
            finally:
                self._sync_lock = False
            return
        
        self._sync_lock = True
        try:
            self.slider_silence.set(valid)
            self.entry_silence.delete(0, "end")
            self.entry_silence.insert(0, f"{valid:.1f}")
        finally:
            self._sync_lock = False
    
    def _validate_silence(self, raw):
        """文字列を検証。有効ならfloat(小数第1位)、無効ならNone"""
        if raw == "":
            return None
        try:
            v = float(raw)
        except ValueError:
            return None
        if v < C.SILENCE_DURATION_MIN or v > C.SILENCE_DURATION_MAX:
            return None
        return round(v, 1)
    
    # =====================================================
    # ショートカットキー
    # =====================================================
    
    def _format_shortcut_display(self, key_str):
        """保存形式 → 表示用(先頭大文字)"""
        if not key_str:
            return "F9"
        parts = key_str.split("+")
        return "+".join(p.capitalize() for p in parts)
    
    def _on_shortcut_click(self):
        dialog = ShortcutDialog(self.winfo_toplevel(), current_key=self._current_shortcut)
        self.winfo_toplevel().wait_window(dialog)
        if dialog.result is not None:
            self._current_shortcut = dialog.result
            self.label_shortcut.configure(text=self._format_shortcut_display(dialog.result))
    
    # =====================================================
    # 共通I/F
    # =====================================================
    
    def get_values(self):
        """現在のUI状態を返す"""
        # マイク選択から index/name/sample_rate を決定
        device_name = self.combo_device.get()
        device_info = audio_devices.find_device_by_name(device_name)
        
        if device_info is None:
            # 既定デバイス
            device_index = None
            sample_rate = C.SAMPLE_RATE
        else:
            device_index = device_info["index"]
            sample_rate = device_info["sample_rate"]
        
        # Entry値は validate 済みの前提だが、念のため再取得
        try:
            volume = int(self.entry_volume.get())
        except ValueError:
            volume = int(round(self.slider_volume.get()))
        
        try:
            silence = round(float(self.entry_silence.get()), 1)
        except ValueError:
            silence = round(self.slider_silence.get() * 10) / 10
        
        return {
            "audio_device_index": device_index,
            "audio_device_name": device_name,
            "audio_device_sample_rate": sample_rate,
            "volume_threshold": volume,
            "silence_duration": silence,
            "shortcut_key": self._current_shortcut,
        }
    
    def is_modified(self):
        values = self.get_values()
        return (
            values["audio_device_name"] != self._initial_device_name
            or values["volume_threshold"] != self._initial_volume
            or abs(values["silence_duration"] - self._initial_silence) > 1e-9
            or values["shortcut_key"] != self._initial_shortcut
        )
