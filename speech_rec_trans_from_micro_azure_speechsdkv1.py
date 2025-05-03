# -*- coding: utf-8 -*-
"""
Created on Fri May  2 10:54:16 2025

@author: Takming
"""

# -*- coding: utf-8 -*-
"""
Created on Fri May  2 10:08:45 2025

@author: Takming
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import azure.cognitiveservices.speech as speechsdk
import time
import os
import json
from threading import Thread, Event
from dotenv import load_dotenv
from googletrans import Translator  # 需要先使用pip安裝: pip install googletrans==4.0.0-rc1
import requests

# 語言對應表
AVAILABLE_LANGUAGES = {
    "英文": "en-US",
    "日文": "ja-JP",
    "越南文": "vi-VN",
    "中文": "zh-TW",
}

class SubtitleApp:
    def __init__(self, root):
        self.root = root
        self.root.title("同步翻譯字幕")
        self.root.geometry("1100x220")
        
        # 確保視窗保持在最上層
        self.root.wm_attributes("-topmost", True)
        
        # 初始化變數
        self.source_language = tk.StringVar(value="zh-TW")
        self.target_languages = []
        self.font_size = tk.IntVar(value=16)
        self.font_color = tk.StringVar(value="white")
        self.bg_color = tk.StringVar(value="black")
        self.transparent_mode = False
        self.selected_languages = []
        self.is_listening = False
        self.translation_recognizer = None
        self.stop_event = Event()  # 用於正確停止線程
        # 添加節流相關變量
        self.last_translation_time = 0
        self.translation_throttle = 0.5  # 最小翻譯間隔（秒）
        # 專有名詞字典
        self.phrase_dict = {}
        
        # 字幕歷史
        self.subtitle_history = []
        self.current_subtitle_index = -1
        
        # 字幕顯示區域 - 使用多個標籤來顯示不同語言
        self.subtitles_frame = tk.Frame(self.root, bg="black")
        self.subtitles_frame.pack(expand=True, fill=tk.BOTH)
        
        # 原始文字標籤
        self.original_text_var = tk.StringVar()
        self.original_label = tk.Label(
            self.subtitles_frame, 
            textvariable=self.original_text_var, 
            font=("Arial", self.font_size.get()), 
            fg=self.font_color.get(), 
            bg=self.bg_color.get(),
            wraplength=1000,
            justify=tk.LEFT
        )
        self.original_label.pack(fill=tk.X, anchor=tk.W, padx=5, pady=2)
        
        # 翻譯文字的標籤字典 - 將在動態創建
        self.translation_labels = {}
        self.translation_vars = {}
        
        # 建立UI元素
        self.create_settings_panel()
        self.create_control_buttons()
        
        # 設定視窗關閉處理 - 確保正確關閉
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 從.env檔案加載憑證
        load_dotenv('.env')
        self.speech_key = os.getenv('SPEECH_KEY')
        self.speech_region = os.getenv('SPEECH_REGION')
        
        if not self.speech_key or not self.speech_region:
            self.show_api_key_dialog()
            
        # 存儲逐字顯示的當前狀態
        self.current_recognition_id = None
        self.partial_results = {}
        
        # 嘗試載入字典檔
        self.load_phrase_dictionary()
        # 創建Google Translate翻譯器實例
        try:
            self.translator = Translator()
        except Exception as e:
            print(f"初始化翻譯器失敗: {str(e)}")
            self.translator = None

    def create_settings_panel(self):
        """創建設定面板"""
        self.settings_frame = tk.Frame(self.root)
        self.settings_frame.pack(side=tk.TOP, fill=tk.X)

        # 左側面板 - 語言設定
        left_panel = tk.Frame(self.settings_frame)
        left_panel.pack(side=tk.LEFT, fill=tk.Y)
        
        # 源語言設定
        tk.Label(left_panel, text="語音:").pack(side=tk.LEFT)
        ttk.Combobox(
            left_panel, textvariable=self.source_language, 
            values=["zh-TW", "en-US", "ja-JP", "vi-VN"], width=8
        ).pack(side=tk.LEFT)

        # 目標語言設定
        tk.Label(left_panel, text="字幕:").pack(side=tk.LEFT)
        self.language_listbox = tk.Listbox(left_panel, selectmode=tk.MULTIPLE, height=4, width=10)
        for lang in AVAILABLE_LANGUAGES.keys():
            self.language_listbox.insert(tk.END, lang)
        self.language_listbox.pack(side=tk.LEFT)
        
        # 應用語言按鈕
        tk.Button(left_panel, text="設定語言", command=self.apply_language_settings).pack(side=tk.LEFT)

        # 中間面板 - 外觀設定
        middle_panel = tk.Frame(self.settings_frame)
        middle_panel.pack(side=tk.LEFT, fill=tk.Y, padx=10)
        
        # 字體大小設定
        tk.Label(middle_panel, text="字體大小:").pack(side=tk.LEFT)
        tk.Spinbox(middle_panel, from_=10, to=50, textvariable=self.font_size, width=5).pack(side=tk.LEFT)

        # 字體顏色設定
        tk.Label(middle_panel, text="字體顏色:").pack(side=tk.LEFT)
        ttk.Combobox(
            middle_panel, textvariable=self.font_color, 
            values=["white", "yellow", "red"], width=8
        ).pack(side=tk.LEFT)

        # 背景顏色設定
        tk.Label(middle_panel, text="背景顏色:").pack(side=tk.LEFT)
        ttk.Combobox(
            middle_panel, textvariable=self.bg_color, 
            values=["black", "blue", "gray", "green"], width=8
        ).pack(side=tk.LEFT)

        # 應用外觀按鈕
        tk.Button(middle_panel, text="設定外觀", command=self.apply_appearance_settings).pack(side=tk.LEFT)
        
        # 右側面板 - 專有名詞字典
        right_panel = tk.Frame(self.settings_frame)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=10)
        
        # 專有名詞字典按鈕
        tk.Button(right_panel, text="載入字典", command=self.load_dictionary_file).pack(side=tk.LEFT, padx=5)
        tk.Button(right_panel, text="編輯字典", command=self.edit_dictionary).pack(side=tk.LEFT, padx=5)

    def create_control_buttons(self):
        """創建控制按鈕"""
        control_frame = tk.Frame(self.root)
        control_frame.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.start_button = tk.Button(control_frame, text="開始聆聽", command=self.toggle_listening)
        self.start_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        # 字幕歷史控制
        history_frame = tk.Frame(control_frame)
        history_frame.pack(side=tk.LEFT, padx=20)
        tk.Button(history_frame, text="◀", command=self.prev_subtitle).pack(side=tk.LEFT)
        tk.Button(history_frame, text="▶", command=self.next_subtitle).pack(side=tk.LEFT)
        
        self.toggle_button = tk.Button(control_frame, text="切換透明", command=self.toggle_transparency)
        self.toggle_button.pack(side=tk.RIGHT, padx=5, pady=5)
        
        self.clear_button = tk.Button(control_frame, text="清除字幕", command=self.clear_subtitles)
        self.clear_button.pack(side=tk.RIGHT, padx=5, pady=5)

    def show_api_key_dialog(self):
        """顯示Azure Speech API憑證輸入對話框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Azure Speech API 憑證")
        dialog.geometry("400x150")
        dialog.transient(self.root)
        dialog.grab_set()
        
        tk.Label(dialog, text="請輸入您的Azure Speech API憑證:").pack(pady=5)
        
        key_frame = tk.Frame(dialog)
        key_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(key_frame, text="Speech Key:").pack(side=tk.LEFT)
        key_entry = tk.Entry(key_frame, width=30)
        key_entry.pack(side=tk.LEFT, padx=5)
        
        region_frame = tk.Frame(dialog)
        region_frame.pack(fill=tk.X, padx=10, pady=5)
        tk.Label(region_frame, text="Region:").pack(side=tk.LEFT)
        region_entry = tk.Entry(region_frame, width=30)
        region_entry.pack(side=tk.LEFT, padx=5)
        
        def save_credentials():
            self.speech_key = key_entry.get()
            self.speech_region = region_entry.get()
            if self.speech_key and self.speech_region:
                dialog.destroy()
            else:
                messagebox.showerror("錯誤", "兩個欄位都必須填寫")
                
        tk.Button(dialog, text="儲存", command=save_credentials).pack(pady=10)
        
        # 將對話框置中
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")
        
        dialog.wait_window()

    def apply_language_settings(self):
        """應用語言設定"""
        # 追蹤已選擇的語言
        new_selected_indices = self.language_listbox.curselection()
        if new_selected_indices != self.selected_languages:
            self.selected_languages = new_selected_indices
            self.target_languages = [
                AVAILABLE_LANGUAGES[self.language_listbox.get(i)] for i in new_selected_indices
            ]
            # 從目標語言中排除源語言
            self.target_languages = [
                lang for lang in self.target_languages if lang != self.source_language.get()
            ]
            
            # 創建或更新翻譯標籤
            self.update_translation_labels()

    def update_translation_labels(self):
        """更新翻譯標籤"""
        # 清除現有的翻譯標籤
        for label in self.translation_labels.values():
            label.pack_forget()
        
        self.translation_labels = {}
        self.translation_vars = {}
        
        # 為每個目標語言創建新標籤
        for lang_code in self.target_languages:
            # 找出對應的語言名稱
            lang_name = next((name for name, code in AVAILABLE_LANGUAGES.items() 
                            if code == lang_code), lang_code)
            
            # 創建變數和標籤
            self.translation_vars[lang_code] = tk.StringVar()
            self.translation_labels[lang_code] = tk.Label(
                self.subtitles_frame, 
                textvariable=self.translation_vars[lang_code], 
                font=("Arial", self.font_size.get()), 
                fg=self.font_color.get(), 
                bg=self.bg_color.get(),
                wraplength=1000,
                justify=tk.LEFT
            )
            # 顯示標籤
            self.translation_labels[lang_code].pack(fill=tk.X, anchor=tk.W, padx=5, pady=2)

    def apply_appearance_settings(self):
        """應用外觀設定"""
        # 更新原始語言標籤
        self.original_label.config(
            font=("Arial", self.font_size.get()),
            fg=self.font_color.get(),
            bg=self.bg_color.get()
        )
        
        # 更新翻譯標籤
        for label in self.translation_labels.values():
            label.config(
                font=("Arial", self.font_size.get()),
                fg=self.font_color.get(),
                bg=self.bg_color.get()
            )
            
        # 更新字幕框背景
        self.subtitles_frame.config(bg=self.bg_color.get())

    def toggle_transparency(self):
        """切換透明模式"""
        self.transparent_mode = not self.transparent_mode
        if self.transparent_mode:
            self.root.attributes("-alpha", 0.8)
            self.settings_frame.pack_forget()
            self.toggle_button.config(text="顯示視窗")
        else:
            self.root.attributes("-alpha", 1.0)
            self.settings_frame.pack(side=tk.TOP, fill=tk.X)
            self.toggle_button.config(text="切換透明")

    def toggle_listening(self):
        """開始或停止語音識別"""
        if not self.is_listening:
            # 檢查是否有憑證
            if not self.speech_key or not self.speech_region:
                messagebox.showerror("錯誤", "需要Azure Speech API憑證")
                self.show_api_key_dialog()
                return
                
            # 檢查是否有目標語言
            if not self.target_languages:
                messagebox.showerror("錯誤", "請至少選擇一種目標語言")
                return
                
            # 開始聆聽
            self.is_listening = True
            self.stop_event.clear()
            self.start_button.config(text="停止聆聽")
            Thread(target=self.start_speech_recognition, daemon=True).start()
        else:
            # 停止聆聽
            self.stop_event.set()
            self.is_listening = False
            self.start_button.config(text="開始聆聽")
            # 停止語音識別
            if self.translation_recognizer:
                self.translation_recognizer.stop_continuous_recognition_async()

    def clear_subtitles(self):
        """清除所有字幕"""
        self.original_text_var.set("")
        for var in self.translation_vars.values():
            var.set("")
        
        # 重置部分結果追蹤
        self.current_recognition_id = None
        self.partial_results = {}
        
        # 清除字幕歷史
        self.subtitle_history = []
        self.current_subtitle_index = -1

    def add_to_subtitle_history(self, original_text, translations):
        """將當前字幕添加到歷史記錄"""
        # 添加新字幕到歷史
        self.subtitle_history.append({
            'original': original_text,
            'translations': translations.copy() if translations else {}
        })
        # 更新索引指向最新字幕
        self.current_subtitle_index = len(self.subtitle_history) - 1

    def display_subtitle(self, subtitle_data):
        """顯示指定的字幕數據"""
        if subtitle_data:
            self.original_text_var.set(subtitle_data['original'])
            for lang_code, text in subtitle_data['translations'].items():
                if lang_code in self.translation_vars:
                    self.translation_vars[lang_code].set(text)

    def prev_subtitle(self):
        """顯示前一條字幕"""
        if self.subtitle_history and self.current_subtitle_index > 0:
            self.current_subtitle_index -= 1
            self.display_subtitle(self.subtitle_history[self.current_subtitle_index])

    def next_subtitle(self):
        """顯示後一條字幕"""
        if self.subtitle_history and self.current_subtitle_index < len(self.subtitle_history) - 1:
            self.current_subtitle_index += 1
            self.display_subtitle(self.subtitle_history[self.current_subtitle_index])

    def recognizing_handler(self, evt):
        """處理部分識別事件 - 即時更新逐字結果"""
        # 獲取唯一識別此語音片段的ID
        if hasattr(evt.result, 'session_id'):
            session_id = evt.result.session_id
        else:
            # 如果沒有session_id，使用偵測時間作為ID
            session_id = time.time()
            
        self.current_recognition_id = session_id
        
        # 套用專有名詞字典進行替換
        partial_text = self.apply_phrase_dictionary(evt.result.text)
        self.root.after(0, lambda: self.original_text_var.set(partial_text))
        
        # 存儲部分結果，以便在recognized_handler中使用
        self.partial_results[session_id] = {
            'original': partial_text,
            'translations': {}
        }
    
        # 如果有文本且有目標語言，啟動翻譯線程
        if partial_text and self.target_languages:
           Thread(target=self.translate_partial_text, args=(partial_text, session_id), daemon=True).start()

    def translate_partial_text(self, text, session_id):
       #"""使用Google Translate API實時翻譯部分文本（帶節流）"""
        current_time = time.time()
    
    # 檢查節流間隔
        if current_time - self.last_translation_time < self.translation_throttle:
           return
        
        self.last_translation_time = current_time
    
        if not text or not self.translator:
           return
        
        for lang_code in self.target_languages:
            try:
            # 從完整語言代碼(如'en-US')中提取基本語言代碼('en')
              target_lang = lang_code.split('-')[0]
            
            # 使用Google Translate API進行翻譯
              result = self.translator.translate(text, dest=target_lang)
              translated_text = result.text if result else ""
            
            # 對翻譯文字也套用字典替換
              translated_text = self.apply_translation_dictionary(translated_text)
            
            # 更新UI顯示翻譯
              if lang_code in self.translation_vars:
                self.root.after(0, lambda lc=lang_code, txt=translated_text: 
                              self.translation_vars[lc].set(txt))
                
            # 更新部分結果字典
              if session_id in self.partial_results:
                self.partial_results[session_id]['translations'][lang_code] = translated_text
                
            except Exception as e:
               print(f"翻譯錯誤 ({lang_code}): {str(e)}")
               error_message = f"翻譯錯誤: {str(e)}"
            
            # 在UI上顯示錯誤信息
               if lang_code in self.translation_vars:
                  self.root.after(0, lambda lc=lang_code, err=error_message: 
                              self.translation_vars[lc].set(err))



    def recognized_handler(self, evt):
        """處理完整識別事件"""
        # 獲取唯一識別此語音片段的ID
        if hasattr(evt.result, 'session_id'):
            session_id = evt.result.session_id
        else:
            # 如果沒有session_id，使用當前時間作為ID
            session_id = time.time()
        
        # 原始文字（套用專有名詞字典進行替換）
        original_text = self.apply_phrase_dictionary(evt.result.text)
        translations = {}
        
        if original_text:  # 避免空白結果
            self.root.after(0, lambda: self.original_text_var.set(original_text))
            
            # 處理翻譯
            for lang_code in self.target_languages:
                # 嘗試使用Azure的翻譯結果
                azure_translation = None
                if lang_code in evt.result.translations:
                    azure_translation  = evt.result.translations[lang_code]
                    # 對翻譯文字也套用字典替換
                    azure_translation  = self.apply_translation_dictionary(azure_translation )
                  # 如果有Azure翻譯結果，則使用它；否則保留Google的即時翻譯
                if azure_translation:   
                    translations[lang_code] = azure_translation 
                    
                    # 更新此語言的翻譯
                    if lang_code in self.translation_vars:
                        self.root.after(0, lambda lc=lang_code, txt=azure_translation: 
                                        self.translation_vars[lc].set(txt))
                elif session_id in self.partial_results and lang_code in self.partial_results[session_id]['translations']:
                # 使用最後的Google翻譯結果
                    google_translation = self.partial_results[session_id]['translations'][lang_code]
                    translations[lang_code] = google_translation
                    # 不需要更新UI，因為Google翻譯已經更新了
        
            # 將當前字幕添加到歷史記錄
            self.root.after(0, lambda: self.add_to_subtitle_history(original_text, translations))

    def apply_phrase_dictionary(self, text):
        """套用專有名詞字典進行文字替換"""
        if not text or not self.phrase_dict:
            return text
            
        result = text
        for orig, replacement in self.phrase_dict.items():
            result = result.replace(orig, replacement)
        return result
    def apply_translation_dictionary(self, text):
        """對翻譯文字套用專有名詞字典"""
        if not text or not self.phrase_dict:
            return text
            
        result = text
        
        # 創建反向字典來處理翻譯 (用於將翻譯中的原始詞替換為修正詞)
        # 這裡假設同一個錯誤詞會被替換為同一個正確詞
        for orig, replacement in self.phrase_dict.items():
            # 在翻譯文本中也進行相同的替換
            result = result.replace(orig, replacement)
            
            # 另外檢查小寫版本
            orig_lower = orig.lower()
            if orig != orig_lower:
                result = result.replace(orig_lower, replacement)
        
        return result


    def load_phrase_dictionary(self, filename="dictionary.json"):
        """載入專有名詞字典"""
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    self.phrase_dict = json.load(f)
                print(f"已載入字典，共 {len(self.phrase_dict)} 個條目")
            else:
                # 如果字典檔不存在，創建一個空字典並保存
                self.phrase_dict = {}
                self.save_phrase_dictionary()
        except Exception as e:
            print(f"載入字典時發生錯誤: {str(e)}")
            self.phrase_dict = {}

    def save_phrase_dictionary(self, filename="dictionary.json"):
        """保存專有名詞字典"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.phrase_dict, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"保存字典時發生錯誤: {str(e)}")

    def load_dictionary_file(self):
        """開啟檔案對話框載入字典"""
        file_path = filedialog.askopenfilename(
            title="選擇字典檔案",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.phrase_dict = json.load(f)
                messagebox.showinfo("成功", f"已載入字典，共 {len(self.phrase_dict)} 個條目")
            except Exception as e:
                messagebox.showerror("錯誤", f"載入字典時發生錯誤: {str(e)}")

    def edit_dictionary(self):
        """編輯字典"""
        dictionary_editor = tk.Toplevel(self.root)
        dictionary_editor.title("專有名詞字典編輯")
        dictionary_editor.geometry("500x400")
        
        # 建立表格框架
        table_frame = tk.Frame(dictionary_editor)
        table_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        
        # 滾動條
        scrollbar = tk.Scrollbar(table_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 列表框
        columns = ("原始文字", "替換文字")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", yscrollcommand=scrollbar.set)
        
        # 設定列標題
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=200)
        
        # 載入字典數據
        for orig, replacement in self.phrase_dict.items():
            tree.insert("", tk.END, values=(orig, replacement))
        
        tree.pack(expand=True, fill=tk.BOTH)
        scrollbar.config(command=tree.yview)
        
        # 編輯區域
        edit_frame = tk.Frame(dictionary_editor)
        edit_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(edit_frame, text="原始文字:").grid(row=0, column=0, sticky=tk.W)
        orig_entry = tk.Entry(edit_frame, width=20)
        orig_entry.grid(row=0, column=1, padx=5, pady=5)
        
        tk.Label(edit_frame, text="替換文字:").grid(row=0, column=2, sticky=tk.W)
        replacement_entry = tk.Entry(edit_frame, width=20)
        replacement_entry.grid(row=0, column=3, padx=5, pady=5)
        
        # 按鈕框架
        button_frame = tk.Frame(dictionary_editor)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        
        def add_item():
            orig = orig_entry.get().strip()
            replacement = replacement_entry.get().strip()
            if orig and replacement:
                self.phrase_dict[orig] = replacement
                tree.insert("", tk.END, values=(orig, replacement))
                orig_entry.delete(0, tk.END)
                replacement_entry.delete(0, tk.END)
        
        def remove_item():
            selected = tree.selection()
            if selected:
                item = tree.item(selected[0])
                orig = item['values'][0]
                if orig in self.phrase_dict:
                    del self.phrase_dict[orig]
                tree.delete(selected[0])
        
        def edit_item():
            selected = tree.selection()
            if selected:
                item = tree.item(selected[0])
                orig_entry.delete(0, tk.END)
                replacement_entry.delete(0, tk.END)
                orig_entry.insert(0, item['values'][0])
                replacement_entry.insert(0, item['values'][1])
                
                # 刪除原條目
                remove_item()
        
        def save_dictionary():
            self.save_phrase_dictionary()
            messagebox.showinfo("成功", "字典已保存")
            dictionary_editor.destroy()
        
        tk.Button(button_frame, text="新增", command=add_item).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="刪除", command=remove_item).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="編輯", command=edit_item).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="保存並關閉", command=save_dictionary).pack(side=tk.RIGHT, padx=5)

    def start_speech_recognition(self):
        """開始連續語音識別過程"""
        try:
            # 配置語音翻譯
            speech_translation_config = speechsdk.translation.SpeechTranslationConfig(
                subscription=self.speech_key, 
                region=self.speech_region
            )
            
            # 設置源語言
            speech_translation_config.speech_recognition_language = self.source_language.get()
            
            # 添加目標語言
            for lang_code in self.target_languages:
                speech_translation_config.add_target_language(lang_code)
            
            # 創建使用麥克風的識別器
            audio_config = speechsdk.audio.AudioConfig(use_default_microphone=True)
            self.translation_recognizer = speechsdk.translation.TranslationRecognizer(
                translation_config=speech_translation_config, 
                audio_config=audio_config
            )
            
            # 訂閱事件
            self.translation_recognizer.recognizing.connect(self.recognizing_handler)  # 用於逐字更新
            self.translation_recognizer.recognized.connect(self.recognized_handler)
            self.translation_recognizer.canceled.connect(self.canceled_handler)
            self.translation_recognizer.session_stopped.connect(self.session_stopped_handler)
            
            # 開始連續識別
            self.translation_recognizer.start_continuous_recognition()
            
            # 更新UI顯示正在聆聽
            self.root.after(0, lambda: self.original_text_var.set("正在聆聽..."))
            
            # 保持執行緒活動直到停止聆聽
            while self.is_listening and not self.stop_event.is_set():
                time.sleep(0.1)
                
            # 確保識別器停止
            if self.translation_recognizer and not self.stop_event.is_set():
                self.translation_recognizer.stop_continuous_recognition()
                
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("錯誤", f"語音識別錯誤: {str(e)}"))
            self.is_listening = False
            self.root.after(0, lambda: self.start_button.config(text="開始聆聽"))

    def canceled_handler(self, evt):
        """處理語音識別取消事件"""
        cancellation_msg = f"識別取消: {evt.reason}"
        if evt.reason == speechsdk.CancellationReason.Error:
            cancellation_msg += f" - 錯誤: {evt.error_details}"
            
        self.root.after(0, lambda: self.original_text_var.set(cancellation_msg))
        
        if evt.reason == speechsdk.CancellationReason.Error:
            self.root.after(0, lambda: messagebox.showerror(
                "錯誤", f"語音識別錯誤: {evt.error_details}"
            ))

    def session_stopped_handler(self, evt):
        """處理會話停止事件"""
        self.is_listening = False
        self.root.after(0, lambda: self.start_button.config(text="開始聆聽"))

    def on_close(self):
        """處理窗口關閉事件"""
        try:
            # 設置停止事件，通知所有線程停止
            self.stop_event.set()
            
            # 停止語音識別
            if self.translation_recognizer:
                # 使用非同步方式停止，避免阻塞UI線程
                self.translation_recognizer.stop_continuous_recognition_async()
                time.sleep(0.5)  # 給一點時間讓它停止
            
            self.is_listening = False
            
            # 保存字典
            self.save_phrase_dictionary()
            
            # 銷毀視窗
            self.root.destroy()
        except Exception as e:
            print(f"關閉程式時發生錯誤: {str(e)}")
            # 強制關閉
            self.root.destroy()

# 啟動應用程式
if __name__ == "__main__":
    root = tk.Tk()
    app = SubtitleApp(root)
    root.mainloop()