import os
import sys
import time
import shutil
import zipfile
import logging
import subprocess
import hashlib
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from win11toast import toast  # notifications Win11 + boutons

from translations import get_translator, set_global_language, show_language_selection_dialog, t

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    TKINTER_AVAILABLE = True
except ImportError:
    TKINTER_AVAILABLE = False

try:
    import winreg  # Windows only
except ImportError:
    winreg = None

import ctypes
from ctypes import wintypes

# =========================
# Config
# =========================

APP_NAME = "Auto Unzip"

DOWNLOADS = Path.home() / "Downloads"

# Installation configuration (can be customized by setup window)
EXTRACT_IN_SUBFOLDER = True
DELETE_ZIP = True
# SECURITY: Restrict incomplete extensions to prevent false positive detection
INCOMPLETE_EXTS = {".crdownload", ".part"}  # Only common Chrome/Firefox download markers

# Installation directory (using Windows API for security)
def _get_local_appdata() -> Path:
    """Get LOCALAPPDATA using Windows API (more secure than env vars)"""
    try:
        path = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        hresult = ctypes.windll.shell32.SHGetFolderPathW(None, 0x001C, None, 0, path)
        if hresult == 0:
            return Path(path.value)
    except Exception as e:
        logging.warning("SHGetFolderPath failed: %s", e)
    return Path.home() / "AppData" / "Local"

def _get_appdata() -> Path:
    """Get APPDATA using Windows API"""
    try:
        path = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        hresult = ctypes.windll.shell32.SHGetFolderPathW(None, 0x0003, None, 0, path)
        if hresult == 0:
            return Path(path.value)
    except Exception as e:
        logging.warning("SHGetFolderPath failed: %s", e)
    return Path.home() / "AppData" / "Roaming"

INSTALL_DIR = _get_local_appdata() / APP_NAME
INSTALLED_EXE = INSTALL_DIR / f"{APP_NAME}.exe"
NEW_EXE = INSTALL_DIR / f"{APP_NAME}.new.exe"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"

# Monitoring folder (customizable during setup)
MONITOR_FOLDER = DOWNLOADS

LOG_DIR = INSTALL_DIR
try:
    LOG_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
except Exception:
    # Fallback on Windows if mode parameter causes issues
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
LOG_FILE = LOG_DIR / "auto_unzip.log"

# Install-dir uninstall shortcut
UNINSTALL_SHORTCUT = INSTALL_DIR / f"Uninstall {APP_NAME}.lnk"

# Start menu shortcuts (per-user)
START_MENU_PROGRAMS = _get_appdata() / r"Microsoft\Windows\Start Menu\Programs"
START_MENU_DIR = START_MENU_PROGRAMS / APP_NAME
START_MENU_SHORTCUT = START_MENU_DIR / f"{APP_NAME}.lnk"
START_MENU_UNINSTALL_SHORTCUT = START_MENU_DIR / f"Uninstall {APP_NAME}.lnk"

# Single instance + shutdown for update/uninstall
MUTEX_NAME = r"Global\Auto Unzip_SingleInstance"
SHUTDOWN_EVENT_NAME = r"Global\Auto Unzip_Shutdown"

# Installation configuration storage
SETUP_CONFIG_FILE = _get_local_appdata() / APP_NAME / "setup_config.json"

# =========================
# Security: Log File Permissions
# =========================

def _set_log_file_permissions():
    """Set restrictive ACL on log file using Windows icacls to prevent information disclosure"""
    try:
        username = os.getenv('USERNAME', 'Owner')
        subprocess.run(
            ["icacls", str(LOG_FILE), "/inheritance:r", "/grant:r", f"{username}:F"],
            capture_output=True,
            check=False,
            timeout=5
        )
    except Exception:
        pass

# =========================
# Logging
# =========================

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# Apply restrictive permissions to log file after creation
try:
    _set_log_file_permissions()
except Exception:
    pass

def log_startup():
    # garantit au moins une trace, même si tout casse tôt
    try:
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            # SECURITY: Don't log full system paths in startup messages
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} START\n")
    except Exception:
        pass

log_startup()

# =========================
# Win32 helpers (mutex + event)
# =========================

kernel32 = ctypes.windll.kernel32
WAIT_OBJECT_0 = 0x00000000

def _win_create_mutex(name: str):
    kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    return kernel32.CreateMutexW(None, False, name)

def _win_get_last_error() -> int:
    return kernel32.GetLastError()

def _win_create_event(name: str):
    kernel32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    return kernel32.CreateEventW(None, True, False, name)

