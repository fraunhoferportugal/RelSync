#!/usr/bin/env python3
import argparse
import json
import subprocess
import os
import sys


# -------------------------
# Utilities
# -------------------------
def run(cmd, cwd=None, capture_output=False, silent=False):
    """Run a shell command."""
    result = subprocess.run(
        cmd,
        cwd=cwd,
        shell=True,
        capture_output=capture_output,
        text=True,
        stdout=subprocess.DEVNULL if silent else None,
        stderr=subprocess.DEVNULL if silent else None
    )
    if capture_output:
        return result.stdout.strip()
    else:
        result.check_returncode()


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
    tags = run("git tag --sort=-v:refname", cwd=path, capture_output=True).splitlines()
    current = run(
        "git describe --tags --exact-match 2>/dev/null || echo 'none'",
        cwd=path,
        capture_output=True,
    )
    latest = tags[0] if tags else "none"
    return tags, current, latest


def prompt(msg, default=None):
    ans = input(msg)
    if not ans and default is not None:
        ans = default
    return ans.strip()


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
            yaml.safe_dump(data, f)

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
            check=True
        )
        try:
            return json.loads(proc.stdout) or {}
        except:
            return {}


# -------------------------
# Fetch updates
# -------------------------
def get_chart_version(chart_path):
    if not os.path.exists(chart_path):
        return None
    chart = load_yaml(chart_path)
    return chart.get("version")


def parse_version(version):
    """Split semver into (major, minor, patch)."""
    parts = version.split(".")
    return tuple(int(p) for p in parts)


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


bump_priority = {"patch": 1, "minor": 2, "major": 3}

default_chart_location = "deploy/chart/Chart.yaml"


def fetch_updates(submodule_tag_overrides, chart_path_overrides):
    submodules = get_submodules()
    updates = {}
    global_bump_level = 0

    submodule_chart_path_overrides = chart_path_overrides.get("submodule_charts", {})
    for name, path in submodules.items():
        tags, current_tag, latest_tag = fetch_tags(path)

        suggested_tag = submodule_tag_overrides.get(name, latest_tag)

        chart_rel_path = submodule_chart_path_overrides.get(
            name, default_chart_location
        )
        sub_chart = os.path.join(path, chart_rel_path)
        current_version = get_chart_version(sub_chart)

        # "simulate" suggested version by checking out suggested_tag in a temp way
        suggested_version = None
        chart_name = None
        if suggested_tag and suggested_tag != "none":
            # git show allows reading a file at a tag without checkout
            try:
                content = run(
                    " ".join(
                        [
                            "git",
                            "show",
                            f"{suggested_tag}:{chart_rel_path}",
                        ]
                    ),
                    cwd=path,
                    capture_output=True,
                )
                chart = load_yaml_string(content)
                suggested_version = chart.get("version")
                chart_name = chart.get("name")
            except subprocess.CalledProcessError:
                print(f"Error: cannot read {chart_rel_path} at tag {suggested_tag} in submodule {name} ({path})", file=sys.stderr)
                sys.exit(1)

        bump = None
        if suggested_version:
            if not current_version:
                bump = "major"
            else:
                bump = version_bump(current_version, suggested_version)
            if bump:
                global_bump_level = max(global_bump_level, bump_priority[bump])

        updates[name] = {
            "path": path,
            "chart_name": chart_name,
            "current_tag": current_tag,
            "latest_tag": latest_tag,
            "suggested_tag": suggested_tag,
            "recent_tags": tags,
            "current_tag_chart_version": current_version,
            "suggested_tag_chart_version": suggested_version,
            "chart_bump": bump,
        }

    bump_type = None
    for k, v in bump_priority.items():
        if v == global_bump_level:
            bump_type = k
            break

    repo_chart = chart_path_overrides.get("repo_chart", default_chart_location)
    repo_current = get_chart_version(repo_chart)
    repo_bump = "minor" if bump_type and bump_priority[bump_type] > 2 else "patch"
    repo_suggested = (
        bump_version(repo_current, repo_bump) if bump_type else repo_current
    )

    return updates, {
        "current": repo_current,
        "suggested": repo_suggested,
        "chart_bump": repo_bump,
    }

def compute_subchart_bumps_from_parent(parent_chart_path, submodule_chart_path_overrides=None):
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
    dep_versions = {dep["name"]: dep["version"] for dep in parent_chart.get("dependencies", [])}

    for name, path in submodules.items():
        chart_rel_path = submodule_chart_path_overrides.get(name, default_chart_location)
        sub_chart_path = os.path.join(path, chart_rel_path)
        current_sub_version = get_chart_version(sub_chart_path)
        parent_dep_version = dep_versions.get(name)

        if parent_dep_version and current_sub_version:
            bump = version_bump(parent_dep_version, current_sub_version)
        else:
            bump = None  # Could not infer

        submodule_bumps[name] = bump

    return submodule_bumps

