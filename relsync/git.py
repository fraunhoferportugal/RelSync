import subprocess

from .utils import run


def get_submodules():
    """Return dict of submodule names -> paths from .gitmodules."""
    out = run("git config --file .gitmodules --get-regexp path", capture_output=True)
    submodules = {}
    for line in out.splitlines():
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        key, path = parts
        if not key.startswith("submodule.") or not key.endswith(".path"):
            continue
        name = key[len("submodule.") : -len(".path")]
        submodules[name] = path
    return submodules


def fetch_tags(path):
    run("git fetch --tags --quiet", cwd=path)
    tags = run("git tag | sort -Vr", cwd=path, capture_output=True).splitlines()
    current = run(
        "git describe --tags --exact-match 2>/dev/null || echo 'none'",
        cwd=path,
        capture_output=True,
    )
    latest = tags[0] if tags else "none"
    return tags, current, latest


def get_latest_tag():
    tag = run("git tag | sort -Vr | head -n 1 || echo ''", capture_output=True)
    return tag.strip() or "0.0.0"


def commit_changes(message):
    """Commit all changes to git with the given message."""
    try:
        run("git add -A")
        run(f'git commit -m "{message}"', silent=True)
    except subprocess.CalledProcessError:
        return False

    return True