def _win_open_event(name: str):
    kernel32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    kernel32.OpenEventW.restype = wintypes.HANDLE
    EVENT_MODIFY_STATE = 0x0002
    SYNCHRONIZE = 0x00100000
    return kernel32.OpenEventW(EVENT_MODIFY_STATE | SYNCHRONIZE, False, name)

def _win_set_event(h):
    if h:
        kernel32.SetEvent(h)

def _win_wait_for_single_object(h, timeout_ms: int) -> int:
    return kernel32.WaitForSingleObject(h, timeout_ms)

def ensure_single_instance_or_exit():
    """
    Empêche 2 watchers actifs. À appeler UNIQUEMENT pour l'instance installée (watcher).
    """
    _ = _win_create_mutex(MUTEX_NAME)
    ERROR_ALREADY_EXISTS = 183
    if _win_get_last_error() == ERROR_ALREADY_EXISTS:
        # une instance existe déjà
        try:
            notify_info(t("app_name"), t("already_installed"))
        except Exception:
            pass
        sys.exit(0)

def create_shutdown_event():
    return _win_create_event(SHUTDOWN_EVENT_NAME)

def request_running_instance_shutdown():
    """
    Demande à l'ancienne instance (installée) de s'arrêter (update/uninstall).
    """
    h = _win_open_event(SHUTDOWN_EVENT_NAME)
    if not h:
        return
    _win_set_event(h)

def wait_until_unlocked(path: Path, timeout_sec: int = 10) -> bool:
    """
    Wait until file is unlocked (not being written to).
    """
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not path.exists():
            return True
        
        try:
            # Just check if we can open, don't modify file
            with open(path, "rb") as f:
                pass
            return True
        except (PermissionError, FileNotFoundError, OSError):
            time.sleep(0.3)
    
    return False

# =========================
# Security helpers
# =========================

def compute_file_hash(path: Path, algorithm: str = "sha256") -> str:
    """
    Compute hash of file for integrity verification.
    """
    try:
        hasher = hashlib.new(algorithm)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        logging.warning(f"Failed to compute hash for {path}: {e}")
        return ""

def escape_vbs_string(s: str) -> str:
    """
    SECURITY: Safely escape VBScript strings to prevent injection attacks.
    Uses whitelist approach - only allows safe characters.
    This prevents single-quote escaping and other VBScript injection attacks.
    """
    # Define safe characters that won't break VBScript string context
    # Explicitly whitelist to prevent any injection vectors
    safe_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 ._-+/\\:;,!?@[](){}')
    
    # Step 1: Escape backslashes first (must be before quotes)
    s = s.replace("\\", "\\\\")
    
    # Step 2: Remove any character NOT in the safe list (replace with underscore)
    # This prevents single-quote escaping, ampersand, etc.
    s = ''.join(c if c in safe_chars else '_' for c in s)
    
    # Step 3: Finally escape any remaining double quotes
    s = s.replace('"', '""')
    
    return s

# =========================
# Helpers: notifications + icon bundling
# =========================

def resource_path(filename: str) -> Path:
    # SECURITY: Prevent path traversal via filename
    # Only allow simple filenames without directory components
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ValueError(f"Invalid filename: {filename}")
    
    # PyInstaller onefile: data in sys._MEIPASS
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / filename
    return Path(__file__).resolve().parent / filename

APP_ICON_PNG_NAME = "app_icon.png"
INSTALLED_ICON_PNG = INSTALL_DIR / APP_ICON_PNG_NAME

def ensure_installed_icon():
    try:
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        if not INSTALLED_ICON_PNG.exists():
            shutil.copy2(resource_path(APP_ICON_PNG_NAME), INSTALLED_ICON_PNG)
    except FileNotFoundError as e:
        logging.warning("Icon file not found in package: %s", e)
    except Exception as e:
        logging.warning("Failed to install icon file: %s", e)

def _file_uri(p: Path) -> str:
    return "file:///" + str(p).replace("\\", "/")

def notify_info(title: str, message: str):
    ensure_installed_icon()
    try:
        toast(title, message, icon=str(INSTALLED_ICON_PNG), duration="short")
    except Exception:
        pass

def notify_success_extract(zip_name: str):
    ensure_installed_icon()
    folder_uri = _file_uri(DOWNLOADS)
    buttons = [
        {"activationType": "protocol", "arguments": folder_uri, "content": t("open_downloads")},
        t("ignore"),
    ]
    try:
        toast(
            t("zip_extracted_success"),
            f"{t('zip_extracted_message')}: {zip_name}",
            buttons=buttons,
            icon=str(INSTALLED_ICON_PNG),
            duration="short",
        )
    except Exception:
        pass

