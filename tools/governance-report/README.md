# OSPO governance report

Scans active (non-archived) repositories except those listed in `excluded-repositories.txt` and any additional runtime exclusions.
The dashboard includes a summary, separate public and private/internal repository-by-check matrices,
and detailed findings for each repository.

The [workflow](../../.github/workflows/governance-report.yml) runs on pushes to `feature/governance-report` for pre-merge testing, weekly (Monday 07:17 UTC), and on demand.
It checks out `National-Node-Net/ospo-resources` `develop` to use the centrally maintained file lists, workflow manifest and Dependabot policies.
The Markdown dashboard is shown in the run's job summary. The artifact includes `dashboard.md`,
`dashboard.html` and `report.json` (kept for 90 days). The HTML dashboard has colored status text and
a responsive matrix; it inherits the browser font and does not set a font family.
GitHub job summaries strip inline CSS, so Markdown uses static Shields.io status badges:
green OK, amber WARN, red FAIL/ERROR, grey N/A. Badge requests contain only fixed status labels and colors,
not repository names or results. Result descriptions use nested sub/sup markup for two relative size reductions;
the HTML equivalent uses 75% text. GitHub controls the final Markdown typography, not arbitrary pixel sizes.

## Repository exclusions

- Edit [`excluded-repositories.txt`](excluded-repositories.txt) to maintain exclusions without changing Python.
	It currently lists `.github` and `opa-pov`, one repository per line. Blank lines and `#` comment lines are ignored.
- Local runs may select another list with `--exclusions-file /path/to/list.txt`. An unreadable or invalid file stops the scan.
- For scheduled and push runs, set repository Actions variable `GOVERNANCE_EXCLUDED_REPOS` to a
	comma- or whitespace-separated list such as `repo-one, repo-two`.
- Manual runs have an optional `excluded_repos` input, which overrides that variable when nonempty.
	Runtime exclusions are added to the file's list; they do not replace it.
- Local runs accept `--exclude-repos "repo-one, repo-two"`. Names are case-insensitive; `Org/repo` is also
	accepted when it belongs to the scanned organisation. URLs and wildcard patterns are rejected.
- Exclusions apply before credential scans, checks, reminders, and summary totals. Excluded repositories
	are listed separately for auditability; their findings are not reported.

## Checks

| Column | Check | Status |
| --- | --- | --- |
| develop branch | `develop` exists where the default branch is `main` | FAIL if missing |
| Required files | `oss-checklist-files.txt` (public) or `private-ospo-resources/inner-source-checklist-files.txt` (private/internal), including `LICENSE.md` | FAIL if any missing |
| PR/issue templates | Same paths as the OSS checker | FAIL if any missing |
| Dependabot config | `.github/dependabot.yml` evaluated with Conftest against `tools/policy-as-code` (`github.dependabot`: target branch and groups) | FAIL if missing or a policy fails |
| Dependabot PRs | Open Dependabot PRs older than the threshold (default 14 days) | WARN if stale, FAIL if older than 90 days |
| Human PRs | Open non-bot PRs older than the threshold (default 30 days); flags drafts and PRs targeting `main` from non-release branches | WARN if stale; no separate FAIL threshold |
| Credential scan | Pinned TruffleHog scan of explicitly selected active repositories, verified results only | FAIL if verified findings; values and locations are never stored |
| Release SBOM | Releases published in the window (default 90 days, otherwise the latest release) have an `*.spdx.json` or `*sbom*` asset | FAIL if missing |
| Auto-delete branches | `delete_branch_on_merge` | FAIL if off, N/A if the token cannot see it |
| Dependabot GitHub Actions auto-merge workflow | Latest applicable `auto-merge-dependabot-pull-requests.yml` run and its job steps; ignores human PR skips and non-GitHub-Actions update skips | OK only if the auto-merge enablement step succeeded; FAIL if missing/failed; WARN if running or unconfirmed; N/A if no applicable run or inaccessible history |
| Activity | Exact days since the latest human-authored commit to `develop` (or the default branch); excludes all bot-authored commits and any commit with `OSPO` anywhere in its subject or body | WARN if over 180 days and no active human work branch |
| OSPO workflows | Workflows listed in `organisation-required-workflows.txt` exist on each repository's default branch and match this checkout byte for byte | FAIL if missing, WARN if out of sync |
| Main-to-develop back-merge | Latest actual run of `.github/workflows/auto-back-merge.yml`; skipped runs from closed, unmerged PRs are ignored | OK if passed, FAIL if failed, WARN if running/other conclusion, N/A if no run or Actions history is not visible |

