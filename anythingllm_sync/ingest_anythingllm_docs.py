import json
import pathlib
import sys
from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
import argparse
import requests  # Added for API calls in purge mode

from anythingllm_loader.database import DocumentDatabase, AnythingLLMDocument
from anythingllm_loader.anythingllm_api import AnythingLLM
from anythingllm_loader.config import AnythingLLMConfig


def create_default_config_template(config_path: pathlib.Path):
    """Create a template config file if the default one is missing."""
    template = """# AnythingLLM Document Sync Configuration Template
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
"""
    config_path.write_text(template)
    print(f"Default config template created at: {config_path}")
    print("Please edit it with your real values and re-run the command.")
    sys.exit(0)


def fetch_local_documents(config: AnythingLLMConfig, verbose: bool = False):
    logger = logging.getLogger("anythingllm-sync")
    local_documents = []
    skipped_count = 0

    for base_path_str in config.file_paths:
        base_path = pathlib.Path(base_path_str).resolve()
        for file in base_path.rglob("*"):
            rel_str = str(file.relative_to(base_path))

            # Config-based excludes only (no .gitignore)
            exclude = False
            for excl in config.file_excludes:
                if excl in file.name:
                    exclude = True
                    break
            for excl in config.directory_excludes:
                if excl in str(file):
                    exclude = True
                    break

            if exclude:
                if verbose:
                    logger.info(f"Skipped (config exclude): {rel_str}")
                skipped_count += 1
                continue

            # Unsupported file type
            ext = file.suffix.lstrip('.')
            if ext not in AnythingLLM.supported_file_types():
                if verbose:
                    logger.info(f"Skipped (unsupported type): {rel_str}")
                skipped_count += 1
                continue

            if file.is_file():
                if verbose:
                    logger.info(f"Included: {rel_str}")
                local_documents.append(str(file.absolute()))

    if verbose:
        logger.info(f"Total files included: {len(local_documents)} | Skipped: {skipped_count}")

    return local_documents


def upload_new_documents(anything_llm: AnythingLLM, database: DocumentDatabase, local_documents: list[str],
                         loaded_documents: list[AnythingLLMDocument], logger: logging.Logger):
    for local_document in local_documents:
        document_loaded = False
        local_mtime = datetime.fromtimestamp(pathlib.Path(local_document).stat().st_mtime, tz=timezone.utc)

        for loaded_doc in loaded_documents:
            if loaded_doc.local_file_path == local_document:
                if int(local_mtime.strftime('%Y%m%d%H%M%S')) > int(
                        loaded_doc.upload_timestamp.strftime('%Y%m%d%H%M%S')):
                    logger.info(f"File changed → will re-upload: {local_document}")
                else:
                    document_loaded = True
                    break

        if not document_loaded:
            logger.info(f"Uploading new/changed document: {local_document}")
            response = anything_llm.upload_document(local_document)
            if response is not None:
                database.add_document(AnythingLLMDocument(
                    local_document,
                    local_mtime,
                    response['location'],
                    json.dumps(response)
                ))
            else:
                logger.warning(f"Upload failed for {local_document}")


def embed_new_documents(anything_llm: AnythingLLM, loaded_documents: list[AnythingLLMDocument],
                        embedded_documents: list, logger: logging.Logger):
    to_embed = [
        doc.anythingllm_document_location
        for doc in loaded_documents
        if doc.anythingllm_document_location not in embedded_documents
    ]

    for loc in to_embed:
        logger.info(f"Embedding document: {loc}")
        anything_llm.embed_new_document(loc)


def remove_embedded_documents(anything_llm: AnythingLLM, local_documents: list,
                              loaded_documents: list[AnythingLLMDocument],
                              embedded_documents: list, logger: logging.Logger):
    to_unembed = []

    for emb_loc in embedded_documents:
        loaded_doc = next((d for d in loaded_documents if d.anythingllm_document_location == emb_loc), None)
        if loaded_doc is None:
            to_unembed.append(emb_loc)
            continue

        if loaded_doc.local_file_path not in local_documents:
            to_unembed.append(emb_loc)

    for loc in to_unembed:
        logger.info(f"Unembedding removed document: {loc}")
        anything_llm.unembed_document(loc)


