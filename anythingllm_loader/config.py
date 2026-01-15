import os
import pathlib
import yaml

CONFIG_DIR = pathlib.Path.home() / ".anythingllm-sync"
CONFIG_FILE = 'config.yaml'


# Config file looks like this:
# api-key: WFSDFD-ASDAFDFD-Q8M53TR-AAAAS48
# workspace-slug: aws
# file-paths:
#   - /Users/username/Documents/
# directory-excludes:
#   - .obsidian
# file-excludes:
#   - .DS_Store

class AnythingLLMConfig:

    # create init method including all config keys
    def __init__(self, api_key: str, file_paths: list, directory_excludes: list, file_excludes: list, workspace_slug: str):
        self.api_key = api_key
        self.file_paths = file_paths
        self.directory_excludes = directory_excludes
        self.file_excludes = file_excludes
        self.workspace_slug = workspace_slug

    @staticmethod
    def load_config(config_path: str | None = None):
        # Determine the path
        if config_path is None:
            config_file = CONFIG_DIR / CONFIG_FILE
            # Auto-create default dir if missing
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        else:
            config_file = pathlib.Path(config_path).resolve()
            # Auto-create parent dir for custom path if missing
            config_file.parent.mkdir(parents=True, exist_ok=True)

        # Now load
        if config_file.exists():
            with open(config_file, "r") as f:
                config = yaml.safe_load(f)

                # check whether api-key is present, fail if not
                if "api-key" not in config:
                    raise KeyError("API key not found in config file")
                # check whether file-paths is present, fail if not
                if "file-paths" not in config:
                    raise KeyError("File paths not found in config file")
                # check whether directory-excludes is present, fail if not
                if "directory-excludes" not in config:
                    raise KeyError("Directory excludes not found in config file")
                # check whether file-excludes is present, fail if not
                if "file-excludes" not in config:
                    raise KeyError("File excludes not found in config file")
                if "workspace-slug" not in config:
                    raise KeyError("Workspace slug not found in config file")
        else:
            raise FileNotFoundError(f"{config_file} file not found. Create it first with required fields.")

        return AnythingLLMConfig(config["api-key"], config["file-paths"], config["directory-excludes"],
                                 config["file-excludes"], config["workspace-slug"])