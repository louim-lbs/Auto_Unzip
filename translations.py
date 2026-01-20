"""
Multi-language support for Auto Unzip
Supports: French (fr), English (en)
"""

import json
import logging
import locale
from pathlib import Path
from typing import Optional

# Language definitions
LANGUAGES = {
    "en": "English",
    "fr": "Français",
}

# Default language
DEFAULT_LANGUAGE = "en"

# Get the directory where this file is located
TRANSLATIONS_DIR = Path(__file__).resolve().parent
LANGUAGE_CONFIG_FILE = Path(__file__).resolve().parent / "language_config.json"

# Translations dictionary
TRANSLATIONS = {
    "en": {
        # General
        "app_name": "Auto Unzip",
        "already_installed": "Already installed.",
        "installation_error": "Installation error",
        "uninstallation_error": "Uninstallation error",
        
        # Installation messages
        "select_language": "Select Language",
        "choose_language_message": "Please choose your preferred language",
        "installed_success": "Installed, will start automatically.",
        "install_requires_exe": "Install mode requires a packaged executable (.exe).",
        "install_error_detail": "Auto Unzip: installation error",
        
        # Uninstallation messages
        "uninstalling": "Uninstalling...",
        "uninstall_requires_exe": "Uninstall mode requires a packaged executable (.exe).",
        
        # Update messages
        "update_in_progress": "Updating...",
        "update_installed": "Update installed.",
        "update_scheduled": "Update scheduled (applied as soon as possible).",
        "update_error": "Auto Unzip: update error",
        "no_update_available": "Already installed, no update available.",
        
        # Watcher messages
        "watch_started": "Monitoring started on Downloads folder.",
        "watch_error_config": "Auto Unzip: configuration",
        "watch_error_folder_not_found": "Folder not found",
        
        # Zip extraction messages
        "zip_detected": "Zip file detected",
        "zip_extracted_success": "Auto Unzip: success",
        "zip_extracted_message": "Extracted",
        "zip_open_downloads": "Open Downloads",
        "zip_ignore": "Ignore",
        "zip_invalid": "Auto Unzip: ZIP error",
        "zip_invalid_message": "Invalid/corrupted ZIP",
        "zip_error": "Auto Unzip: error",
        "zip_error_locked": "ZIP not ready (timeout)",
        "zip_error_extraction": "Error on",
        
        # Buttons
        "open_downloads": "Open Downloads",
        "open_log": "Open log",
        "ignore": "Ignore",
        
        # Monitoring
        "monitoring_started": "Monitoring started on %s",
        "shutdown_requested": "Shutdown requested (update/uninstall).",
    },
    "fr": {
        # General
        "app_name": "Auto Unzip",
        "already_installed": "Déjà installé.",
        "installation_error": "Erreur d'installation",
        "uninstallation_error": "Erreur de désinstallation",
        
        # Installation messages
        "select_language": "Sélectionner la langue",
        "choose_language_message": "Veuillez choisir votre langue préférée",
        "installed_success": "Installé, démarrera automatiquement.",
        "install_requires_exe": "Le mode install nécessite l'exécutable (.exe) packagé.",
        "install_error_detail": "Auto Unzip : erreur d'installation",
        
        # Uninstallation messages
        "uninstalling": "Désinstallation en cours...",
        "uninstall_requires_exe": "Le mode uninstall nécessite l'exécutable (.exe) packagé.",
        
        # Update messages
        "update_in_progress": "Mise à jour en cours...",
        "update_installed": "Mise à jour installée.",
        "update_scheduled": "Mise à jour planifiée (appliquée dès que possible).",
        "update_error": "Auto Unzip : erreur de mise à jour",
        "no_update_available": "Déjà installé, pas de mise à jour disponible.",
        
        # Watcher messages
        "watch_started": "Surveillance démarrée sur le dossier Téléchargements.",
        "watch_error_config": "Auto Unzip : configuration",
        "watch_error_folder_not_found": "Dossier introuvable",
        
        # Zip extraction messages
        "zip_detected": "Zip détecté",
        "zip_extracted_success": "Auto Unzip : succès",
        "zip_extracted_message": "Extrait",
        "zip_open_downloads": "Ouvrir Téléchargements",
        "zip_ignore": "Ignorer",
        "zip_invalid": "Auto Unzip : erreur ZIP",
        "zip_invalid_message": "Zip invalide/corrompu",
        "zip_error": "Auto Unzip : erreur",
        "zip_error_locked": "Zip pas prêt (timeout)",
        "zip_error_extraction": "Erreur sur",
        
        # Buttons
        "open_downloads": "Ouvrir Téléchargements",
        "open_log": "Ouvrir le log",
        "ignore": "Ignorer",
        
        # Monitoring
        "monitoring_started": "Surveillance démarrée sur %s",
        "shutdown_requested": "Arrêt demandé (mise à jour / désinstallation).",
    },
}


