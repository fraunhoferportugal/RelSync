import re

bump_priority = {"patch": 1, "minor": 2, "major": 3}

semver_regex = re.compile(
    r"^(?P<prefix>v?)"
    r"(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


def parse_version(version):
    """Split semver into (major, minor, patch)."""
    match = semver_regex.match(version)
    if not match:
        raise ValueError(f"Invalid SemVer: {version}")
    major = int(match.group("major"))
    minor = int(match.group("minor"))
    patch = int(match.group("patch"))
    return (major, minor, patch)

def get_version_string(version):
    version_parts=parse_version(version)
    return '.'.join(str(part) for part in version_parts)


def version_bump(old, new):
    """Return bump type: 'patch', 'minor', 'major', or None."""
    old_major, old_minor, old_patch = parse_version(old)
    new_major, new_minor, new_patch = parse_version(new)

    if new_major > old_major:
        return "major"
    elif new_minor > old_minor:
        return "minor"
    elif new_patch > old_patch:
        return "patch"
    return None


def bump_version(version, bump):
    """Return version bumped according to bump type."""
    major, minor, patch = parse_version(version)
    if bump == "major":
        return f"{major+1}.0.0"
    elif bump == "minor":
        return f"{major}.{minor+1}.0"
    elif bump == "patch":
        return f"{major}.{minor}.{patch+1}"
    return version
