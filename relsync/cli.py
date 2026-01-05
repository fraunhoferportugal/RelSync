#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys

from .distribution import *
from .git import *
from .helm import *
from .semver import *
from .submodules import *
from .utils import *


def fetch_updates(
    submodule_tag_overrides,
    chart_path_overrides,
    prerelease_identifier=None,
):
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
                print(
                    f"Error: cannot read {chart_rel_path} at tag {suggested_tag} in submodule {name} ({path})",
                    file=sys.stderr,
                )
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
    (repo_current, repo_base) = get_chart_version(repo_chart, True)
    repo_bump = (
        "minor"
        if bump_type and bump_priority[bump_type] > 2
        else "patch" if bump_type else None
    )
    repo_suggested = (
        bump_version(repo_base, repo_bump)
        if repo_bump
        else ".".join(str(x) for x in parse_version(repo_base))
    )

    if prerelease_identifier is not None:
        prerelease = parse_version(repo_current, VersionGroup.PRERELEASE)
        if parse_version(repo_suggested) > parse_version(repo_current):
            repo_suggested = f"{repo_suggested}-{prerelease_identifier}"
        elif prerelease and prerelease_identifier in prerelease:
            prerelease_number = 0
            parts = prerelease.split(".")
            if len(parts) > 1 and parts[-1].isdigit():
                prerelease_number = int(parts[-1])
            repo_suggested = f"{".".join(str(x) for x in parse_version(repo_current))}-{prerelease_identifier}.{prerelease_number+1}"
        else:
            repo_suggested = f"{repo_suggested}-{prerelease_identifier}"

    return updates, {
        "current": repo_current,
        "suggested": repo_suggested,
        "chart_bump": repo_bump,
    }