def get_current_status_from_parent_chart(chart_path_overrides=None):
    """
    Return current state using the versions recorded in the parent chart dependencies
    for inferring subchart bumps.
    """
    if chart_path_overrides is None:
        chart_path_overrides = {}

    submodules = get_submodules()
    submodule_chart_path_overrides = chart_path_overrides.get("submodule_charts", {})
    parent_chart_path = chart_path_overrides.get("repo_chart", default_chart_location)

    # Compute bumps from current versions in parent chart dependencies
    subchart_bumps = compute_subchart_bumps_from_parent(parent_chart_path, submodule_chart_path_overrides)

    updates = {}
    for name, path in submodules.items():
        chart_rel_path = submodule_chart_path_overrides.get(name, default_chart_location)
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
        "suggested": bump_version(parent_current, repo_bump) if bump else parent_current,
        "chart_bump": repo_bump,
    }

    return updates, parent_info

def safe(v):
    return v if v is not None else "-"

def print_updates(updates, parent_info, output="cli", changes=None):
    """
    output: "cli", "json", "ci", None
    """
    if output == None:
        return

    if output == "json":
        data = {"parent": parent_info, "submodules": updates}
        if changes is not None:
            data["commited_changes"] = changes
        print(json.dumps(data, indent=2))
        return

    if output == "comment":
        lines = []
        lines.append(f"### Submodule updates")
        lines.append(
            "| Submodule | Current Tag | Suggested Tag | Current Chart | Suggested Chart | Chart Bump | Recent Tags |"
        )
        lines.append(
            "|-----------|------------|---------------|---------------|----------------|------|-------------|"
        )
        for name, info in updates.items():
            recent = ", ".join(info["recent_tags"][:5])
            lines.append(
                f"| {name} | {info['current_tag']} | {safe(info['suggested_tag'])} | "
                f"{info['current_tag_chart_version']} | {safe(info['suggested_tag_chart_version'])} | "
                f"{info['chart_bump'] or '-'} | {recent} |"
            )
        lines.append("")
        lines.append(
            f"**Parent chart:** {parent_info['current']} → {parent_info['suggested']} (chart bump: {parent_info['chart_bump'] or '-'})"
        )
        if changes is not None:
            if changes is True:
                lines.append(f"**Commited changes to this branch**")
            else:
                lines.append(f"**No changes in this branch**")
        print("\n".join(lines))
        return

    # CLI output
    print("Submodule updates (<git-tag> (<chart-version>)):")
    for name, info in updates.items():
        print(f"- {name}:")
        print(
            f"    Current tag: {info['current_tag']} ({info['current_tag_chart_version']})"
        )
        print(
            f"    Suggested tag: {safe(info['suggested_tag'])} ({safe(info['suggested_tag_chart_version'])})"
        )
        print(f"    Chart bump: {info['chart_bump'] or '-'}")
        print(f"    Recent tags: {', '.join(info['recent_tags'][:5])}")
    print(
        f"Parent chart: {parent_info['current']} → {parent_info['suggested']} (chart bump: {parent_info['chart_bump'] or '-'})"
    )
    if changes is None:
        return
    if changes is True:
        print("Commited changes to this branch")
    else:
        print("No changes in this branch")


# -------------------------
# Update submodules
# -------------------------
def apply_submodule_updates(updates, yes=False, quiet=False):

    for submodule, info in updates.items():
        if not quiet:
            print(f"\nProcessing submodule: {submodule}")

        current_tag = info["current_tag"]
        tags = info["recent_tags"]
        latest_tag = info["latest_tag"]
        suggested_tag = info["suggested_tag"]
        path = info["path"]

        if not quiet:
            print(f"  Current tag: {current_tag}")
            print(f"  Latest tag:  {latest_tag}")
            print(f"  Suggested tag: {suggested_tag}")

            print("  Available tags:")
            for i, t in enumerate(tags, start=1):
                print(f"   {i:2d}) {t}")

        if yes:
            ans = "s"
        else:
            ans = prompt(
                f"Update {submodule} to (s)uggested [{suggested_tag}], latest (l), skip (n), or manual index <number>? [s/l/n/<number>] ",
                "s",
            )

        if ans.lower() == "s":
            if quiet:
                run(f"git checkout -q {suggested_tag}", cwd=path)
            else:
                run(f"git checkout {suggested_tag}", cwd=path)
        elif ans.lower() == "l":
            if quiet:
                run(f"git checkout -q {latest_tag}", cwd=path)
            else:
                run(f"git checkout {latest_tag}", cwd=path)
        elif ans.isdigit() and 1 <= int(ans) <= len(tags):
            if quiet:
                run(f"git checkout -q {tags[int(ans)-1]}", cwd=path)
            else:
                run(f"git checkout {tags[int(ans)-1]}", cwd=path)

        else:
            print(
                f'Skipping submodule "{submodule}" because of unrecognized option "{ans}"'
            )

        run(f"git add {path}")


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


