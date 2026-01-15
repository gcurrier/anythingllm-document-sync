#!/usr/bin/env bash
set -euo pipefail

echo "============================================================="
echo " Installing anythingllm-sync tool + standalone binary"
echo "============================================================="


# 1. Activate venv if it exists, or create one
if [[ -d ".venv" ]]; then
    echo "Activating existing virtual environment..."
    source .venv/bin/activate
else
    echo "Creating new virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
fi


# 2. Install Python dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt || true   # ignore if no requirements.txt
pip install pyinstaller pathspec requests PyYAML


# 3. Install the package editable (so entry-point works)
echo "Installing package in editable mode..."
pip install -e .


# 4. Create ~/.anythingllm-sync/ + default config + log dir
CONFIG_DIR="$HOME/.anythingllm-sync"
LOG_DIR="$CONFIG_DIR/log"

echo "Creating config directory: $CONFIG_DIR"
mkdir -p "$CONFIG_DIR" "$LOG_DIR"

DEFAULT_CONFIG="$CONFIG_DIR/config.yml"
if [[ ! -f "$DEFAULT_CONFIG" ]]; then
    echo "Creating default config template: $DEFAULT_CONFIG"
    cat > "$DEFAULT_CONFIG" << 'EOF'
# AnythingLLM Document Sync Configuration Template
# Edit this file with your real values and remove this comment block.

api-key: YOUR_ANYTHINGLLM_API_KEY_HERE
workspace-slug: your-workspace-slug-here

file-paths:
  - /home/user/path/to/your/repo-or-folder
  # Add more absolute paths as needed

directory-excludes:
  - .git
  - venv
  - node_modules
  - __pycache__

file-excludes:
  - "*.log"
  - "*.tmp"

# The script will automatically respect any .gitignore files found in the roots of file-paths.
EOF
    echo "→ Please edit $DEFAULT_CONFIG before first use"
else
    echo "Default config already exists: $DEFAULT_CONFIG"
fi

# 5. Build standalone binary with PyInstaller
echo "Building standalone binary with PyInstaller..."
pyinstaller \
  --onefile \
  --name anythingllm-sync \
  --add-data "anythingllm_loader:anythingllm_loader" \
  --add-data "anythingllm_sync:anythingllm_sync" \
  --clean \
  --log-level INFO \
  anythingllm_sync/ingest_anythingllm_docs.py

BINARY="dist/anythingllm-sync"

if [[ ! -f "$BINARY" ]]; then
    echo "ERROR: Binary not found at $BINARY"
    exit 1
fi


# 6. Install binary to ~/bin
BIN_DIR="$HOME/bin"
mkdir -p "$BIN_DIR"

BINARY_PATH="$BIN_DIR/anythingllm-sync"

echo "Installing binary to $BINARY_PATH"
cp "$BINARY" "$BINARY_PATH"
chmod +x "$BINARY_PATH"


# 7. Add ~/bin to PATH (only if not already present)
PATH_LINE='export PATH="$HOME/bin:$PATH"'

# Common variations we want to detect and avoid duplicating
PATTERNS_TO_CHECK=(
    'export PATH="$HOME/bin:$PATH"'
    'export PATH=$HOME/bin:$PATH'
    'PATH="$HOME/bin:$PATH"'
    'PATH=$HOME/bin:$PATH'
)

already_present=false

for rcfile in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile" "$HOME/.bash_profile"; do
    if [[ -f "$rcfile" ]]; then
        for pattern in "${PATTERNS_TO_CHECK[@]}"; do
            if grep -qF "$pattern" "$rcfile"; then
                echo "~/bin already in PATH in $rcfile (skipping append)"
                already_present=true
                break 2
            fi
        done
    fi
done

if ! $already_present; then
    echo "Adding ~/bin to PATH in shell config files"
    for rcfile in "$HOME/.bashrc" "$HOME/.zshrc"; do
        if [[ -f "$rcfile" ]]; then
            echo "" >> "$rcfile"
            echo "# Added by anythingllm-sync installer - $(date '+%Y-%m-%d')" >> "$rcfile"
            echo "$PATH_LINE" >> "$rcfile"
            echo "→ Added to $rcfile"
        fi
    done
    echo "Note: You may need to run 'source ~/.bashrc' (or open a new terminal) for the change to take effect."
else
    echo "No PATH modification needed — ~/bin is already configured."
fi

# 8. Final instructions & quick test
echo ""
echo "============================================================="
echo " Installation finished successfully!"
echo ""
echo "Binary location:   $BIN_DIR/anythingllm-sync"
echo "Default config:    $DEFAULT_CONFIG"
echo "Log directory:     $LOG_DIR"
echo ""
echo "Next steps:"
echo "  1. Edit your config file:"
echo "     nano $DEFAULT_CONFIG"
echo ""
echo "  2. Test the tool:"
echo "     anythingllm-sync --help"
echo "     anythingllm-sync --verbose --config config.yml"
echo ""
echo "  3. Reload your shell (or open new terminal) to use the new PATH:"
echo "     source ~/.bashrc   # or source ~/.zshrc"
echo ""
echo "Done."
echo "============================================================="