def print_updates(updates, parent_info, output="cli", changes=None):
    """
    output: "cli", "json", "ci", None
    """
    if output == None:
        return

    if output == "json":
        data = {"parent": parent_info, "submodules": updates}
        if changes is not None:
            data["committed_changes"] = changes
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
                lines.append(f"**Committed changes to this branch**")
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
        print("Committed changes to this branch")
    else:
        print("No changes in this branch")


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
        action="store_true",
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
        help="Do not create Chart.yaml backup",
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
        "-c", "--commit", action="store_true", help="Commit the changes", default=False
    )
    commit_args.add_argument("-m", "--commit-message", help="Commit message")

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
    update_parser.add_argument(
        "--prerelease-identifier",
        help="Add a prerelease identifier to the helm chart version. Follows the format <next-version>-<identifier>(.nr-of-the-update)",
        default=None,
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
        "update", parents=[commit_args], help="Update submodules and commit"
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

    tag_parser = subparsers.add_parser(
        "bump",
        help="Bump the version of repository",
        parents=[chart_args, commit_args, output_args],
    )
    tag_parser.add_argument(
        "bump_type",
        help="The bump to apply to the repo",
        choices=["major", "minor", "patch", "release"],
        default="patch",
    )
    tag_parser.add_argument("-t", "--create-tag", action="store_true")
    tag_parser.add_argument(
        "--skip-repo-bump",
        help="Skip bumping the repo version for chart only changes",
        action="store_true",
        default=False,
    )
    tag_parser.add_argument(
        "--chart-bump-type",
        help="The bump type to apply to the chart",
        choices=["major", "minor", "patch", "release"],
        default="patch",
    )
    tag_parser.add_argument(
        "--no-chart",
        action="store_true",
        help="Use if this repo does not contain a chart",
        default=False,
    )

    args = parser.parse_args()

    submodule_tag_overrides = parse_tag_overrides(
        args.submodule_tag_overrides_file, args.submodule_tag_overrides
    )
    chart_path_overrides = {}
    match (args.command):
        case "fetch" | "update" | "distribution" | "bump":
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

            print_updates(
                data.get("submodules"),
                data.get("parent"),
                args.output,
                data.get("committed_changes"),
            )

        case "fetch":
            updates, parent_info = fetch_updates(
                submodule_tag_overrides, chart_path_overrides
            )
            print_updates(updates, parent_info, args.output)
            if args.use_state_file:
                save_state(updates, parent_info, args.state_file)

        case "update":
            if (
                args.use_state_file
                and args.state_file
                and not args.force_refetch
                and os.path.isfile(args.state_file)
            ):
                updates, parent_info = load_state(args.state_file)
                if updates is None or parent_info is None:
                    print(f"State file {args.state_file} is invalid", file=sys.stderr)
                    sys.exit(1)
            else:
                updates, parent_info = fetch_updates(
                    submodule_tag_overrides,
                    chart_path_overrides,
                    prerelease_identifier=args.prerelease_identifier,
                )
                if args.use_state_file:
                    save_state(updates, parent_info, args.state_file)

            apply_submodule_updates(updates, True, True)
            apply_distribution_updates(
                updates,
                parent_info,
                chart_path_overrides,
                True,
                args.no_backup,
                prerelease_identifier=args.prerelease_identifier,
            )
            new_updates, new_parent_info = fetch_updates(
                submodule_tag_overrides, chart_path_overrides
            )
            if args.use_state_file:
                save_state(new_updates, new_parent_info, args.state_file)
            changed = None
            if args.commit:
                changed = commit_changes("Update submodules and chart versions")
            print_updates(updates, parent_info, args.output, changed)

        case "submodule":
            match (args.submodule_command):
                case "update":
                    updates, parent_info = fetch_updates(
                        submodule_tag_overrides, chart_path_overrides
                    )
                    apply_submodule_updates(updates, yes=args.accept)
                    if args.commit:
                        commit_changes("Update submodules")
                case _:
                    print("Unknown or missing command")
                    parser_submodule.print_help()

        case "distribution":
            match (args.distribution_command):
                case "update":
                    updates, parent_info = get_current_status_from_parent_chart(
                        chart_path_overrides
                    )
                    apply_distribution_updates(
                        updates, parent_info, chart_path_overrides
                    )
                    if args.commit:
                        commit_changes("Update parent chart versions")
                case _:
                    print("Unknown or missing command")
                    distribution_update_parser.print_help()
        case "bump":
            if args.create_tag and not args.commit and not args.no_chart:
                print(
                    'WARNING: Running with "--create-tag" without "--commit" only prints the versions if the "--no-chart" option is not used.'
                )

            latest_tag = get_latest_tag()
            app_version = get_version_string(latest_tag)
            if not args.skip_repo_bump:
                app_version = bump_version(latest_tag, args.bump_type)

            chart_version = None
            if not args.no_chart:
                chart_version = bump_chart_version(
                    args.chart_bump_type, app_version, args.commit, chart_path_overrides
                )

            new_tag = None
            if args.commit and args.create_tag:
                if not args.no_chart:
                    if args.skip_repo_bump:
                        message = (
                            args.commit_message
                            if args.commit_message
                            else "Update chart version"
                        )
                        commit_changes(message)
                        new_tag = f"{app_version}+chart{chart_version}"
                        run(f"git tag {new_tag}")
                    else:
                        message = (
                            args.commit_message
                            if args.commit_message
                            else "Update app and chart versions"
                        )
                        commit_changes(message)
                        new_tag = app_version
                        run(f"git tag {new_tag}")
            if args.no_chart:
                message = (
                    args.commit_message
                    if args.commit_message
                    else "Update app versions"
                )
                new_tag = app_version
                run(f"git tag {new_tag}")

            match (args.output):
                case "json":
                    output = {
                        "appVersion": app_version,
                        "chartVersion": chart_version,
                        "newTag": new_tag,
                    }
                    print(json.dumps(output))

                case "cli" | "comment" | _:
                    print(f"Repo version: {app_version}")
                    print(f"Chart Version: {safe(chart_version)}")
                    print(f"New tag: {safe(new_tag)}")

        case _:
            print("Unknown or missing command")
            parser.print_help()


if __name__ == "__main__":
    main()
