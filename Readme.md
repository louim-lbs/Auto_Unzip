# Auto Unzip

**Automatically extract ZIP files from your Downloads folder**

![License](https://img.shields.io/badge/license-AGPL--3.0%2BCommons-blue.svg)
![Python](https://img.shields.io/badge/python-3.8+-green.svg)
![Windows](https://img.shields.io/badge/platform-Windows-lightblue.svg)

## Overview

Auto Unzip is a lightweight Windows utility that automatically monitors your Downloads folder and extracts ZIP files as soon as they finish downloading. No more manual extraction—just download and let Auto Unzip handle the rest!

## Features

✨ **Automatic Extraction**
- Monitors Downloads folder in real-time
- Extracts ZIP files automatically when download completes
- No user intervention required

🌍 **Multi-Language Support**
- Automatic language detection based on Windows settings
- Supports English and French
- Language preference persisted across sessions

🔒 **Smart & Safe**
- Validates ZIP file integrity before extraction
- Prevents path traversal attacks
- Extracts to subfolders by default (prevents file conflicts)
- Keeps comprehensive logs of all operations

🚀 **Easy Installation**
- Simple one-click installer
- Automatic startup on Windows boot
- Minimal system overhead
- Start Menu shortcuts included

⚙️ **Configurable**
- Option to delete ZIP files after extraction
- Customizable extraction location (subfolder or same directory)
- System tray notifications with action buttons

## Installation

### Method 1: Direct Installation
1. Download `AutoUnzip-Setup.exe`
2. Double-click to install
3. The app will auto-start just after installation
4. You'll see a notification when installation is complete

### Method 2: Command Line
```bash
AutoUnzip-Setup.exe --install
```

## Usage

### After Installation
The application runs automatically in the background:
- Monitors your Downloads folder 24/7
- When a ZIP is downloaded, it extracts automatically
- You'll receive a notification showing what was extracted

### Notifications
- **Success**: Shows what was extracted with quick access buttons
- **Errors**: Detailed error messages with log file access

## Uninstall

### Method 1: Start Menu
1. Open Start Menu
2. Find "Auto Unzip"
3. Click "Uninstall Auto Unzip"

### Method 2: Command Line
```bash
AutoUnzip-Setup.exe --uninstall
```

## Configuration (in source)

### File Settings

Edit the settings in `Auto_unzip.py`:

```python
# Extract into subfolders (recommended)
EXTRACT_IN_SUBFOLDER = True

# Delete ZIP after successful extraction
DELETE_ZIP = True

# File extensions to ignore (incomplete downloads)
INCOMPLETE_EXTS = {".crdownload", ".part", ".download"}
```

### Language Preference

Language is automatically detected from your Windows settings:
- **Windows in French** → App runs in French
- **Windows in English** → App runs in English

To manually override, edit `language_config.json`:
```json
{
  "language": "fr"
}
```

Location: `%LOCALAPPDATA%\Auto Unzip\language_config.json`

## Logs

All operations are logged to: `%LOCALAPPDATA%\Auto Unzip\auto_unzip.log`

View the log to:
- Track extraction history
- Debug issues
- Monitor application activity

## Requirements

- Windows 7 or later
- 10 MB disk space
- .NET Framework (usually pre-installed)

## Troubleshooting

### Extraction failed - "ZIP invalid/corrupted"
**Solution**:
- Re-download the ZIP file
- Try extracting manually to confirm it's valid
- Check the log for details

## Performance Impact

- **Memory**: ~15 MB when running
- **CPU**: Minimal (only active when monitoring)
- **Disk**: <20 MB for installation

## Security Features

- ✅ **Path Traversal Protection**: Prevents extraction outside target folder
- ✅ **Integrity Checks**: Validates ZIP files before extraction
- ✅ **Logging**: Detailed logs for auditing and troubleshooting
- ✅ **Minimal Permissions**: Runs with least privileges necessary
- ✅ **Open Source**: Code available for review on GitHub
- ✅ **No Data Collection**: Respects user privacy, no telemetry

## System Integration

- **Registry**: Single entry in HKEY_CURRENT_USER Run key for autostart
- **Start Menu**: Shortcuts in `Start Menu\Programs\Auto Unzip\`
- **Install Dir**: `Program Files\Auto Unzip\`
- **Log Files**: Auto-rotated to prevent disk space issues

## Known Limitations

- Only monitors Downloads folder (not custom folders)
- Only supports ZIP format (not RAR, 7Z, etc.)
- Windows only (not available for Mac/Linux)

## Building from Source

### Prerequisites
```bash
pip install pyinstaller watchdog win11toast
```

### Build Executable
```powershell
pyinstaller `
  --onefile `
  --noconsole `
  --icon app_icon.ico `
  --add-data "app_icon.png;." `
  --name "Auto Unzip" `
  auto_unzip.py
```

Or use the spec file:
```bash
pyinstaller Auto_Unzip.spec
```

### Development

Clone or download the source:
```bash
# Install dependencies
pip install watchdog win11toast

# Run without compiling
python auto_unzip.py
```

## Dependencies

| Package | Purpose |
|---------|---------|
| `watchdog` | File system monitoring |
| `win11toast` | Windows notifications |
| `pyinstaller` | Build executable |

All are included in the binary distribution.

## Translation Support

Currently supported:
- 🇬🇧 English
- 🇫🇷 Français

Want to add another language? See [TRANSLATIONS.md](TRANSLATIONS.md)

## Updates

- Newer versions replace older ones automatically
- No restart required (takes effect on next launch)
- Update notifications show in system tray

## Advanced Features

### Command Line Arguments

```bash
# Install mode
Auto_Unzip.exe --install

# Uninstall mode
Auto_Unzip.exe --uninstall

# Normal mode (with watcher)
Auto_Unzip.exe
```

### Single Instance Protection

Only one monitor instance runs at a time:
- Prevents duplicate processing
- Prevents notification spam
- Uses Windows mutex for protection

## FAQ

**Q: Will this slow down my computer?**  
A: No, Auto Unzip uses minimal resources and only activates when files are downloaded.

**Q: Can I choose where files are extracted?**  
A: Currently extracts to Downloads folder. Can be modified at installation.

**Q: What about incomplete downloads?**  
A: Auto Unzip automatically ignores `.crdownload`, `.part`, and `.download` files.

**Q: Is it safe?**  
A: Yes, the app includes security checks to prevent malicious ZIP extractions.

**Q: How can I uninstall it?**  
A: Use the uninstall shortcut or run `--uninstall` flag.

## Support

If Auto Unzip has been helpful to you, you can support me! ☕

- **[Buy Me a Coffee](https://buymeacoffee.com/louimlbs)** ☕

Thank you very much for your support! 🙏

For issues, questions, or feature requests:
- Check the log file: `%LOCALAPPDATA%\Auto Unzip\auto_unzip.log`

## License

This project is licensed under **AGPL-3.0 + Commons Clause**.

**What this means:**
- ✅ Open source for community use
- ✅ Free for personal, educational, and non-commercial use
- ❌ Cannot be sold or used for commercial services (SaaS, etc.)
- 📜 For commercial use, a separate license is required

See [LICENSE](LICENSE) file for details.

## Changelog

### Version 1.0 - Initial Release
- ✅ Automatic ZIP extraction
- ✅ Multi-language support (EN/FR)
- ✅ System tray notifications
- ✅ Auto-start on boot
- ✅ Windows integration
- ✅ Comprehensive logging
- ✅ Security features

---

**Made with ❤️ in 🏔️ with 🍫 and 🧀**

*Auto Unzip v1.0 - January 2026*
