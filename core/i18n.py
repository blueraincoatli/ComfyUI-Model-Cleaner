import json
from pathlib import Path
import threading

class I18nManager:
    _instance = None
    _lock = threading.Lock() # For thread-safe singleton creation

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, '_initialized') and self._initialized: # Prevent re-initialization
            return
        
        self.translations = {}
        self.current_language = "en"  # Default language
        # Correctly points to ComfyUI_model_cleaner/translations
        self.base_path = Path(__file__).resolve().parent.parent / "translations"
        self._load_all_languages()
        self._initialized = True

    def _load_language_data(self, lang_code):
        try:
            lang_file = self.base_path / f"{lang_code}.json"
            if lang_file.exists():
                with open(lang_file, "r", encoding="utf-8") as f:
                    self.translations[lang_code] = json.load(f)
                print(f"ComfyModelCleaner I18n: Successfully loaded translations for {lang_code} from {lang_file}")
            else:
                print(f"ComfyModelCleaner I18n Warning: Language file for '{lang_code}' not found at {lang_file}")
                if lang_code not in self.translations:
                    self.translations[lang_code] = {}
        except Exception as e:
            print(f"ComfyModelCleaner I18n Error: Error loading language file for '{lang_code}': {e}")
            if lang_code not in self.translations:
                self.translations[lang_code] = {}
    
    def _load_all_languages(self):
        if not self.base_path.exists():
            self.base_path.mkdir(parents=True, exist_ok=True) # Create directory if it doesn't exist
            print(f"ComfyModelCleaner I18n Warning: Translations directory created at {self.base_path}. Please add translation files (e.g., en.json, zh.json).")
            self.translations["en"] = {} # Ensure 'en' exists as a fallback
            return

        loaded_langs = []
        for lang_file in self.base_path.glob("*.json"):
            lang_code = lang_file.stem
            self._load_language_data(lang_code)
            if lang_code in self.translations and self.translations[lang_code]:
                loaded_langs.append(lang_code)
        
        if not loaded_langs:
            print(f"ComfyModelCleaner I18n Warning: No translation files found or loaded from {self.base_path}.")

        if "en" not in self.translations: # Ensure 'en' exists as a fallback
            self.translations["en"] = {}
        if "zh" not in self.translations: # Ensure 'zh' exists
            self.translations["zh"] = {}


    def set_language(self, lang_code):
        # Normalize lang_code (e.g., "zh_CN" -> "zh", "en_US" -> "en")
        normalized_lang_code = lang_code.split('_')[0].lower()
        
        if normalized_lang_code in self.translations and self.translations[normalized_lang_code]:
            self.current_language = normalized_lang_code
        elif "en" in self.translations and self.translations["en"]:
            print(f"ComfyModelCleaner I18n Warning: Language '{normalized_lang_code}' not fully supported or empty. Falling back to 'en'.")
            self.current_language = "en"
        else:
             print(f"ComfyModelCleaner I18n Warning: Language '{normalized_lang_code}' and fallback 'en' not found or empty. Using keys as strings.")
             # Use a special key to indicate no translations are effectively loaded
             # This helps in get_string to return the key itself or a provided default.
             self.current_language = "_key_fallback_" 
             if self.current_language not in self.translations: # Ensure this special key dict exists
                 self.translations[self.current_language] = {}


    def get_string(self, key, default_text_or_args=None, **kwargs):
        fmt_args = {}
        default_text = key # Default to key itself if no translation and no default_text provided

        if isinstance(default_text_or_args, str):
            default_text = default_text_or_args
            fmt_args = kwargs
        elif isinstance(default_text_or_args, dict):
            fmt_args = default_text_or_args
        elif default_text_or_args is None: # No default text, only formatting kwargs
            fmt_args = kwargs
        
        translation = self.translations.get(self.current_language, {}).get(key)
        
        if translation is None and self.current_language != "en":
            translation = self.translations.get("en", {}).get(key)
            
        if translation is None:
            translation = default_text

        try:
            return translation.format(**fmt_args) if fmt_args and isinstance(translation, str) else translation
        except (KeyError, ValueError) as e: 
            print(f"ComfyModelCleaner I18n Warning: Formatting error for key '{key}' (lang: '{self.current_language}'): {e}. Raw: '{translation}'")
            return translation
        except AttributeError: 
             return str(default_text)

# Global instance
i18n = I18nManager()

def get_t(key, default_text_or_args=None, **kwargs):
    """Shorthand for get_translated_string"""
    return i18n.get_string(key, default_text_or_args, **kwargs) 