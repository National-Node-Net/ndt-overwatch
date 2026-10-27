# OSPO governance report

Scans active (non-archived) repositories except those listed in `excluded-repositories.txt` and any additional runtime exclusions.
The dashboard includes a summary, separate public and private/internal repository-by-check matrices,
and detailed findings for each repository.

The [workflow](../../.github/workflows/governance-report.yml) runs on pushes to `feature/governance-report` for pre-merge testing, weekly (Monday 07:17 UTC), and on demand.
It checks out `National-Node-Net/ospo-resources` `develop` into `ospo-resources` for the centrally maintained
file checklists and Dependabot policies, including groups. An independent checkout of `main` into
`ospo-workflows` supplies only the published workflow manifest and workflow files for synchronization comparisons.
Workflows listed only on `develop` (such as `stale-pr-alerts.yml` before publication) are not required by this comparison.
The Markdown dashboard is shown in the run's job summary. The artifact includes `dashboard.md`,
`dashboard.html` and `report.json` (kept for 90 days). The HTML dashboard has colored status text and
a responsive matrix; it inherits the browser font and does not set a font family.
GitHub job summaries strip inline CSS, so Markdown uses static Shields.io status badges:
green OK, amber WARN, red FAIL/ERROR, grey N/A. Badge requests contain only fixed status labels and colors,
not repository names or results. Result descriptions use nested sub/sup markup for two relative size reductions;
the HTML equivalent uses 75% text. GitHub controls the final Markdown typography, not arbitrary pixel sizes.

## Feature-branch README badges

The root README embeds three SVGs stored in [`.github/badges`](../../.github/badges).
This pilot writes only to `feature/governance-report`; it neither publishes to `main`/`develop`
nor distributes a workflow to other repositories. Initial assets are amber placeholders, not demo results.

- **OSPO compliance:** green only when every expected, applicable check passes, no processing errors exist,
	and the qualifying `develop` commit is within the report's `dormant_days` threshold (currently 180).
	WARN, FAIL, ERROR, missing checks, or unavailable N/A results stay amber. Only explicitly marked
	non-applicable N/A checks (currently SBOM when there are no releases) are excluded.
- **Develop activity:** whole days from the last qualifying human commit on `develop` to scan completion.
	Uses the existing bot/merge/governance filters and repository exceptions. Work-branch activity cannot
	reset this age. Missing `develop` or unavailable commit data shows `unknown`, not default-branch age.
- **Last checked:** actual scan completion time in UTC, not workflow start or badge publication time.
	The color indicates age regardless of check findings: green when the report is less than three days old,
	amber from three through eight days inclusive, and red when it is more than eight days old. Missing or
	invalid timestamps are red. Compliance pass/fail is shown separately.

The existing report still checks governance files and workflows on each repository's default branch;
these badges are results for `ndt-overwatch`, not a claim that the feature-branch tree passed those checks.
No organisation-wide or private-repository findings are copied into the badge assets.

After the report, `governance_badges.py` generates the images even when the report job reports processing
errors; errors cannot produce an overall green badge. If no JSON was produced, images show `not checked`.
A separate job downloads only the three SVGs and uses the repository `GITHUB_TOKEN` with Contents: write
to commit them to the feature branch. It skips if the branch moved, never force-pushes, and stages no report
data. GitHub branch rules still apply. The report job remains Contents: read; the settings App token remains
GET-only. Bot badge commits do not count as human development activity or retrigger the push workflow.

Badges update on the existing feature-branch push runs, not nightly. GitHub scheduled runs use the default
branch, so scheduling is unchanged for this feature-only pilot. Static SVGs cannot expire or increment age
when a workflow stops; their color bands are recalculated only when another run regenerates the SVG, so read
the timestamp and use separate monitoring if the workflow itself stops.

`governance_badges.py` also accepts `--report PATH --repository OWNER/NAME --output-dir PATH` locally.
Omitting `--report` generates the initial placeholders. Existing malformed reports generate placeholders
and a nonzero exit code; a legacy report without a completion timestamp is not presented as newly checked.

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
| Activity | Exact days since the latest qualifying human commit to `develop` (or the default branch); excludes bots, `OSPO` in the subject/body, and governance-only file changes | WARN if over 180 days and no active human work branch |
| OSPO workflows | Workflows listed in `organisation-required-workflows.txt` on `National-Node-Net/ospo-resources` `main` exist on each repository's default branch and match the published `main` workflow files byte for byte | FAIL if missing, WARN if out of sync |
| Main-to-develop back-merge | Latest actual run of `.github/workflows/auto-back-merge.yml`; skipped runs from closed, unmerged PRs are ignored | OK if passed, FAIL if failed, WARN if running/other conclusion, N/A if no run or Actions history is not visible |

The report's Legend section lists all governance-file and template paths, the Dependabot policy rules,
and the PR/activity thresholds. The Python script uses no AI or LLM.

Bot commits are those whose author name or login ends in `[bot]`.

### Governance-only activity exclusions

[`governance-only-paths.txt`](governance-only-paths.txt) lists repository-relative, case-sensitive glob patterns.
It currently covers `.github/**`, licences and standard root governance documents (including changelog).
README and application documentation are not excluded. Blank lines and `#` comment lines are ignored.
A commit is ignored only when all changed paths match; mixed project/governance commits count as activity.
Renames check both the original and new paths. Empty commits do not count as project activity.
The same filter applies to develop/default-branch age and work-branch history. The scanner pages past
governance-only commits, caches commit classifications, and reports an error if file history cannot be
classified completely rather than assuming the repository is active.
Merge commits do not refresh activity age; the original commits in their ancestry are evaluated instead.

[`governance-activity-repositories.txt`](governance-activity-repositories.txt) lists repositories whose
purpose is governance. It currently contains `ospo-resources`, `ndt-overwatch`, and `private-ospo-resources`.
Human OSPO commits and governance-only file changes count as activity in those repositories, on both
develop/default and work branches. Bot commits (including Dependabot and OSPO Apps) and merge commits
remain excluded. All other repositories retain the stricter OSPO/governance-only exclusions.

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
Prepare separate `ospo-resources` checkouts: `develop` for `--source-root` and published `main` for
`--workflow-source-root`. The latter defaults to `<report repository root>/ospo-workflows`, never to
`--source-root`. A missing workflow checkout, manifest, or listed source workflow stops the scan before API calls.

```bash
python3 tools/governance-report/governance_report.py --org National-Node-Net --source-root /path/to/ospo-resources-develop --workflow-source-root /path/to/ospo-resources-main --output-dir /tmp/governance-report
python3 tools/governance-report/governance_report.py --org National-Node-Net --source-root /path/to/ospo-resources-develop --workflow-source-root /path/to/ospo-resources-main --repo node-lib --repo opa-pov
python3 -m unittest discover -s tools/governance-report
```

## Not covered

- Dependabot, code scanning and secret scanning alert counts: need an app with Dependabot alerts and security events read permission.
- Ruleset bypass actors, organisation admin count and member activity.
