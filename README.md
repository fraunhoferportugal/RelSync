# RelSync — Release Synchronizer

RelSync is a command-line tool for preparing and managing releases across repositories that use Git submodules.

It automates updating submodules, Helm charts, and distribution manifests, ensuring release artifacts are consistent and up to date.

## Features

- Fetch submodule updates:
    - Detects new tags for each submodule.
    - Compares chart versions and infers semantic version bumps (patch, minor, major).
- Update repository artifacts:
    - Updates submodules to the suggested tags.
    - Updates distribution charts with correct dependency versions.
    - Optional automatic commit of changes.
- Flexible configuration:
    - Override tag selections and chart paths via JSON.
    - Save and reuse fetch state between runs.
    - Output in CLI, JSON, or Markdown formats (for PR comments).


## Requirements
- Python 3.8 or higher
- Git
- PyYAML (recommended) or yq v4+ for YAML parsing

## Installation
Clone the repository and make the script executable:
```bash
git clone <repo-url>
cd relsync
chmod +x relsync
```

Optionally, install dependencies:
```bash
pip install pyyaml
```

Run the script directly:
```bash
./relsync --help
```

## Usage
### Fetch Submodule Updates
Collect the latest tags and chart versions:
```bash
./relsync fetch -o cli
```

Output formats:
- cli — human-readable interactive output
- json — machine-readable output
- comment — Markdown table suitable for PR comments

Example:
```bash
./relsync fetch -o json
./relsync fetch -o comment
```

### Update Submodules and Distribution Chart
Update all submodules to suggested tags, adjust dependency versions, and optionally commit changes:
```bash
./relsync update --commit
```

### Update Only Submodules
Interactively choose tags for each submodule or accept all suggested ones:
```bash
./relsync submodule update --accept --commit
```

### Update Only Distribution Chart
Update the parent chart to reflect current submodule versions:
```bash
./relsync distribution update --commit
```

## Configuration
### Submodule Tag Overrides
Override suggested tags for specific submodules via a JSON file or CLI argument.

**File** (`submodule-tag-overrides.json`):
```json
{
  "api": "v2.0.0",
  "ui": "v1.5.1"
}
```
**CLI argument**:
```bash
./relsync fetch --submodule-tag-overrides '{"api":"v2.0.0","ui":"v1.5.1"}'
```
### Chart Path Overrides
Override default chart locations:

**CLI arguments**:
```bash
./relsync fetch \
  --repo-chart-path charts/main/Chart.yaml \
  --submodule-chart-paths '{"api":"charts/api/Chart.yaml","ui":"charts/ui/Chart.yaml"}'
```

**File** (`chart-path-overrides.json`):
```json
{
  "repoChart": "charts/main/Chart.yaml",
  "submoduleCharts": {
    "api": "charts/api/Chart.yaml",
    "ui": "charts/ui/Chart.yaml"
  }
}
```

### Using State Files
Save fetch results for later reuse (e.g., in CI pipelines):
```bash
./relsync fetch --use-state-file
./relsync update --use-state-file
```

Default state file location: `.submodule_update_state.json.`

## Example Workflow
```bash
# Fetch updates
./relsync fetch -o comment --use-state-file > release-summary.md

# Review suggested updates
cat release-summary.md

# Apply updates and commit
./relsync update --commit --use-state-file
```

## Output Formats
- cli — human-readable interactive output
- json — machine-readable output
- comment — Markdown table suitable for GitHub/GitLab comments

### Example Markdown output:

#### Submodule updates
| Submodule | Current Tag | Suggested Tag | Current Chart | Suggested Chart | Chart Bump | Recent Tags |
|-----------|-------------|---------------|---------------|----------------|------------|-------------|
| api       | v1.2.0      | v1.3.0        | 1.2.0         | 1.3.0          | minor      | v1.3.0, v1.2.0, v1.1.0 |
| ui        | v0.9.0      | v1.0.0        | 0.9.0         | 1.0.0          | major      | v1.0.0, v0.9.0, v0.8.0 |

**Parent chart:** 1.5.0 → 2.0.0 (chart bump: major)

## CLI Reference
### Global Options
| Option | Description | Default |
| --- | --- | --- |
| --submodule-tag-overrides | JSON string specifying tag overrides for submodules | None |
|--submodule-tag-overrides-file | JSON file with tag overrides | submodule-tag-overrides.json |
|--repo-chart-path | Path to parent Chart.yaml | dist/chart/Chart.yaml |
|--submodule-chart-paths | JSON string mapping submodules to chart paths | {} |
|--chart-path-overrides | JSON file for chart path overrides | chart-path-overrides.json |
|--state-file | Path to save/load state | .submodule_update_state.json |
|--use-state-file | Use the state file to avoid re-fetching | False |
|--force-refetch | Force refetching submodule updates | False |
|-o, --output | Output format (cli, json, comment) | cli |
|-c, --commit | Commit changes after updating | False |


### Commands
`fetch`\
Fetch submodule updates and calculate suggested chart version bumps.
```bash
./relsync fetch [options]
```
Options inherited from global options.

`update`\
Update submodules, distribution charts, and optionally commit changes.
```bash
./relsync update [options]
```
Options inherited from global options.

`submodule update`\
Update submodules only. Can accept all suggested tags.
```bash
./relsync submodule update [options]
```
Options:
| Option | Description |
| --- | --- |
|-a, --accept | Automatically accept all suggested tags |
|-c, --commit | Commit the changes |

`distribution update`\
Update the parent chart to reflect submodule versions.
```bash
./relsync distribution update [options]
```
Options:
| Option | Description |
| --- | --- |
|-c, --commit | Commit the changes |