def notify_error(title: str, message: str):
    ensure_installed_icon()
    # SECURITY: Don't include file paths in notifications
    # Other processes can monitor toast notifications and extract path info
    # Only provide folder button without revealing full path
    folder_uri = _file_uri(DOWNLOADS)
    buttons = [
        {"activationType": "protocol", "arguments": folder_uri, "content": t("open_downloads")},
        t("ignore"),
    ]
    try:
        toast(title, message, buttons=buttons, icon=str(INSTALLED_ICON_PNG), duration="long")
    except Exception:
        pass

# =========================
# Helpers: install / autostart / uninstall / update + shortcuts
# =========================

def _is_frozen_exe() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")

def _current_exe_path() -> Path:
    return Path(sys.executable if _is_frozen_exe() else __file__).resolve()

def _is_running_from_install_dir() -> bool:
    if not _is_frozen_exe():
        return False
    cur = _current_exe_path()
    return str(cur).lower().startswith(str(INSTALL_DIR).lower())

def _ensure_install_dir():
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

def _set_run_at_login(exe_path: Path):
    if winreg is None:
        return
    
    # Validate exe_path exists and is valid
    if not exe_path.exists():
        logging.error("Cannot set autostart: EXE not found: %s", exe_path)
        return
    
    # Validate it's actually our executable
    if not exe_path.name.lower().endswith(".exe"):
        logging.error("Cannot set autostart: Invalid executable: %s", exe_path)
        return
    
    # Verify executable is in installation directory (not attacker-controlled)
    try:
        exe_resolved = exe_path.resolve()
        install_resolved = INSTALL_DIR.resolve()
        exe_str = str(exe_resolved).lower()
        install_str = str(install_resolved).lower()
        
        if not exe_str.startswith(install_str):
            logging.error("Cannot set autostart: EXE outside installation directory: %s", exe_path)
            return
    except Exception as e:
        logging.error("Cannot validate autostart path: %s", e)
        return
    
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
    except Exception as e:
        logging.exception(f"Failed to set autostart: {e}")

def _remove_run_at_login():
    if winreg is None:
        return
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_NAME)
    except (FileNotFoundError, OSError):
        pass

def _launch_detached(exe_path: Path, args=None):
    """Launch executable detached with argument validation"""
    # Validate exe_path
    if not exe_path.exists():
        logging.error("Executable not found: %s", exe_path)
        return
    
    # Verify exe is in expected location
    try:
        exe_resolved = exe_path.resolve()
        install_resolved = INSTALL_DIR.resolve()
        if not str(exe_resolved).lower().startswith(str(install_resolved).lower()):
            logging.error("Executable outside installation directory: %s", exe_path)
            return
    except Exception as e:
        logging.error("Cannot validate executable path: %s", e)
        return
    
    if not exe_path.name.lower().endswith(".exe"):
        logging.error("Invalid executable: %s", exe_path)
        return
    
    # Validate and sanitize args
    args = args or []
    if not isinstance(args, list):
        logging.error("Arguments must be a list")
        return
    
    # Validate each argument - only allow specific safe flags
    allowed_flags = {"--uninstall", "--install"}
    for arg in args:
        if not isinstance(arg, str):
            logging.error("Argument must be string: %s", arg)
            return
        if len(arg) > 32768:  # Windows command line limit
            logging.error("Argument too long: %d bytes", len(arg))
            return
        if arg not in allowed_flags:
            logging.error("Argument not in whitelist: %s", arg)
            return
    
    try:
        creationflags = 0x00000008 | 0x00000200  # DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([str(exe_path), *args], close_fds=True, creationflags=creationflags)
    except Exception as e:
        logging.exception("Failed to launch detached process: %s", e)

