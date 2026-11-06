# OSPO governance report

The weekly central scan checks active repositories in National-Node-Net and publishes a dashboard for public and private repositories. It also scans repository history for verified credentials. Credential values and locations are never included in the report.

## Schedule and results

The [workflow](../../.github/workflows/governance-report.yml) runs Monday at 03:00 UTC, on pushes to `feature/governance-report`, and on demand. Scheduled and push runs prefer `develop`, falling back to each repository's default branch. Manual runs provide a `main`/`develop` dropdown; if the selected branch is missing, that repository's default branch is used. Each report records the branch actually scanned. Scheduled runs also remind authors about stale, non-draft human pull requests; manual runs only report.

Each run adds a Markdown dashboard to the Actions summary and uploads `dashboard.md`, `dashboard.html`, and `report.json` as a 90-day artifact. The full report remains an artifact; it is not published to the badge branch.

The scan publishes status-only SVG badges for every included repository under `sync/governance-badges/repositories/<repo>/`. Individual repository READMEs and the public `.github` profile use the same OSPO compliance badge mapping. For badges, no required develop branch on a non-main default, no releases, and no applicable auto-merge/back-merge runs count as passing; an unavailable credential scan or unreadable required setting counts as failing. The central report retains its original `N/A` results. Badges contain no findings or report data.

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
