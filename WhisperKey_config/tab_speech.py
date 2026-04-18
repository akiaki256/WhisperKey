"""
音声認識タブ
仕様書§6.2
- 認識言語(ラジオボタン)
- モデルサイズ(ラジオボタン、edition別に選択肢分岐)
"""

import customtkinter as ctk

import constants as C


class SpeechTab(ctk.CTkFrame):
    """音声認識タブ"""
    
    def __init__(self, parent, config):
        """
        Args:
            parent: 親ウィジェット
            config: 初期値を含むdict(config_io.load_configの結果)
        """
        super().__init__(parent, fg_color="transparent")
        
        self._edition = config.get("edition", "gpu")
        self._initial_language = config.get("language", C.LANGUAGE_DEFAULT)
        self._initial_model = config.get("model_size", C.MODEL_DEFAULT_GPU)
        
        # 変数
        self.var_language = ctk.StringVar(value=self._initial_language)
        self.var_model = ctk.StringVar(value=self._initial_model)
        
        self._build_ui()
    
    def _build_ui(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=20, pady=15)
        
        # -------- 認識言語 --------
        ctk.CTkLabel(
            container,
            text="認識言語:",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 5))
        
        for tag, label in C.LANGUAGE_CHOICES:
            rb = ctk.CTkRadioButton(
                container,
                text=label,
                variable=self.var_language,
                value=tag,
            )
            rb.pack(anchor="w", padx=20, pady=2)
        
        # -------- モデルサイズ --------
        ctk.CTkLabel(
            container,
            text="モデルサイズ:",
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        ).pack(fill="x", pady=(20, 5))
        
        # edition に応じて選択肢を切り替え
        if self._edition == "cpu":
            choices = C.MODEL_CHOICES_CPU
        else:
            choices = C.MODEL_CHOICES_GPU
        
        for tag, label in choices:
            rb = ctk.CTkRadioButton(
                container,
                text=label,
                variable=self.var_model,
                value=tag,
            )
            rb.pack(anchor="w", padx=20, pady=2)
    
    # =====================================================
    # 共通I/F
    # =====================================================
    
    def get_values(self):
        """現在のUI状態を返す"""
        return {
            "language": self.var_language.get(),
            "model_size": self.var_model.get(),
        }
    
    def is_modified(self):
        """初期値から変更があればTrue"""
        return (
            self.var_language.get() != self._initial_language
            or self.var_model.get() != self._initial_model
        )