def _make_shortcut_vbs(path_lnk: Path, target: Path, args: str = "", workdir=None) -> bool:
    """
    Creates a .lnk shortcut via VBScript (cscript). Secure implementation.
    """
    try:
        # Validate inputs
        if not target.exists():
            logging.error("Shortcut target does not exist: %s", target)
            return False
        if not target.name.lower().endswith(".exe"):
            logging.error("Shortcut target is not an executable: %s", target)
            return False
        
        path_lnk.parent.mkdir(parents=True, exist_ok=True)
        wd = str(workdir) if workdir else str(target.parent)

        # Escape paths to prevent VBScript injection
        safe_lnk = escape_vbs_string(str(path_lnk))
        safe_target = escape_vbs_string(str(target))
        safe_args = escape_vbs_string(args)
        safe_wd = escape_vbs_string(wd)

        vbs = f'''
Set oWS = CreateObject("WScript.Shell")
sLinkFile = "{safe_lnk}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{safe_target}"
oLink.Arguments = "{safe_args}"
oLink.WorkingDirectory = "{safe_wd}"
oLink.WindowStyle = 7
oLink.IconLocation = "{safe_target},0"
oLink.Save
'''

        # Write temporary VBS file in INSTALL_DIR with restricted permissions
        tmp_vbs = INSTALL_DIR / "_mkshortcut.vbs"
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        tmp_vbs.write_text(vbs, encoding="utf-8")
        
        # Set restrictive permissions on temporary file
        try:
            subprocess.run(
                ["icacls", str(tmp_vbs), "/inheritance:r", "/grant:r", f"{os.getenv('USERNAME', 'Owner')}:F"],
                capture_output=True,
                check=False,
                timeout=5
            )
        except Exception:
            pass

        try:
            r = subprocess.run(
                ["cscript.exe", "//nologo", str(tmp_vbs)],
                capture_output=True,
                text=True,
                check=False,
                creationflags=0x00000008,
            )

            if path_lnk.exists():
                logging.info("Shortcut OK (VBS): %s", path_lnk)
                return True

            logging.warning(
                "Shortcut FAILED (VBS no file). rc=%s",
                r.returncode
            )
            return False
        finally:
            # Ensure temp file is cleaned up securely with retries
            max_attempts = 5
            for attempt in range(max_attempts):
                try:
                    tmp_vbs.unlink()
                    logging.debug("Temporary VBS file cleaned up after %d attempt(s)", attempt + 1)
                    break
                except FileNotFoundError:
                    # File already deleted - success
                    break
                except Exception as cleanup_error:
                    if attempt < max_attempts - 1:
                        time.sleep(0.2)  # Slightly longer wait between retries
                    else:
                        # Final attempt failed - log but don't crash
                        logging.warning("Failed to clean up temporary VBS file after %d attempts: %s", max_attempts, cleanup_error)

    except Exception as e:
        logging.exception("Shortcut VBS exception for %s: %s", path_lnk, e)
        return False

def _write_cmd_launcher(path_cmd: Path, exe: Path, args: str = ""):
    try:
        path_cmd.parent.mkdir(parents=True, exist_ok=True)
        # Validate exe path to prevent injection
        if not exe.exists():
            logging.error("CMD launcher: executable does not exist: %s", exe)
            return
        if not exe.name.lower().endswith(".exe"):
            logging.error("CMD launcher: invalid executable: %s", exe)
            return
        # Properly quote args for safety
        safe_args = f'"{args}"' if args else ""
        line = f'@echo off\r\nstart "" "{exe}" {safe_args}\r\n'
        path_cmd.write_text(line, encoding="utf-8")
        logging.info("CMD launcher OK: %s", path_cmd)
    except Exception as e:
        logging.exception("CMD launcher failed for %s: %s", path_cmd, e)

def ensure_shortcuts(exe: Path):
    # uninstall dans le dossier d'installation
    ok1 = _make_shortcut_vbs(UNINSTALL_SHORTCUT, exe, args="--uninstall", workdir=INSTALL_DIR)
    if not ok1:
        _write_cmd_launcher(INSTALL_DIR / f"Uninstall {APP_NAME}.cmd", exe, args="--uninstall")

    # menu démarrer
    ok2 = _make_shortcut_vbs(START_MENU_SHORTCUT, exe, args="", workdir=INSTALL_DIR)
    ok3 = _make_shortcut_vbs(START_MENU_UNINSTALL_SHORTCUT, exe, args="--uninstall", workdir=INSTALL_DIR)

    if not ok2:
        _write_cmd_launcher(START_MENU_DIR / f"{APP_NAME}.cmd", exe, args="")
    if not ok3:
        _write_cmd_launcher(START_MENU_DIR / f"Uninstall {APP_NAME}.cmd", exe, args="--uninstall")


def remove_start_menu_shortcuts():
    try:
        if START_MENU_SHORTCUT.exists():
            START_MENU_SHORTCUT.unlink()
        if START_MENU_UNINSTALL_SHORTCUT.exists():
            START_MENU_UNINSTALL_SHORTCUT.unlink()
        if START_MENU_DIR.exists():
            try:
                shutil.rmtree(START_MENU_DIR)  # Recursive delete
            except Exception as e:
                logging.warning("Failed to remove start menu dir: %s", e)
    except Exception as e:
        logging.exception("Failed to remove start menu shortcuts: %s", e)