class Translator:
    """Handles translations with fallback to default language"""
    
    def __init__(self, language: Optional[str] = None):
        self.language = language or self._load_saved_language() or self._detect_system_language()
        if self.language not in TRANSLATIONS:
            self.language = DEFAULT_LANGUAGE
    
    @staticmethod
    def _detect_system_language() -> str:
        """
        Detect Windows system language and return appropriate language code.
        Maps Windows locale to supported languages.
        """
        try:
            # Get system locale
            system_locale = locale.getdefaultlocale()[0]  # e.g., 'fr_FR', 'en_US'
            
            if system_locale:
                # Extract language code (first 2 characters)
                lang_code = system_locale.split('_')[0].lower()
                
                # Check if we support this language
                if lang_code in LANGUAGES:
                    logging.info(f"Detected system language: {lang_code}")
                    return lang_code
        except Exception as e:
            logging.debug(f"Failed to detect system language: {e}")
        
        return DEFAULT_LANGUAGE
    
    @staticmethod
    def _load_saved_language() -> Optional[str]:
        """Load saved language preference from config file"""
        try:
            if LANGUAGE_CONFIG_FILE.exists():
                with open(LANGUAGE_CONFIG_FILE, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    return config.get("language")
        except Exception as e:
            logging.debug(f"Failed to load language config: {e}")
        return None
    
    def save_language(self):
        """Save language preference to config file"""
        try:
            config = {"language": self.language}
            with open(LANGUAGE_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            logging.info(f"Language preference saved: {self.language}")
        except Exception as e:
            logging.error(f"Failed to save language config: {e}")
    
    def get(self, key: str, *args) -> str:
        """Get translated string with optional formatting"""
        if key not in TRANSLATIONS[self.language]:
            # Fallback to English if key not found
            text = TRANSLATIONS[DEFAULT_LANGUAGE].get(key, f"[{key}]")
            logging.warning(f"Missing translation key '{key}' for language {self.language}")
        else:
            text = TRANSLATIONS[self.language][key]
        
        # Support formatting with arguments
        if args:
            try:
                return text % args
            except (TypeError, ValueError):
                logging.warning(f"Format error for key '{key}': {args}")
                return text
        return text
    
    def set_language(self, language: str):
        """Set the current language"""
        if language in TRANSLATIONS:
            self.language = language
            self.save_language()
            logging.info(f"Language changed to: {language}")
        else:
            logging.warning(f"Unknown language: {language}")


# Global translator instance
_translator: Optional[Translator] = None


def get_translator() -> Translator:
    """Get the global translator instance"""
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator


def set_global_language(language: str):
    """Set the global language"""
    translator = get_translator()
    translator.set_language(language)


def t(key: str, *args) -> str:
    """Shorthand for get_translator().get()"""
    return get_translator().get(key, *args)


def show_language_selection_dialog() -> Optional[str]:
    """
    Show a dialog for the user to select their preferred language.
    Returns the selected language code or None if cancelled.
    """
    try:
        import tkinter as tk
        from tkinter import simpledialog
        
        root = tk.Tk()
        root.withdraw()  # Hide the root window
        root.attributes('-topmost', True)  # Bring to front
        
        # Create a simple dialog
        dialog = tk.Toplevel(root)
        dialog.title("Select Language / Sélectionner la langue")
        dialog.attributes('-topmost', True)
        
        selected_lang = tk.StringVar(value="en")
        
        tk.Label(dialog, text="Choose your language:", font=("Arial", 12, "bold")).pack(pady=10)
        tk.Label(dialog, text="Choisissez votre langue :", font=("Arial", 10)).pack()
        
        tk.Radiobutton(dialog, text="English", variable=selected_lang, value="en", font=("Arial", 11)).pack(anchor=tk.W, padx=20, pady=5)
        tk.Radiobutton(dialog, text="Français", variable=selected_lang, value="fr", font=("Arial", 11)).pack(anchor=tk.W, padx=20, pady=5)
        
        def ok_clicked():
            dialog.destroy()
            root.destroy()
        
        tk.Button(dialog, text="OK", command=ok_clicked, font=("Arial", 10), width=15).pack(pady=15)
        
        dialog.transient(root)
        dialog.focus()
        root.mainloop()
        
        return selected_lang.get()
    
    except ImportError:
        logging.warning("tkinter not available, cannot show language selection dialog")
        return None
    except Exception as e:
        logging.error(f"Error showing language selection dialog: {e}")
        return None
