# AnythingLLM Document Sync Tool

A Python utility for managing document ingestion into AnythingLLM workspaces.  
This tool automates uploading, embedding, and remote cleanup of documents — keeping your workspace in sync with local files.

**Important**: This tool **never** deletes, moves, or modifies any local files on your system.  
All operations are remote-only (uploads, embeddings, un-embedding/unloading via API).

## Features

- **Automatic Document Discovery**: Recursively scans configured paths for supported file types
- **Smart Sync**: Uploads only new or modified documents; embeds only what's needed
- **Per-Workspace Tracking**: Separate local SQLite database per workspace (`uploaded-docs-<slug>.db`)
- **Config-Driven Exclusions**: File and directory excludes defined in YAML config (no automatic .gitignore)
- **Remote Cleanup**: Automatically removes remote embeddings/unloads for files no longer present locally
- **Purge Commands**: `--purge` removes all workspace embeddings; `--purge-raw` also deletes tracked raw uploads from storage
- **Verbose Logging**: Detailed file-by-file scanning with `--verbose`
- **Force Re-sync**: `--force` clears tracking DB and re-processes everything
- **One-Click Installer**: `install.sh` handles venv, deps, binary build, PATH setup, and config template
- **Standalone Binary**: Built as a single executable for easy use on servers or other machines
- **Logging**: Console progress + persistent log in `~/.anythingllm-sync/log/sync.log`

## Requirements

- Python 3.10+ (tested with 3.12)
- AnythingLLM instance (default: http://localhost:3001)
- macOS prerequisites (via Homebrew):
  ```shell
  brew install pyenv sqlite
  ```
- Python packages: `requests`, `PyYAML`, `pyinstaller` (installed by script)

## Installation

### Recommended: One-command installer (macOS/Linux)

From the project root:

```shell
chmod +x install.sh
./install.sh
```

This script does everything:
- Creates/activates virtual environment (`.venv`)
- Installs dependencies
- Installs the package editable
- Builds the standalone binary
- Creates `~/.anythingllm-sync/` + default `config.yaml` template + `log/` dir
- Moves binary to `~/bin/anythingllm-sync`
- Adds `~/bin` to PATH (in `.bashrc`/`.zshrc` if missing)

After running:
- Reload shell: `source ~/.bashrc` (or `~/.zshrc`)
- Test: `anythingllm-sync --help`

### Manual / Development Install

1. Create and activate virtual environment:

```shell
pyenv install 3.12.7
pyenv local 3.12.7
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
```

2. Install dependencies and package:

```shell
pip install -r requirements.txt
pip install -e .
```

3. (Optional) Build standalone binary manually:

```shell
pip install pyinstaller
pyinstaller \
  --onefile \
  --name anythingllm-sync \
  --add-data "anythingllm_loader:anythingllm_loader" \
  --add-data "anythingllm_sync:anythingllm_sync" \
  --clean \
  anythingllm_sync/ingest_anythingllm_docs.py
```

- Binary: `dist/anythingllm-sync`
- Move to PATH: `mv dist/anythingllm-sync ~/bin/ && chmod +x ~/bin/anythingllm-sync`

## Configuration

All config files live in `~/.anythingllm-sync/` (created automatically).

### Default config (auto-created template if missing)

`~/.anythingllm-sync/config.yaml`

```yaml
# AnythingLLM Document Sync Configuration
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
```

- **api-key**: AnythingLLM → Settings → Developer API → Generate New API Key
- **workspace-slug**: Workspace settings → Vector Database → "Vector database identifier"
- Exclusions apply only to `file-paths` — no automatic `.gitignore` support

### Multiple workspaces

Create additional files in the same directory, e.g.:

- `~/.anythingllm-sync/qpredict.yaml`
- `~/.anythingllm-sync/aws-prod.yaml`

Run with: `anythingllm-sync --config qpredict.yaml`

## Usage

Basic sync (default config):

```shell
anythingllm-sync
```

With custom config + details:

```shell
anythingllm-sync --config qpredict.yaml --verbose
```

Common commands:

```shell
# Force full re-sync (ignores previous tracking)
anythingllm-sync --force --verbose

# Purge all embeddings from workspace (remote only)
anythingllm-sync --purge --verbose

# Purge embeddings + delete tracked raw files from storage
anythingllm-sync --purge --purge-raw --verbose
```

## Logging

- Console: High-level progress + warnings/errors
- With `--verbose`: File-by-file include/skip details
- Persistent log: `~/.anythingllm-sync/log/sync.log` (rotating, 5 MB max, 3 backups)

## Project Structure

- `ingest_anythingllm_docs.py`: Main script (entry point)
- `anythingllm_loader/`: Core package (API, config, DB)
- `anythingllm_sync/`: Package wrapper for main script
- `install.sh`: One-command installer (venv, deps, binary, PATH, config setup)
- `requirements.txt`: Frozen dependencies

## Notes

- Fork enhancements: per-workspace DB, purge commands, verbose output, improved logging, remote-only cleanup language, one-command installer, standalone binary support.
- Never modifies local files — only interacts with AnythingLLM via API.
- For production: use the standalone binary created by `install.sh`.
- For development: keep editable install (`pip install -e .`).