def _schedule_replace_installed():
    """
    Remplacement différé (si l’exe installé est verrouillé).
    Uses safe subprocess execution without shell=True.
    """
    try:
        # Create batch file with safe commands instead of passing through cmd shell
        batch_file = INSTALL_DIR / "_update_replace.bat"
        batch_content = f"""@echo off
setlocal disabledelayedexpansion
timeout /t 3 /nobreak >nul 2>&1
if exist "{INSTALLED_EXE}" (
    move /y "{INSTALLED_EXE}" "{INSTALLED_EXE}.bak" >nul 2>&1
)
move /y "{NEW_EXE}" "{INSTALLED_EXE}" >nul 2>&1
exit /b 0
"""
        batch_file.write_text(batch_content, encoding="utf-8")
        
        # Execute batch file directly (no shell injection)
        subprocess.Popen(
            [str(batch_file)],
            creationflags=0x00000008,
            close_fds=True
        )
    except Exception as e:
        logging.exception(f"Failed to schedule replacement: {e}")

def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except Exception:
        return 0.0

def is_installed() -> bool:
    return INSTALLED_EXE.exists()

def ensure_autostart_and_shortcuts():
    _ensure_install_dir()
    exe = INSTALLED_EXE if is_installed() else _current_exe_path()
    _set_run_at_login(exe)
    ensure_shortcuts(exe)

def install(force: bool = False, show_already_installed_notif: bool = True) -> bool:
    if not _is_frozen_exe():
        notify_error(t("app_name"), t("install_requires_exe"))
        return False

    cur = _current_exe_path()
    _ensure_install_dir()

    if is_installed() and not force:
        if show_already_installed_notif:
            notify_info(t("app_name"), t("already_installed"))
        ensure_autostart_and_shortcuts()
        return True

    try:
        # Read source file into memory to avoid TOCTOU race condition
        try:
            with open(cur, "rb") as f:
                exe_content = f.read()
        except FileNotFoundError:
            logging.error("Source executable not found: %s", cur)
            notify_error(t("app_name"), t("install_requires_exe"))
            return False
        except PermissionError:
            logging.error("Permission denied reading source executable: %s", cur)
            notify_error(t("app_name"), "Cannot read source executable")
            return False
        
        if not exe_content:
            logging.error("Source executable is empty: %s", cur)
            return False
        
        # Write to destination
        try:
            INSTALLED_EXE.write_bytes(exe_content)
        except Exception as e:
            logging.error("Failed to write executable: %s", e)
            notify_error(t("install_error_detail"), str(e))
            return False
        
        # Verify the copy was successful
        try:
            with open(INSTALLED_EXE, "rb") as f:
                installed_content = f.read()
            
            if len(installed_content) != len(exe_content) or installed_content != exe_content:
                logging.warning("File content mismatch after copy - possible corruption")
                INSTALLED_EXE.unlink()
                raise RuntimeError("Installation verification failed - file content mismatch")
        except Exception as e:
            logging.exception("Failed to verify installation: %s", e)
            return False
        
        ensure_installed_icon()
        ensure_autostart_and_shortcuts()
        notify_info(t("app_name"), t("installed_success"))
        return True
    except Exception as e:
        logging.exception("Install failed: %s", e)
        notify_error(t("install_error_detail"), str(e))
        return False

def try_update_if_newer(setup_exe: Path) -> str:
    if not is_installed():
        return "no_update"

    installed_m = _mtime(INSTALLED_EXE)
    setup_m = _mtime(setup_exe)

    if setup_m <= installed_m + 1.0:
        return "no_update"

    notify_info(t("app_name"), t("update_in_progress"))

    request_running_instance_shutdown()
    # SECURITY: Check if file unlock succeeded within timeout
    if not wait_until_unlocked(INSTALLED_EXE, timeout_sec=10):
        logging.warning("Executable still locked after timeout - update failed")
        notify_error(t("update_error"), "Executable is locked")
        return "no_update"

    try:
        # Verify source executable
        if not setup_exe.exists():
            raise FileNotFoundError(f"Setup executable not found: {setup_exe}")
        
        # Copy and verify
        shutil.copy2(setup_exe, INSTALLED_EXE)
        
        # Verify integrity
        src_hash = compute_file_hash(setup_exe)
        if src_hash:
            dst_hash = compute_file_hash(INSTALLED_EXE)
            if src_hash != dst_hash:
                logging.warning("Update file hash mismatch - possible corruption")
                raise RuntimeError("Update verification failed - file hash mismatch")
        
        ensure_autostart_and_shortcuts()
        notify_info(t("app_name"), t("update_installed"))
        return "updated"
    except PermissionError:
        try:
            shutil.copy2(setup_exe, NEW_EXE)
            _schedule_replace_installed()
            ensure_autostart_and_shortcuts()
            notify_info(t("app_name"), t("update_scheduled"))
            return "scheduled"
        except Exception as e:
            logging.exception("Update schedule failed: %s", e)
            notify_error(t("update_error"), str(e))
            return "no_update"
    except Exception as e:
        logging.exception("Update failed: %s", e)
        notify_error(t("update_error"), str(e))
        return "no_update"

