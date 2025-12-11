import os

from .distribution import default_chart_location
from .git import get_submodules
from .semver import *
from .utils import *


def get_chart_version(chart_path):
    if not os.path.exists(chart_path):
        return None
    chart = load_yaml(chart_path)
    return chart.get("version")


def get_current_status_from_parent_chart(chart_path_overrides=None):
    """
    Return current state using the versions recorded in the parent chart dependencies
    for inferring subchart bumps.
    """
    if chart_path_overrides is None:
        chart_path_overrides = {}

    submodules = get_submodules()
    submodule_chart_path_overrides = chart_path_overrides.get("submodule_charts", {})
    parent_chart_path = chart_path_overrides.get("repo_chart")

    # Compute bumps from current versions in parent chart dependencies
    subchart_bumps = compute_subchart_bumps_from_parent(
        parent_chart_path, submodule_chart_path_overrides
    )

    updates = {}
    for name, path in submodules.items():
        chart_rel_path = submodule_chart_path_overrides.get(name)
        sub_chart_path = os.path.join(path, chart_rel_path)
        chart_data = load_yaml(sub_chart_path)
        chart_name = chart_data.get("name") or name
        current_version = chart_data.get("version")

        updates[name] = {
            "path": path,
            "chart_name": chart_name,
            "current_tag": run(
                "git describe --tags --exact-match 2>/dev/null || echo 'none'",
                cwd=path,
                capture_output=True,
            ),
            "latest_tag": None,
            "suggested_tag": None,
            "recent_tags": [],
            "current_tag_chart_version": current_version,
            "suggested_tag_chart_version": None,
            "chart_bump": subchart_bumps.get(name),
        }

    parent_current = get_chart_version(parent_chart_path)
    # Decide parent bump from subchart bumps
    max_bump_level = max(
        (bump_priority[b] for b in subchart_bumps.values() if b is not None),
        default=0,
    )
    bump = None
    for k, v in bump_priority.items():
        if v == max_bump_level:
            bump = k
            break

    repo_bump = "minor" if bump and bump_priority[bump] > 2 else "patch"
    parent_info = {
        "current": parent_current,
        "suggested": (
            bump_version(parent_current, repo_bump) if bump else parent_current
        ),
        "chart_bump": repo_bump,
    }

    return updates, parent_info


def compute_subchart_bumps_from_parent(
    parent_chart_path, submodule_chart_path_overrides=None
):
    """
    Returns a dict of submodule_name -> bump type based on parent chart dependencies.
    Only uses the versions in the parent chart, not the suggested tags.
    """
    if submodule_chart_path_overrides is None:
        submodule_chart_path_overrides = {}

    if not os.path.isfile(parent_chart_path):
        print(f"Parent chart not found: {parent_chart_path}", file=sys.stderr)
        return {}

    parent_chart = load_yaml(parent_chart_path)
    submodule_bumps = {}
    submodules = get_submodules()

    # Map current versions from parent chart dependencies
    dep_versions = {
        dep["name"]: dep["version"] for dep in parent_chart.get("dependencies", [])
    }

    for name, path in submodules.items():
        chart_rel_path = submodule_chart_path_overrides.get(name)
        sub_chart_path = os.path.join(path, chart_rel_path)
        current_sub_version = get_chart_version(sub_chart_path)
        parent_dep_version = dep_versions.get(name)

        if parent_dep_version and current_sub_version:
            bump = version_bump(parent_dep_version, current_sub_version)
        else:
            bump = None  # Could not infer

        submodule_bumps[name] = bump

    return submodule_bumps


def bump_chart_version(bump_type, app_version, update_chart, chart_path_overrides=None):
    chart_file = chart_path_overrides.get("repo_chart", default_chart_location)
    if not os.path.exists(chart_file):
        print(f"Chart not found: {chart_file}", file=sys.stderr)
        sys.exit(1)

    chart = load_yaml(chart_file)
    if len(chart) == 0:
        print(f"Couldn't load chart file", file=sys.stderr)

    chart_version = chart["version"]
    new_chart_version = bump_version(chart_version, bump_type)
    if update_chart:
        chart["version"] = new_chart_version
        chart["appVersion"] = app_version
        dump_yaml(chart, chart_file)

    return new_chart_version
