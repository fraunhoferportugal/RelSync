import os

from .utils import *

default_chart_dir = "deploy/chart"
default_chart_location = f"{default_chart_dir}/Chart.yaml"
default_values_location = f"{default_chart_dir}/values.yaml"


def apply_distribution_updates(
    updates, parent_info, chart_path_overrides, quiet=False, no_backup=False
):
    repo_chart = chart_path_overrides.get("repo_chart")
    if not os.path.isfile(repo_chart):
        print(f"Repo chart not found: {repo_chart}", file=sys.stderr)
        sys.exit(1)

    if not no_backup:
        subprocess.run(f"cp {repo_chart} {repo_chart}.bak", shell=True)
    chart_data = load_yaml(repo_chart)

    for info in updates.values():
        for dep in chart_data.get("dependencies", []):
            if dep["name"] == info["chart_name"]:
                dep["version"] = (
                    info["suggested_tag_chart_version"]
                    or info["current_tag_chart_version"]
                )

    if not quiet:
        print(
            f"Updating parent chart version: {chart_data.get("version")} -> {parent_info["suggested"]}"
        )
    chart_data["version"] = parent_info["suggested"]

    dump_yaml(chart_data, repo_chart)


def parse_chart_path_overrides(
    chart_path_overrides, submodule_chart_paths_arg, repo_chart_path_arg
):
    file_overrides = parse_json_file(chart_path_overrides)
    submodule_chart_path_overrides = parse_json_arg(
        submodule_chart_paths_arg
    ) or file_overrides.get("submoduleCharts", {})

    repo_chart_path_override = (
        repo_chart_path_arg if repo_chart_path_arg else file_overrides.get("repoChart")
    )
    return {
        "repo_chart": (
            repo_chart_path_override
            if repo_chart_path_override
            else default_chart_location
        ),
        "submodule_charts": submodule_chart_path_overrides,
    }