def _schedule_delete_install_dir():
    # SECURITY: Use batch file with disabled delayed expansion to prevent injection
    # Create temporary batch file that safely deletes the installation directory
    try:
        batch_file = INSTALL_DIR / "_uninstall_cleanup.bat"
        # Use disabledelayedexpansion to prevent any code execution via special chars
        batch_content = f"""@echo off
setlocal disabledelayedexpansion
timeout /t 3 /nobreak > nul 2>&1
rmdir /s /q "{INSTALL_DIR}" >nul 2>&1
exit /b 0
"""
        batch_file.write_text(batch_content, encoding="utf-8")
        
        # Execute the batch file directly instead of passing through cmd
        subprocess.Popen(
            [str(batch_file)],
            creationflags=0x00000008,
            close_fds=True
        )
    except Exception as e:
        logging.exception("Failed to schedule install dir deletion: %s", e)

def uninstall():
    notify_info(t("app_name"), t("uninstalling"))

    request_running_instance_shutdown()
    wait_until_unlocked(INSTALLED_EXE, timeout_sec=10)

    _remove_run_at_login()
    remove_start_menu_shortcuts()

    if _is_running_from_install_dir():
        _schedule_delete_install_dir()
        return

    try:
        if INSTALL_DIR.exists():
            shutil.rmtree(INSTALL_DIR, ignore_errors=True)
    except Exception:
        pass

# =========================
# Zip logic
# =========================

def is_zip_ready(zip_path: Path, stable_seconds=2.0, timeout=180.0) -> bool:
    start = time.time()
    last_size = -1
    last_change = time.time()

    while time.time() - start < timeout:
        if not zip_path.exists():
            time.sleep(0.2)
            continue

        for ext in INCOMPLETE_EXTS:
            if zip_path.with_suffix(zip_path.suffix + ext).exists():
                time.sleep(0.5)
                break
        else:
            size = zip_path.stat().st_size
            if size != last_size:
                last_size = size
                last_change = time.time()
            else:
                if time.time() - last_change >= stable_seconds:
                    return True
            time.sleep(0.2)

    return False

def is_within_directory(base: Path, target: Path) -> bool:
    try:
        base = base.resolve()
        target = target.resolve()
        # Ensure target is truly under base using relative_to
        # This is safer than string comparison
        try:
            target.relative_to(base)
            return True
        except ValueError:
            # target is not relative to base (path traversal detected)
            return False
    except (OSError, RuntimeError) as e:
        logging.error("Path resolution failed (possible symlink/junction attack): %s", e)
        return False
    except Exception as e:
        logging.error("Unexpected error in path validation: %s", e)
        return False

# ZIP bomb protection constants (defined at module level for consistency)
MAX_EXTRACT_SIZE = 5 * 1024 * 1024 * 1024  # 5GB
MAX_FILES = 10000
MAX_NAME_LENGTH = 260  # Windows MAX_PATH
MAX_ZIP_FILE_SIZE = 10 * 1024 * 1024 * 1024  # 10GB - prevent processing suspiciously large ZIPs

