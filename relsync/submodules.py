from .utils import parse_json_arg, parse_json_file, prompt, run


def parse_tag_overrides(tag_overrides_file_path, tag_overrides_arg):
    return parse_json_file(tag_overrides_file_path) | parse_json_arg(tag_overrides_arg)


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
