# OSPO governance report

The weekly central scan checks active repositories in National-Node-Net and publishes a dashboard for public and private repositories. It also scans repository history for verified credentials. Credential values and locations are never included in the report.

## Schedule and results

The [workflow](../../.github/workflows/governance-report.yml) runs Monday at 03:00 UTC, on pushes to `feature/governance-report`, and on demand. Per-repository badge scans are pinned to `develop` for now; manual runs offer only `develop`. A repository without `develop` is reported as unavailable rather than silently scanned on `main`. Switch the workflow input and this policy to `main` only when the organization is ready to change the badge baseline. Each report records the branch actually scanned. Scheduled runs also remind authors about stale, non-draft human pull requests; manual runs only report.

Each run adds a Markdown dashboard to the Actions summary and uploads `dashboard.md`, `dashboard.html`, and `report.json` as a 90-day artifact. The full report remains an artifact; it is not published to the badge branch.

The scan publishes status-only SVG badges for every included repository under `sync/governance-badges/repositories/<repo>/`. Individual repository READMEs and the central `ndt-overwatch` README use the same OSPO compliance badge mapping. The **OSPO compliance** badge combines these checks: develop branch, required governance files, templates, Dependabot configuration, open Dependabot PR age, open human PR age, verified credential scan, release SBOM, automatic branch deletion, current Dependabot auto-merge state, workflow synchronization, and main-to-develop back-merge. It deliberately excludes repository activity and scan freshness: those are shown by the separate **Days since last commit to Develop** and **Last checked** badges. Badges are emitted as unknown/not checked unless that repository was scanned on `develop`. A Develop-age badge is always gray and reports elapsed whole days; it does not encode red/amber/green status. For compliance, a develop branch not required by a non-main default and no releases are non-applicable passes. Missing evidence for auto-merge/back-merge, an unevaluated Dependabot policy, or an unreadable repository setting stays unknown rather than being presented as a pass or failure. An unavailable credential scan remains a failure. The central report retains its raw status and reason. Badges contain no findings or report data.

The Dependabot auto-merge check evaluates the current state of open Dependabot pull requests whose head branch starts with `dependabot/github_actions/`. It reports a pass only when GitHub currently returns an enabled `auto_merge` request for every such PR. A missing run, an old successful run with auto-merge no longer enabled, or an inaccessible Actions API is reported separately. With no open GitHub Actions Dependabot PRs, the result is N/A/unknown—not evidence that a future attempt will work.

The `node-net-repository-reader` GitHub App must have `Actions: read` permission and be installed on every repository whose workflow history is scanned. Approve the App permission update and confirm private/internal repositories are included in the installation. Without this, the report emits an explicit Actions API error instead of treating inaccessible history as a passing N/A.

## Checks

The report covers required governance files and templates, Dependabot policy, repository workflows, branches and activity, open pull requests, SBOMs, auto-merge settings, and verified credential scans. Repositories can be excluded in `excluded-repositories.txt` or with the `GOVERNANCE_EXCLUDED_REPOS` Actions variable; manual runs also accept the `excluded_repos` input.

## Run locally

Requires Python 3 and the GitHub CLI. Conftest enables Dependabot policy checks; Docker enables credential scans. Provide `ospo-resources` checkouts from `develop` and `main`:

```bash
python3 tools/governance-report/governance_report.py \
  --org National-Node-Net \
  --source-root /path/to/ospo-resources-develop \
  --workflow-source-root /path/to/ospo-resources-main \
  --output-dir governance-report
python3 -m unittest discover -s tools/governance-report
```
