# OSPO governance report

The weekly central scan checks active repositories in National-Node-Net and publishes a dashboard for public and private repositories. It also scans repository history for verified credentials. Credential values and locations are never included in the report.

## Schedule and results

The [workflow](../../.github/workflows/governance-report.yml) runs Monday at 03:00 UTC, on pushes to `feature/governance-report`, and on demand. Per-repository badge scans are pinned to `develop` for now; manual runs offer only `develop`. A repository without `develop` is reported as unavailable rather than silently scanned on `main`. Required workflow synchronization compares each repository's scanned `develop` branch with the manifest and files on `ospo-resources/develop`; it does not wait for those files to be released to `main`. Switch both scan and synchronization baselines to `main` only when the organization is ready. Each report records the branch actually scanned. Scheduled runs also remind authors about stale, non-draft human pull requests; manual runs only report.

Each run adds a Markdown dashboard to the Actions summary and uploads `dashboard.md`, `dashboard.html`, and `report.json` as a 90-day artifact. The full report remains an artifact; it is not published to the badge branch.

## Historical overviews

Every successful scan execution creates a public-repository overview on the separate `history/governance` branch. This includes **push-triggered**, manual, and scheduled scans, so history does not have to wait for the cron workflow to reach `main`.

Scans and history publication are allowed from `feature/governance-report`, `develop`, and `main`. A manual dispatch on another ref is skipped before scanning, rather than producing a scan that cannot be archived. Push-triggered scans currently run on `feature/governance-report`; the existing Monday 03:00 UTC cron starts running when the workflow reaches the default branch. History-branch commits do not match the scan's push trigger, so archiving does not trigger a scan loop.

The history branch's root `README.md` indexes snapshots newest first. Each snapshot is stored at `snapshots/YYYY-MM-DD/run-<run-id>-attempt-<attempt>/README.md`, with three frozen SVG badges per public repository in its own `badges/` folder. The Markdown uses relative image links, so subsequent badge updates cannot change historical results. It records the scan completion time in UTC, scanned branch, source commit, event, and workflow run/attempt link. The overview is generated from that run's report and exact badge bytes rather than copying live image URLs from the repository README.

Snapshots are append-only: existing records are never pruned or replaced, identical publication retries are a no-op, conflicting duplicates fail, and rerunning a scan creates a separate attempt folder. Completed reports with FAIL or unknown check results are still archived; failed/incomplete scan executions do not publish a completed snapshot. Private/internal repository names, report JSON, processing details, and credentials are not committed. The history publishing job is independent of live badge publication, so it retains a completed scan even if the source branch has moved while it ran. The existing workflow concurrency group serializes archive writers. Publication requires `contents: write` on this repository and branch rules that permit the workflow to create/update `history/governance`; it never force-pushes or changes those rules.

## Badge results

The scan publishes status-only SVG badges for every included repository under `sync/governance-badges/repositories/<repo>/`. Individual repository READMEs and the central `ndt-overwatch` README use the same OSPO compliance badge mapping. The **OSPO compliance** badge combines these checks: develop branch, required governance files, templates, Dependabot configuration, open Dependabot PR age, open human PR age, verified credential scan, release SBOM, automatic branch deletion, current Dependabot auto-merge state, workflow synchronization, and main-to-develop back-merge. It deliberately excludes repository activity and scan freshness: those are shown by the separate **Days since last commit to develop branch** and **Last checked** badges. Badges are emitted as unknown/not checked unless that repository was scanned on `develop`. For compliance, a develop branch not required by a non-main default and no releases are non-applicable passes. Missing evidence for auto-merge/back-merge, an unevaluated Dependabot policy, or an unreadable repository setting stays unknown rather than being presented as a pass or failure. An unavailable credential scan remains a failure. The central report retains its raw status and reason. Badges contain no findings or report data.

### Develop commit-age colors and paused development

The **Days since last commit to develop branch** badge uses only the last qualifying Develop commit's age at scan completion, in whole days. It uses the report's `dormant_days` window (`--dormant-days`, currently 180): **green** at or below the window, **amber** above it. Unlike the broader activity check in the report, recent feature/release branch activity cannot turn an old Develop commit green. Existing exclusions for bots, merge commits, OSPO commit messages, and governance-only changes still apply to this badge.

Maintain intentionally paused repositories in [`paused-development-repositories.txt`](paused-development-repositories.txt), one repository name per line. Names are case-insensitive; blank lines and lines beginning with `#` are ignored. The badge CLI loads this file automatically, or accepts `--paused-repositories-file` for an alternative file. Listed repositories retain their numeric age but always use **gray**; missing, invalid, future-dated, or non-Develop activity also stays gray. The list starts empty: no repositories are assumed paused. Pausing changes only this badge's color, not scan inclusion, OSPO compliance, the report's broader activity check, or Last checked. Historical snapshots preserve the exact colors from each scan, even if the pause list changes later.

The **Dependabot Actions auto-merge workflow result** checks only the latest run conclusion for `.github/workflows/auto-merge-dependabot-pull-requests.yml`. It passes if there are no recorded runs, or if the latest run succeeded or was skipped. It fails if the latest run failed, timed out, or had a startup failure; an in-progress run or unrecognized conclusion is a warning. It does **not** inspect repository auto-merge settings, PR `auto_merge` fields, or workflow-file presence; workflow-file synchronization is a separate check. If the Actions API is inaccessible (for example HTTP 403), the result remains unknown/error until reader-App access is fixed.

Dependabot and human PR-age checks count open PRs targeting the scanned branch. Scheduled stale-human-PR reminders remain repository-wide and may still comment on stale, non-draft PRs targeting other branches.

The `node-net-repository-reader` GitHub App must have `Actions: read` permission and be installed on every repository whose workflow history is scanned. An organization administrator must grant that permission in the GitHub App settings, approve the organization permission update, and confirm private/internal repositories are included in the App installation. Then rerun the report. An HTTP 403 is an access problem, not proof that Actions is disabled, so the badge remains unknown until access is fixed.

## Checks

The report covers required governance files and templates, Dependabot policy, repository workflows, branches and activity, open pull requests, SBOMs, auto-merge settings, and verified credential scans. Repositories can be excluded in `excluded-repositories.txt` or with the `GOVERNANCE_EXCLUDED_REPOS` Actions variable; manual runs also accept the `excluded_repos` input.

## Run locally

Requires Python 3 and the GitHub CLI. Conftest enables Dependabot policy checks; Docker enables credential scans. Provide separate policy and workflow-baseline checkouts of `ospo-resources` from `develop`:

```bash
python3 tools/governance-report/governance_report.py \
  --org National-Node-Net \
  --source-root /path/to/ospo-resources-develop \
  --workflow-source-root /path/to/ospo-resources-develop \
  --output-dir governance-report
python3 -m unittest discover -s tools/governance-report
```