def parse_tag_overrides(tag_overrides_file_path, tag_overrides_arg):
    return parse_json_file(tag_overrides_file_path) | parse_json_arg(tag_overrides_arg)


# -------------------------
# Update distribution (Chart.yaml)
# -------------------------
def apply_distribution_updates(updates, parent_info, chart_path_overrides, quiet=False, no_backup=False):
    repo_chart = chart_path_overrides.get("repo_chart", default_chart_location)
    if not os.path.isfile(repo_chart):
        print(f"Repo chart not found: {repo_chart}", file=sys.stderr)
        sys.exit(1)

    if not no_backup:
        subprocess.run(f"cp {repo_chart} {repo_chart}.bak", shell=True)
    chart_data = load_yaml(repo_chart) 

    for info in updates.values():
        for dep in chart_data.get("dependencies", []):
            if dep["name"] == info["chart_name"]:
                dep["version"] = info["suggested_tag_chart_version"] or info["current_tag_chart_version"]

    if not quiet:
        print(f"Updating parent chart version: {chart_data.get("version")} -> {parent_info["suggested"]}")
    chart_data["version"] = parent_info["suggested"]

    dump_yaml(chart_data, repo_chart)


def parse_chart_path_overrides(
    chart_path_overrides, submodule_chart_paths_arg, repo_chart_path_arg
):
    file_overrides = parse_json_file(chart_path_overrides)
    submodule_chart_path_overrides = file_overrides.get(
        "submoduleCharts"
    ) | parse_json_arg(submodule_chart_paths_arg)

    repo_chart_path_override = (
        repo_chart_path_arg if repo_chart_path_arg else file_overrides.get("repoChart")
    )
    return {
        "repo_chart": repo_chart_path_override,
        "submodule_charts": submodule_chart_path_overrides,
    }

def commit_changes(message):
    """Commit all changes to git with the given message."""
    try:
        run("git add -A")
        run(f'git commit -m "{message}"', silent=True)
    except subprocess.CalledProcessError:
        return False

    return True

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