def safe_extract(zip_path: Path, dest_dir: Path) -> None:
    """Safely extract ZIP with comprehensive security checks"""
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    # SECURITY: Reject suspiciously large ZIP files before processing
    try:
        zip_size = zip_path.stat().st_size
        if zip_size > MAX_ZIP_FILE_SIZE:
            raise ValueError(f"ZIP file exceeds maximum size ({zip_size} > {MAX_ZIP_FILE_SIZE})")
    except OSError as e:
        raise RuntimeError(f"Cannot stat ZIP file: {e}")

    with zipfile.ZipFile(zip_path) as z:
        total_size = 0
        
        for member in z.infolist():
            # Security check 1: Reject null bytes
            if '\x00' in member.filename or '\0' in member.filename:
                raise RuntimeError("Extraction blocked (null byte in filename)")
            
            # Security check 2: Reject absolute paths
            if member.filename.startswith("/") or member.filename.startswith("\\"):
                raise RuntimeError("Extraction blocked (absolute path detected)")
            
            # Security check 3: Reject parent directory traversal
            if ".." in member.filename:
                raise RuntimeError("Extraction blocked (directory traversal detected)")
            
            # Security check 4: Filename length
            if len(member.filename) > MAX_NAME_LENGTH:
                raise ValueError(f"Filename exceeds maximum length ({len(member.filename)} > {MAX_NAME_LENGTH})")
            
            # Security check 5: Individual file size check for negative or huge files
            if member.file_size < 0:
                raise ValueError(f"Invalid file size: {member.file_size}")
            
            if member.file_size > MAX_EXTRACT_SIZE:
                raise ValueError(f"File size exceeds maximum ({member.file_size} > {MAX_EXTRACT_SIZE})")
            
            # Security check 6: Total extraction size (zip bomb protection)
            total_size += member.file_size
            if total_size < 0:  # Check for integer overflow
                raise ValueError("Archive size calculation overflow")
            
            if total_size > MAX_EXTRACT_SIZE:
                raise ValueError(f"Archive exceeds maximum decompressed size ({total_size} > {MAX_EXTRACT_SIZE})")
            
            # Security check 7: Path traversal via symlink/junction
            out_path = dest_dir / member.filename
            if not is_within_directory(dest_dir, out_path):
                raise RuntimeError("Extraction blocked (path traversal or symlink attack detected)")
        
        # All checks passed
        if len(z.infolist()) > MAX_FILES:
            raise ValueError(f"Archive contains too many files ({len(z.infolist())} > {MAX_FILES})")
        
        z.extractall(dest_dir)

def robust_delete(path: Path):
    """Safely delete a file with retry logic and security validation"""
    try:
        if not path.exists():
            return
        
        # SECURITY: Check for symlink/junction BEFORE any path operations
        # This prevents TOCTOU where symlink could be created between checks
        if path.is_symlink():
            logging.warning("Refusing to delete symlink: %s", path)
            return
        
        # Validate path is within expected monitored locations for safety
        path_resolved = path.resolve()
        downloads_resolved = DOWNLOADS.resolve()
        install_resolved = INSTALL_DIR.resolve()
        
        is_in_downloads = str(path_resolved).lower().startswith(str(downloads_resolved).lower())
        is_in_install = str(path_resolved).lower().startswith(str(install_resolved).lower())
        
        if not (is_in_downloads or is_in_install):
            logging.warning("Refusing to delete file outside monitored locations: %s", path)
            return
    except Exception:
        logging.warning("Could not validate path for deletion: %s", path)
        return
    
    for _ in range(10):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            time.sleep(0.5)