The report's Legend section lists all governance-file and template paths, the Dependabot policy rules,
and the PR/activity thresholds. The Python script uses no AI or LLM.

Bot commits are those whose author name or login ends in `[bot]`.

## PR reminders

Scheduled runs comment on stale, non-draft human PRs, mentioning the author. A PR is not reminded
again within six days of the last reminder from the same app (hidden marker
`<!-- ospo-stale-human-pr-reminder -->`). Manual runs only report. Nothing is merged, closed or deleted.

## Permissions

| Token | Used for | App permissions |
| --- | --- | --- |
| `NODE_NET_REPOSITORY_READER_APP_PRIVATE_KEY` | Repository list, files, releases, branches, commits and Actions runs; App ID is public metadata pinned in the workflow | Contents: read, Metadata: read, Actions: read |
| `NODE_NET_PULL_REQUEST_CONTROLLER_APP_PRIVATE_KEY` | Listing PRs and posting reminders; App ID is public metadata pinned in the workflow | Pull requests: write |
| `NODE_NET_REPOSITORY_WRITER_APP_PRIVATE_KEY` | GET repository settings only, via `SETTINGS_TOKEN`; token requests Contents only, no Workflows write | Contents: write |

The apps must be installed on the target repositories; repositories the reader app cannot see are not reported.
GitHub requires Contents: write to expose merge-related settings, even for GET requests.
The writer token is used only by the cached repository-settings GET; no settings are changed.
The merge-back and Dependabot auto-merge workflow checks need Actions: read for private run history and job steps.
Successful enablement means GitHub accepted an auto-merge request; it does not prove the PR has already merged.

Actions must be enabled in `ndt-overwatch` for the workflow to run. The repository-reader App's credentials must be available as organisation Actions secrets and the App must be installed with access to the repositories being scanned and `ospo-resources`.
The TruffleHog scan needs Git, Docker and a token that can read every selected repository.
Git clones each repository with full history and no checkout into a temporary directory using the reader token, supplied only through
process environment configuration (never URL arguments or persisted Git config). TruffleHog scans the clone
using its `git` source rather than its user-token-based `github` source. The scanner container receives a
read-only mount and no GitHub token. Temporary clones and containers are removed after each scan.
Output is parsed for verified finding counts and never written to logs or artifacts. Malformed output,
clone failures, unavailable prerequisites and scanner errors fail the job after saving the report; findings
remain FAIL results rather than processing errors. A green job must not hide incomplete credential scans.
Locally, authentication can use `GH_TOKEN`/`GITHUB_TOKEN`, `gh auth token`, or the Git credential helper.
The merge-back check shows N/A unless the reader App is granted Actions: read.

### Manual runs from a branch

GitHub only enables `workflow_dispatch` after this workflow file exists on the repository's default branch (`main`).
After it reaches `main`, select `OSPO governance report`, choose the branch in the **Run workflow** branch selector,
and start it. The selected branch must also contain this workflow and the report code. Manual runs are report-only;
only scheduled runs post stale-human-PR reminders.

## Run locally

Requires Python 3, the GitHub CLI authenticated with read access to the organisation, and optionally
Conftest on `PATH`. Local runs never post comments unless `--post-reminders` is given.

```bash
python3 tools/governance-report/governance_report.py --org National-Node-Net --source-root /path/to/ospo-resources --output-dir /tmp/governance-report
python3 tools/governance-report/governance_report.py --org National-Node-Net --source-root /path/to/ospo-resources --repo node-lib --repo opa-pov
python3 -m unittest discover -s tools/governance-report
```

## Not covered

- Dependabot, code scanning and secret scanning alert counts: need an app with Dependabot alerts and security events read permission.
- Ruleset bypass actors, organisation admin count and member activity.
