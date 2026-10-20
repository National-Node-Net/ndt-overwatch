# OSPO governance report

Scans every active (non-archived) repository in the organisation except the organisation-level `.github` repository.
The dashboard includes a summary, a repository-by-check matrix, and detailed findings for each repository.

The [workflow](../../.github/workflows/governance-report.yml) runs on pushes to `feature/governance-report` for pre-merge testing, weekly (Monday 07:17 UTC), and on demand.
It checks out `National-Node-Net/ospo-resources` `develop` to use the centrally maintained file lists, workflow manifest and Dependabot policies.
The Markdown dashboard is shown in the run's job summary. The artifact includes `dashboard.md`,
`dashboard.html` and `report.json` (kept for 90 days). The HTML dashboard has colored status text and
a responsive matrix; it inherits the browser font and does not set a font family.

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
| Allow auto-merge | `allow_auto_merge` repository setting | FAIL if off |
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
| `NODE_NET_REPOSITORY_READER_APP_*` | Repository list, files, releases, branches, commits and Actions runs | Contents: read, Metadata: read, Actions: read |
| `NODE_NET_PULL_REQUEST_CONTROLLER_APP_*` | Listing PRs and posting reminders | Pull requests: write |

Both apps must be installed on all repositories; repositories the reader app cannot see are not reported.
`delete_branch_on_merge` is only returned with Administration: read, which the reader app does not have,
so that column shows N/A until that permission is granted.
The merge-back check similarly shows N/A until the repository-reader App has Actions: read; its current installation does not have that permission.

Actions must be enabled in `ndt-overwatch` for the workflow to run. The repository-reader App's credentials must be available as organisation Actions secrets and the App must be installed with access to the repositories being scanned and `ospo-resources`.
The TruffleHog scan needs Docker and a token that can read every selected repository. Its output is captured,
parsed for verified finding counts, and never written to logs or artifacts. In local usage it can read
`GH_TOKEN`/`GITHUB_TOKEN` or use `gh auth token`; TruffleHog's GitHub source documents classic PAT support.
The merge-back check shows N/A unless the reader App is granted Actions: read. The branch-setting checks need Administration: read to expose `delete_branch_on_merge`.

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
