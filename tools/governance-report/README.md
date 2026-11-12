# OSPO governance report

The weekly central scan checks active repositories in National-Node-Net and publishes a dashboard for public and private repositories. It also scans repository history for verified credentials. Credential values and locations are never included in the report.

## Schedule and results

The [workflow](../../.github/workflows/governance-report.yml) runs Monday at 03:00 UTC, on pushes to `feature/governance-report`, and on demand. Per-repository badge scans are pinned to `develop` for now; manual runs offer only `develop`. A repository without `develop` is reported as unavailable rather than silently scanned on `main`. Required workflow synchronization compares each repository's scanned `develop` branch with the manifest and files on `ospo-resources/develop`; it does not wait for those files to be released to `main`. Switch both scan and synchronization baselines to `main` only when the organization is ready. Each report records the branch actually scanned. Scheduled runs also remind authors about stale, non-draft human pull requests; manual runs only report.

Each run adds a Markdown dashboard to the Actions summary and uploads `dashboard.md`, `dashboard.html`, and `report.json` as a 90-day artifact. The full report remains an artifact; it is not published to the badge branch.

The scan publishes status-only SVG badges for every included repository under `sync/governance-badges/repositories/<repo>/`. Individual repository READMEs and the central `ndt-overwatch` README use the same OSPO compliance badge mapping. The **OSPO compliance** badge combines these checks: develop branch, required governance files, templates, Dependabot configuration, open Dependabot PR age, open human PR age, verified credential scan, release SBOM, automatic branch deletion, current Dependabot auto-merge state, workflow synchronization, and main-to-develop back-merge. It deliberately excludes repository activity and scan freshness: those are shown by the separate **Days since last commit to develop branch** and **Last checked** badges. Badges are emitted as unknown/not checked unless that repository was scanned on `develop`. The **Days since last commit to develop branch** badge is always gray and reports elapsed whole days; it does not encode red/amber/green status. For compliance, a develop branch not required by a non-main default and no releases are non-applicable passes. Missing evidence for auto-merge/back-merge, an unevaluated Dependabot policy, or an unreadable repository setting stays unknown rather than being presented as a pass or failure. An unavailable credential scan remains a failure. The central report retains its raw status and reason. Badges contain no findings or report data.

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
