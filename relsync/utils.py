import json
import os
import subprocess
import sys

try:
    import yaml

    def load_yaml(path):
        try:
            with open(path) as f:
                return yaml.safe_load(f)
        except:
            return {}

    def dump_yaml(data, path):
        with open(path, "w") as f:
            yaml.safe_dump(data, f, sort_keys=False)

    def load_yaml_string(yaml_str):
        try:
            return yaml.safe_load(yaml_str) or {}
        except:
            return {}

except ImportError:

    def yq_available(min_major=4):
        try:
            out = subprocess.run(
                ["yq", "--version"], capture_output=True, text=True, check=True
            )
            import re

            match = re.search(r"version\s+(\d+)\.(\d+)\.(\d+)", out.stdout)
            if not match:
                return False
            major, minor, patch = map(int, match.groups())
            return major >= min_major
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    if not yq_available():
        print(
            "PyYAML not installed and yq v4+ not available. Exiting.", file=sys.stderr
        )
        sys.exit(1)

    print("PyYAML not installed, using yq for YAML parsing")

    def load_yaml(path):
        out = subprocess.run(
            ["yq", "-o=json", ".", path], capture_output=True, text=True, check=True
        )
        return json.loads(out.stdout)

    def dump_yaml(data, path):
        json_str = json.dumps(data)
        subprocess.run(
            ["yq", "-P", "-o=yaml", ".", "-i", path],
            input=json_str,
            text=True,
            check=True,
        )

    def load_yaml_string(yaml_str):
        """Load YAML from a string using yq fallback."""
        # Pipe the string into yq
        proc = subprocess.run(
            ["yq", "-o=json", "."],
            input=yaml_str,
            capture_output=True,
            text=True,
            check=True,
        )
        try:
            return json.loads(proc.stdout) or {}
        except:
            return {}


def run(cmd, cwd=None, capture_output=False, silent=False):
    """Run a shell command."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        shell=True,
        capture_output=capture_output,
        text=True,
        stdout=subprocess.DEVNULL if silent else None,
        stderr=subprocess.DEVNULL if silent else None,
    )
    if capture_output:
        return result.stdout.strip()
    else:
        result.check_returncode()


def prompt(msg, default=None):
    ans = input(msg)
    if not ans and default is not None:
        ans = default
    return ans.strip()


def safe(v):
    return v if v is not None else "-"


def parse_json_file(tag_overrides_file_path):
    if tag_overrides_file_path and os.path.isfile(tag_overrides_file_path):
        with open(tag_overrides_file_path) as f:
            try:
                overrides_map = json.load(f)
            except:
                return {}
        return overrides_map
    return {}


def parse_json_arg(tag_overrides_arg):
    try:
        overrides_map = json.loads(tag_overrides_arg)
    except:
        return {}

    return overrides_map


def save_state(updates, parent_info, path):
    """Save updates and parent info to JSON."""
    state = {"updates": updates, "parent_info": parent_info}
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def load_state(path):
    """Load updates and parent info from JSON."""
    if not os.path.isfile(path):
        return None, None
    with open(path) as f:
        try:
            state = json.load(f)
            return state.get("updates"), state.get("parent_info")
        except Exception:
            return None, None