# -------------------------
# Main CLI
# -------------------------
def main():
    chart_args = argparse.ArgumentParser(add_help=False)
    chart_args.add_argument(
        "--repo-chart-path",
        help="Repo Chart.yaml path",
        default="",
    )
    chart_args.add_argument(
        "--submodule-chart-paths",
        help='Overrides for the submodule chart paths in JSON format \'{"subA": "path-in-A", "subB": "path-in-B"}\'',
        default="{}",
    )
    chart_args.add_argument(
        "--chart-path-overrides",
        help='File with overrides for chart paths in the format \'{ "repoChart": "path", "submoduleCharts": {...}}\'',
        default="chart-path-overrides.json",
    )
    chart_args.add_argument(
    "--state-file",
    help="Path to store/load fetch state JSON",
    default=".submodule_update_state.json",
    )
    chart_args.add_argument(
    "--use-state-file",
    action='store_true',
    help="Whether to use a state file",
    default=False,
    )

    chart_args.add_argument(
        "--force-refetch",
        action="store_true",
        help="Force refetching submodule updates instead of loading from state file",
        default=False,
    )

    chart_args.add_argument(
        "--no-backup",
        action="store_true",
        default=False,
        help="Do not create Chart.yaml backup"
    )


    output_args = argparse.ArgumentParser(add_help=False)
    output_args.add_argument(
        "-o",
        "--output",
        help="Print output formatted as CLI, JSON or GitHub comment",
        choices=["cli", "json", "comment"],
        default="cli",
    )

    commit_args = argparse.ArgumentParser(add_help=False)
    commit_args.add_argument(
        "-c",
        "--commit",
        action='store_true',
        help="Commit the changes",
        default=False
    )

    parser = argparse.ArgumentParser(description="Submodule release helper")
    parser.add_argument(
        "--submodule-tag-overrides",
        help='JSON array in the format \'{"subA": "latest", "subB": "v2"}\' with tags to be used as overrides for the suggested tags.',
    )
    parser.add_argument(
        "--submodule-tag-overrides-file",
        help='JSON file in the format \'{"subA": "latest", "subB": "v2"}\' with tags to be used as overrides for the suggested tags.',
        default="submodule-tag-overrides.json",
    )

    subparsers = parser.add_subparsers(dest="command")
    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Get submodule updates and corresponding chart changes",
        parents=[chart_args, output_args],
    )
    update_parser = subparsers.add_parser(
        "update",
        help="Update submodules and chart versions and commit",
        parents=[chart_args, output_args, commit_args],
    )

    format_parser = subparsers.add_parser(
        "format",
        help="Render JSON file or string in the desired format",
        parents=[output_args],
    )
    format_parser.add_argument(
        "-f",
        "--file",
        help="Use file contents instead of STDIN",
    )

    parser_submodule = subparsers.add_parser(
        "submodule",
        help="Update submodules and commit",
    )
    parser_submodule_subparsers = parser_submodule.add_subparsers(
        dest="submodule_command"
    )
    submodule_update_parser = parser_submodule_subparsers.add_parser(
        "update",
        parents=[commit_args],
        help="Update submodules and commit"
    )
    submodule_update_parser.add_argument(
        "-a",
        "--accept",
        action="store_true",
        help="Accept all suggested tags. Either the tag defined in the mappings or the latest tag.",
    )

    parser_distribution = subparsers.add_parser(
        "distribution",
        help="Update chart versions and commit",
    )
    parser_distribution_subparsers = parser_distribution.add_subparsers(
        dest="distribution_command",
    )
    distribution_update_parser = parser_distribution_subparsers.add_parser(
        "update", help="Update distribution versions", parents=[chart_args, commit_args]
    )

    args = parser.parse_args()

    submodule_tag_overrides = parse_tag_overrides(
        args.submodule_tag_overrides_file, args.submodule_tag_overrides
    )
    chart_path_overrides = {}
    match (args.command):
        case "fetch", "update", "distribution":
            chart_path_overrides.update(
                parse_chart_path_overrides(
                    args.chart_path_overrides,
                    args.submodule_chart_paths,
                    args.repo_chart_path,
                )
            )
        case _:
            pass

    match (args.command):
        case "format":
            if args.file:
                with open(args.file, "r") as f:
                    raw = f.read()
            else:
                raw = sys.stdin.read()

            if not raw.strip():
                print("No input provided.", file=sys.stderr)
                sys.exit(1)

            try:
                data = json.loads(raw)
            except json.JSONDecodeError as e:
                print(f"Invalid JSON: {e}", file=sys.stderr)
                sys.exit(1)

            print_updates(data.get("submodules"), data.get("parent"), args.output, data.get("commited_changes"))
        
        case "fetch":
            updates, parent_info = fetch_updates(
                submodule_tag_overrides, chart_path_overrides
            )
            print_updates(updates, parent_info, args.output)
            if args.use_state_file:
                save_state(updates, parent_info, args.state_file)

        case "update":
            if args.use_state_file and args.state_file and not args.force_refetch and os.path.isfile(args.state_file):
                updates, parent_info = load_state(args.state_file)
                if updates is None or parent_info is None:
                    print(f"State file {args.state_file} is invalid", file=sys.stderr)
                    sys.exit(1)
            else:
                updates, parent_info = fetch_updates(submodule_tag_overrides, chart_path_overrides)
                if args.use_state_file:
                    save_state(updates, parent_info, args.state_file)

            apply_submodule_updates(updates, True, True)
            apply_distribution_updates(updates, parent_info, chart_path_overrides, True, args.no_backup)
            new_updates, new_parent_info = fetch_updates(submodule_tag_overrides, chart_path_overrides)
            if args.use_state_file:
                save_state(new_updates, new_parent_info, args.state_file)
            changed = None
            if (args.commit):
                changed = commit_changes("Update submodules and chart versions")
            print_updates(updates, parent_info, args.output, changed)

        case "submodule":
            match (args.submodule_command):
                case "update":
                    updates, parent_info = fetch_updates(submodule_tag_overrides, chart_path_overrides)
                    apply_submodule_updates(
                        updates, yes=args.accept
                    )
                    if (args.commit):
                        commit_changes("Update submodules")
                case _:
                    print("Unknown or missing command")
                    parser_submodule.print_help()

        case "distribution":
            match (args.distribution_command):
                case "update":
                    updates, parent_info = get_current_status_from_parent_chart(chart_path_overrides)
                    apply_distribution_updates(updates, parent_info, chart_path_overrides)
                    if (args.commit):
                        commit_changes("Update parent chart versions")
                case _:
                    print("Unknown or missing command")
                    distribution_update_parser.print_help()

        case _:
            print("Unknown or missing command")
            parser.print_help()


if __name__ == "__main__":
    main()