def remove_loaded_documents(anything_llm: AnythingLLM, database: DocumentDatabase, local_documents: list,
                            loaded_documents: list[AnythingLLMDocument], logger: logging.Logger):
    to_unload = [
        doc.anythingllm_document_location
        for doc in loaded_documents
        if doc.local_file_path not in local_documents
    ]

    for loc in to_unload:
        logger.info(f"Unloading removed document: {loc}")
        if anything_llm.unload_document(loc):
            database.remove_document(loc)


def main():
    parser = argparse.ArgumentParser(
        description="""AnythingLLM Document Sync Tool

This tool synchronizes local files from specified paths to an AnythingLLM workspace.
It uploads new or changed files, embeds them into the workspace vector database, and removes
remote embeddings/unloads for files no longer present locally.

Important:
- This tool NEVER deletes, moves, or modifies any local files on your system.
- All changes happen ONLY in AnythingLLM (uploads, embeddings, remote cleanup).
- Local tracking is stored per workspace in ~/.anythingllm-sync/uploaded-docs-<workspace-slug>.db

Key Features:
- Multiple configs via --config <filename> (all in ~/.anythingllm-sync/)
- Per-workspace local tracking database
- Exclusion rules (file-excludes, directory-excludes) in your .yml config 
- Force mode to reset and re-sync everything
- Purge mode to remove all embeddings (and optionally raw uploads) from workspace

Workflow:
1. Scan local files (respecting the defined excludes)
2. Compare against local DB and remote workspace state
3. Upload new/changed files to AnythingLLM
4. Embed uploaded files into workspace
5. Unembed/unload removed files

Usage Examples:
- Normal sync (default config): anythingllm-sync
- Custom config + verbose: anythingllm-sync --config wkspc.yml --verbose
- Force full re-sync: anythingllm-sync --force --verbose
- Purge all embeddings: anythingllm-sync --purge --verbose
- Purge embeddings + raw files: anythingllm-sync --purge --purge-raw --verbose

For issues, check logs or run with --verbose.
""",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yml",
        help="""Name of the config file inside ~/.anythingllm-sync/
(default: config.yml - auto-created template if missing)

All configs MUST be in this directory.
Examples:
--config wkspc.yml → ~/.anythingllm-sync/wkspc.yml
--config aws-prod.yml → ~/.anythingllm-sync/aws-prod.yml
"""
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="""Enable detailed logging:
- Shows every scanned file, include/skip reasons
- Upload/embed progress per file
- Total counts (included/skipped)

Without -v: Only warnings/errors + high-level progress (e.g. 'Scanning...', 'Sync completed')
"""
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="""Force a full re-sync:
- Deletes the workspace-specific DB (uploaded-docs-<slug>.db)
- Re-scans and re-processes ALL files as if first run
- Useful after manual workspace purge in UI or to reset tracking

Warning: This causes re-upload/re-embed of everything (may take time/CPU)
"""
    )
    parser.add_argument(
        "--purge",
        action="store_true",
        help="""Purge mode: Remove ALL currently embedded documents from the workspace.
- Fetches current embeddings via API
- Sends bulk delete to /update-embeddings
- Does NOT affect local files or uploads (use --purge-raw for that)

Safe after UI changes; combines with --force for full reset.
"""
    )
    parser.add_argument(
        "--purge-raw",
        action="store_true",
        help="""When combined with --purge:
- Also deletes raw uploaded files from AnythingLLM storage (/system/remove-documents)
- ONLY deletes files tracked in your local DB for this workspace
- Prevents orphan files; very targeted/safe

Example: anythingllm-sync --purge --purge-raw --verbose
"""
    )

    args = parser.parse_args()

    # Fixed config directory
    CONFIG_DIR = pathlib.Path.home() / ".anythingllm-sync"
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Build full config path
    config_path = CONFIG_DIR / args.config

    # Create template if the default config is missing
    if not config_path.exists() and args.config == "config.yml":
        create_default_config_template(config_path)

    # Load config (exit if not found)
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        print("Available configs in ~/.anythingllm-sync/:")
        for f in CONFIG_DIR.glob("*.yml"):
            print(f"  - {f.name}")
        for f in CONFIG_DIR.glob("*.yml"):
            print(f"  - {f.name}")
        sys.exit(1)

    # Logging setup
    logger = logging.getLogger("anythingllm-sync")
    logger.setLevel(logging.INFO if args.verbose else logging.WARNING)

    # Console
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
    logger.addHandler(console)

    # File (in log subdir, rotating)
    log_dir = CONFIG_DIR / "log"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "sync.log"
    file_handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3)
    file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(file_handler)

    logger.info(f"Starting sync with config: {config_path}")

    # Load config
    config = AnythingLLMConfig.load_config(str(config_path))

    # AnythingLLM connection
    anything_llm = AnythingLLM(config)
    if not anything_llm.authenticate():
        logger.error("Failed to authenticate with AnythingLLM API. Check your api-key.")
        return

    # Database (per-workspace)
    db_filename = f"uploaded-docs-{config.workspace_slug}.db"
    db_path = CONFIG_DIR / db_filename

    # Instantiate database first
    database = DocumentDatabase(db_path=str(db_path))

    if args.force:
        if db_path.exists():
            logger.warning(f"Force mode: deleting tracking DB {db_path}")
            db_path.unlink()

    if not database.initialize_database():
        logger.error("Failed to initialize local tracking database.")
        return

    # PURGE MODE
    if args.purge:
        logger.warning(f"PURGE MODE activated for workspace: {config.workspace_slug}")

        # Get current embedded documents
        embedded = anything_llm.fetch_embedded_workspace_documents()
        if not embedded:
            logger.info("No embedded documents found in workspace → nothing to purge.")
        else:
            logger.info(f"Found {len(embedded)} embedded documents to remove.")

            # Purge embeddings
            response = requests.post(
                f"http://localhost:3001/api/v1/workspace/{config.workspace_slug}/update-embeddings",
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                json={"deletes": embedded},
                timeout=120
            )
            if response.status_code == 200:
                logger.info("Successfully purged all embeddings from workspace.")
            else:
                logger.error(f"Embedding purge failed: {response.status_code} - {response.text}")
                return

        # Optional: delete raw files tracked in our DB
        if args.purge_raw:
            loaded = database.get_documents()
            if not loaded:
                logger.info("No tracked documents in local DB → no raw files to delete.")
            else:
                raw_locations = [doc.anythingllm_document_location for doc in loaded]
                logger.info(f"Deleting {len(raw_locations)} matching raw uploaded files from storage...")

                del_response = requests.delete(
                    "http://localhost:3001/api/v1/system/remove-documents",
                    headers={
                        "Authorization": f"Bearer {config.api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    json={"names": raw_locations},
                    timeout=60
                )
                if del_response.status_code == 200:
                    logger.info("Raw uploaded files deleted successfully.")
                else:
                    logger.error(f"Raw file deletion failed: {del_response.status_code} - {del_response.text}")

        # Clear local DB after purge
        if db_path.exists():
            db_path.unlink()
            logger.info("Local tracking DB cleared after purge.")
        return  # Exit after purge

    # NORMAL SYNC (continues below if not purging)
    logger.info("Scanning local files...")
    local_documents = fetch_local_documents(config, verbose=args.verbose)

    loaded_documents = database.get_documents()

    logger.info("Processing uploads...")
    upload_new_documents(anything_llm, database, local_documents, loaded_documents, logger)

    embedded_documents = anything_llm.fetch_embedded_workspace_documents()
    loaded_documents = database.get_documents()  # refresh

    logger.info("Processing embeddings...")
    embed_new_documents(anything_llm, loaded_documents, embedded_documents, logger)

    embedded_documents = anything_llm.fetch_embedded_workspace_documents()

    logger.info("Cleaning up removed documents...")
    remove_embedded_documents(anything_llm, local_documents, loaded_documents, embedded_documents, logger)
    remove_loaded_documents(anything_llm, database, local_documents, loaded_documents, logger)

    logger.info("Sync completed successfully.")


if __name__ == "__main__":
    main()