class ZipHandler(FileSystemEventHandler):
    def __init__(self, max_recent=1000):
        self._recent = {}
        self.max_recent = max_recent

    def on_created(self, event):
        if event.is_directory:
            return
        self._maybe_process(Path(event.src_path))

    def on_moved(self, event):
        if event.is_directory:
            return
        self._maybe_process(Path(event.dest_path))

    def _cleanup_old_entries(self, now: float):
        """Remove entries older than 1 hour to prevent memory leak"""
        cutoff = now - 3600
        self._recent = {p: t for p, t in self._recent.items() if t > cutoff}
        
        # Limit dictionary size
        if len(self._recent) > self.max_recent:
            oldest = min(self._recent.values())
            self._recent = {p: t for p, t in self._recent.items() if t > oldest}

    def _maybe_process(self, path: Path):
        if path.suffix.lower() != ".zip":
            return
        
        # SECURITY: Reject symlinks to prevent processing wrong files
        if path.is_symlink():
            logging.warning("Ignoring symlink ZIP file: %s", path)
            return

        now = time.time()
        
        # Clean up old entries periodically
        if len(self._recent) > 100:  # Cleanup when reaching 100 entries
            self._cleanup_old_entries(now)
        
        if path in self._recent and (now - self._recent[path]) < 5:
            return
        self._recent[path] = now

        logging.info("Zip detected: %s", path.name)

        try:
            if not is_zip_ready(path):
                raise TimeoutError(f"{t('zip_error_locked')}: {path.name}")

            extract_dir = path.parent / path.stem if EXTRACT_IN_SUBFOLDER else path.parent
            
            # Validate extraction directory is under Downloads
            try:
                extract_dir_resolved = extract_dir.resolve()
                downloads_resolved = DOWNLOADS.resolve()
                
                if not str(extract_dir_resolved).lower().startswith(str(downloads_resolved).lower()):
                    logging.error("Extraction directory outside Downloads: %s", extract_dir.name)
                    notify_error(t("zip_error"), t("zip_error_generic_message"))
                    return
            except Exception as e:
                logging.error("Could not validate extraction directory: %s", e)
                notify_error(t("zip_error"), t("zip_error_generic_message"))
                return
            
            logging.info("Extraction directory: %s", extract_dir.name)

            try:
                safe_extract(path, extract_dir)
            except Exception as e:
                # SECURITY: Clean up partial extraction on failure
                try:
                    if extract_dir.exists() and extract_dir.parent == DOWNLOADS:
                        logging.info("Removing partial extraction: %s", extract_dir)
                        shutil.rmtree(extract_dir, ignore_errors=True)
                except Exception:
                    pass
                raise e
            
            logging.info("Extraction OK: %s", path.name)

            if DELETE_ZIP:
                robust_delete(path)
                logging.info("Archive deleted: %s", path.name)

            notify_success_extract(path.name)

        except zipfile.BadZipFile:
            logging.exception("Invalid ZIP file: %s", path.name)
            notify_error(t("zip_invalid"), t("zip_invalid_message"))
        except Exception as e:
            # Log detailed error for debugging, but show generic message to user
            logging.exception("ZIP processing failed for %s: %s", path.name, e)
            notify_error(t("zip_error"), t("zip_error_generic_message"))

# =========================
# Main
# =========================

def run_watcher():
    if not MONITOR_FOLDER.exists():
        msg = f"{t('watch_error_folder_not_found')}: {MONITOR_FOLDER.name}"
        logging.error(msg)
        notify_error(t("watch_error_config"), msg)
        return

    # ✅ Mutex uniquement pour l'instance installée (watcher)
    if _is_running_from_install_dir():
        ensure_single_instance_or_exit()

    shutdown_event = create_shutdown_event()

    handler = ZipHandler()
    observer = Observer()
    observer.schedule(handler, str(MONITOR_FOLDER), recursive=False)
    observer.start()

    logging.info(t("monitoring_started", MONITOR_FOLDER))
    notify_info(t("app_name"), t("watch_started"))

    restart_count = 0
    max_restarts = 5  # SECURITY: Prevent infinite restart loops
    
    try:
        while True:
            res = _win_wait_for_single_object(shutdown_event, 1000)
            if res == WAIT_OBJECT_0:
                logging.info(t("shutdown_requested"))
                break
            
            # SECURITY: Check if observer is still alive
            if not observer.is_alive():
                restart_count += 1
                if restart_count > max_restarts:
                    logging.error("Observer crashed %d times - giving up to prevent infinite loop", restart_count)
                    break
                
                logging.warning("Observer thread died (restart %d/%d) - attempting restart", restart_count, max_restarts)
                try:
                    observer.stop()
                    observer.join(timeout=2)
                except Exception:
                    pass
                
                # SECURITY: Wait before restart to avoid tight loop
                time.sleep(1.0)
                
                # Restart observer
                handler = ZipHandler()
                observer = Observer()
                observer.schedule(handler, str(MONITOR_FOLDER), recursive=False)
                observer.start()
                logging.info("Observer restarted successfully")
    except Exception as e:
        logging.exception("Watcher error: %s", e)
    finally:
        try:
            observer.stop()
            observer.join(timeout=5)
        except Exception:
            pass

def main():
    # SECURITY: Validate command line arguments - whitelist approach only
    arg = (sys.argv[1].lower().strip() if len(sys.argv) > 1 else "")
    
    # Only allow specific known arguments - whitelist approach for maximum security
    allowed_args = {"--uninstall", "/uninstall"}  # Canonical forms only
    
    if arg:
        if arg not in allowed_args:
            # Unknown argument - log and exit silently (don't provide error detail that might be exploited)
            logging.error("Invalid command line argument rejected: argument length=%d", len(arg))
            sys.exit(1)
        
        if arg in allowed_args:
            uninstall()
            return

    # Normal mode: just run the watcher
    # Installation is handled by Inno Setup installer
    if _is_running_from_install_dir():
        ensure_autostart_and_shortcuts()
    
    run_watcher()

if __name__ == "__main__":
    main()
