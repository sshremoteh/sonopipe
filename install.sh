#!/usr/bin/env bash
# ==============================================================================
# Sonopipe Installer Script
# Installs Sonopipe, sets up Python virtual environment and adds 'sonopipe' alias/command
# ==============================================================================

set -e

REPO_URL="https://github.com/sshremoteh/sonopipe.git"
INSTALL_DIR="${HOME}/.local/share/sonopipe"
BIN_DIR="${HOME}/.local/bin"
ALIAS_LINE="alias sonopipe='${HOME}/.local/bin/sonopipe'"

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}"
echo "  ____                              _             "
echo " / ___|  ___  _ __   ___  _ __ (_) _ __   ___ "
echo " \___ \ / _ \| '_ \ / _ \| '_ \| || '_ \ / _ \ "
echo "  ___) | (_) | | | | (_) | |_) | || |_) |  __/ "
echo " |____/ \___/|_| |_|\___/| .__/|_|| .__/ \___| "
echo "                         |_|      |_|          "
echo -e "${NC}"
echo -e "${BLUE}>>> Installing Sonopipe (PC Audio to Android via ADB)...${NC}\n"

# 1. Check prerequisites
for cmd in git python3; do
    if ! command -v "$cmd" &>/dev/null; then
        echo -e "${RED}[Error] $cmd is required but not installed.${NC}"
        exit 1
    fi
done

if ! command -v adb &>/dev/null; then
    echo -e "${CYAN}[Notice] 'adb' was not found in PATH.${NC}"
    echo "  Please install Android platform-tools:"
    echo "    - Arch Linux: sudo pacman -S android-tools"
    echo "    - Ubuntu/Debian: sudo apt install adb"
    echo "    - Fedora: sudo dnf install android-tools"
    echo ""
fi

# 2. Clone or update repository
if [ -d "$INSTALL_DIR/.git" ]; then
    echo -e ">>> Updating existing Sonopipe installation in ${CYAN}${INSTALL_DIR}${NC}..."
    git -C "$INSTALL_DIR" pull --ff-only
else
    echo -e ">>> Cloning Sonopipe into ${CYAN}${INSTALL_DIR}${NC}..."
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

# 3. Setup Virtual Environment
echo -e ">>> Setting up Python virtual environment..."
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip -q
echo -e ">>> Installing Python dependencies (PySide6, soundcard, numpy)..."
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

# 4. Create launcher binary in ~/.local/bin
mkdir -p "$BIN_DIR"
cat << 'EOF' > "$BIN_DIR/sonopipe"
#!/bin/sh
export QT_LOGGING_RULES="${QT_LOGGING_RULES:-qt.qpa.wayland*=false}"
exec "$HOME/.local/share/sonopipe/.venv/bin/python3" "$HOME/.local/share/sonopipe/run.py" "$@"
EOF
chmod +x "$BIN_DIR/sonopipe"

# 5. Add alias and PATH to Shell Configuration
update_shell_rc() {
    local rc_file="$1"
    if [ -f "$rc_file" ]; then
        if ! grep -q "alias sonopipe=" "$rc_file" 2>/dev/null; then
            echo "" >> "$rc_file"
            echo "# Sonopipe alias & PATH" >> "$rc_file"
            echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$rc_file"
            echo "$ALIAS_LINE" >> "$rc_file"
            echo -e ">>> Added 'sonopipe' alias to ${CYAN}${rc_file}${NC}"
        fi
    fi
}

update_shell_rc "${HOME}/.bashrc"
update_shell_rc "${HOME}/.zshrc"

if [ -f "${HOME}/.config/fish/config.fish" ]; then
    if ! grep -q "alias sonopipe" "${HOME}/.config/fish/config.fish" 2>/dev/null; then
        echo "" >> "${HOME}/.config/fish/config.fish"
        echo 'fish_add_path "$HOME/.local/bin"' >> "${HOME}/.config/fish/config.fish"
        echo "alias sonopipe '$BIN_DIR/sonopipe'" >> "${HOME}/.config/fish/config.fish"
        echo -e ">>> Added 'sonopipe' alias to ${CYAN}~/.config/fish/config.fish${NC}"
    fi
fi

echo -e "\n${GREEN}================================================================${NC}"
echo -e "${GREEN}  ✓ Sonopipe successfully installed!${NC}"
echo -e "${GREEN}================================================================${NC}"
echo -e "You can now run:  ${CYAN}sonopipe${NC} (GUI) or ${CYAN}sonopipe --cli${NC}"
echo -e "To install the APK to your phone directly from terminal:"
echo -e "  ${CYAN}sonopipe --install-apk${NC}"
echo ""
echo -e "Restart your terminal or run: ${CYAN}source ~/.bashrc${NC} (or ~/.zshrc) to load the alias."
