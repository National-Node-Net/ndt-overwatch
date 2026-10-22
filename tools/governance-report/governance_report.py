#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © Crown Copyright 2026. This work has been developed by the National Digital Twin Programme and is legally attributed to the UK's Department for Business, Innovation, Science and Trade (BIST) as the governing entity.
"""Scan every active repository in a GitHub organisation and write an OSPO governance dashboard."""

import argparse
import base64
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

DEPENDABOT = 'dependabot[bot]'
EXCLUDED_REPOSITORIES = {'.github'}
TEMPLATE_FILES = [
    '.github/PULL_REQUEST_TEMPLATE.md',
    '.github/ISSUE_TEMPLATE/bug_report.md',
    '.github/ISSUE_TEMPLATE/feature_request.md',
]
DEPENDABOT_CONFIGS = ['.github/dependabot.yml', '.github/dependabot.yaml']
WORK_BRANCH_PREFIXES = ('feature/', 'bugfix/', 'hotfix/', 'release/')
VERY_OLD_DEPENDABOT_DAYS = 90
HUMAN_PR_MARKER = '<!-- ospo-stale-human-pr-reminder -->'
TRUFFLEHOG_IMAGE = 'trufflesecurity/trufflehog@sha256:47a84bc18a0d04a165498bbbd3bacfd84176661cbc91f8e0f85467f6a771e99a'
# Slightly under a week so a weekly schedule that runs early still reminds.
REMINDER_COOLDOWN = timedelta(days=6)

TRANSIENT_ERROR = re.compile(r'EOF|timeout|connection reset|HTTP 5\d\d', re.IGNORECASE)

OK, WARN, FAIL, NA, ERROR = 'OK', 'WARN', 'FAIL', 'N/A', 'ERROR'
STATUSES = [OK, WARN, FAIL, NA, ERROR]
STATUS_COLORS = {OK: '#1a7f37', WARN: '#9a6700', FAIL: '#cf222e', NA: '#6e7781', ERROR: '#cf222e'}

COLUMNS = [
    ('develop', 'Develop branch'),
    ('files', 'Required governance files'),
    ('templates', 'Pull request and issue templates'),
    ('dependabot_config', 'Dependabot configuration'),
    ('dependabot_prs', 'Dependabot pull requests'),
    ('human_prs', 'Human pull requests'),
    ('secret_scan', 'TruffleHog verified credential scan'),
    ('sbom', 'Release SBOM asset'),
    ('delete_branch', 'Automatic branch deletion'),
    ('allow_auto_merge', 'Allow auto-merge setting'),
    ('activity', 'Recent repository activity'),
    ('workflows', 'OSPO workflow synchronization'),
    ('auto_backmerge', 'Main-to-develop back-merge'),
]

MATRIX_HEADERS = {
    'develop': 'Develop<br>branch',
    'files': 'Required governance<br>files',
    'templates': 'Pull request and issue<br>templates',
    'dependabot_config': 'Dependabot<br>configuration',
    'dependabot_prs': 'Dependabot pull<br>requests',
    'human_prs': 'Human pull<br>requests',
    'secret_scan': 'Verified credential<br>scan',
    'sbom': 'Release SBOM<br>asset',
    'delete_branch': 'Automatic branch<br>deletion',
    'allow_auto_merge': 'Allow automatic<br>merge',
    'activity': 'Recent repository<br>activity',
    'workflows': 'OSPO workflow<br>synchronization',
    'auto_backmerge': 'Main-to-develop<br>back-merge',
}

GRAPHQL_ACTIVITY = '''
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    develop: ref(qualifiedName: "refs/heads/develop") {
            target { ... on Commit { history(first: 100) { nodes { committedDate messageHeadline messageBody author { name user { login __typename } } } pageInfo { hasNextPage endCursor } } } }
    }
    defaultBranchRef {
            target { ... on Commit { history(first: 100) { nodes { committedDate messageHeadline messageBody author { name user { login __typename } } } pageInfo { hasNextPage endCursor } } } }
    }
    refs(refPrefix: "refs/heads/", first: 100, orderBy: {field: TAG_COMMIT_DATE, direction: DESC}) {
    nodes { name target { ... on Commit { committedDate messageHeadline messageBody author { name user { login __typename } } } } }
    }
  }
}
'''

GRAPHQL_HISTORY_PAGE = '''
query($owner: String!, $name: String!, $branch: String!, $after: String) {
    repository(owner: $owner, name: $name) {
        ref(qualifiedName: $branch) {
            target { ... on Commit { history(first: 100, after: $after) { nodes { committedDate messageHeadline messageBody author { name user { login __typename } } } pageInfo { hasNextPage endCursor } } } }
        }
    }
}
'''


class ApiError(Exception):
    pass


def gh_api(endpoint, *, token=None, paginate=False, method=None, body=None, raw=False, fields=None):
    command = ['gh', 'api', endpoint]
    if raw:
        command += ['-H', 'Accept: application/vnd.github.raw']
    if paginate:
        command += ['--paginate', '--jq', '.[] | tojson']
    if method:
        command += ['--method', method]
    if body is not None:
        command += ['--input', '-']
    for key, value in (fields or {}).items():
        command += ['-f', f'{key}={value}']
    env = dict(os.environ)
    if token:
        env['GH_TOKEN'] = token
    # Writes are never retried, so a reminder cannot be posted twice.
    attempts = 1 if method else 3
    for attempt in range(attempts):
        result = subprocess.run(
            command, input=json.dumps(body) if body is not None else None,
            text=True, capture_output=True, timeout=60, env=env,
        )
        message = (result.stderr or result.stdout).strip()
        if result.returncode == 0 or not TRANSIENT_ERROR.search(message) or attempt == attempts - 1:
            break
        time.sleep(2 * (attempt + 1))
    if result.returncode != 0:
        raise ApiError(f'{endpoint}: {message}')
    if raw:
        return result.stdout
    if paginate:
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    return json.loads(result.stdout) if result.stdout.strip() else None


def parse_time(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def age_days(value, now):
    return (now - parse_time(value)).days


def result(status, summary, details=None):
    return {'status': status, 'summary': summary, 'details': list(details or [])}


def git_blob_sha(data):
    return hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()


def read_list_file(text):
    return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith('#')]


def is_bot_author(author):
    user = (author or {}).get('user') or {}
    login = (user.get('login') or '').lower()
    name = ((author or {}).get('name') or '').lower()
    return user.get('__typename') == 'Bot' or login.endswith('[bot]') or name.endswith('[bot]')


def is_automation_commit(commit):
    message = f'{commit.get("messageHeadline") or ""}\n{commit.get("messageBody") or ""}'.casefold()
    return is_bot_author(commit.get('author')) or 'ospo' in message


def is_bot_user(user):
    return (user or {}).get('type') == 'Bot' or ((user or {}).get('login') or '').endswith('[bot]')


def check_develop(default_branch, has_develop):
    if has_develop:
        return result(OK, 'present')
    if default_branch != 'main':
        return result(NA, f'default branch is {default_branch}')
    return result(FAIL, 'missing', ['Default branch is main but no develop branch exists.'])


def check_required_paths(paths, required, label):
    missing = [path for path in required if path not in paths]
    if not missing:
        return result(OK, f'all {len(required)} present')
    summary = ', '.join(Path(path).name for path in missing) if len(missing) <= 2 else f'{len(missing)} missing'
    return result(FAIL, summary, [f'Missing {label}: {path}' for path in missing])


def check_dependabot_config(config_path, failures, evaluated=True):
    if not config_path:
        return result(FAIL, 'no dependabot.yml', ['No .github/dependabot.yml on the default branch.'])
    if not evaluated:
        return result(NA, 'conftest not installed')
    if failures:
        return result(FAIL, f'{len(failures)} policy failures', [f'Dependabot policy: {msg}' for msg in failures])
    return result(OK, 'policy passed')


def parse_trufflehog_output(output, repositories, *, local_repository=False):
    names = {repo['full_name'].lower(): repo['name'] for repo in repositories}
    counts = {repo['name']: 0 for repo in repositories}
    unmapped = 0
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            finding = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError('Malformed scanner JSON') from None
        if not isinstance(finding, dict):
            raise ValueError('Malformed scanner result')
        if finding.get('Verified') is not True:
            continue
        git = (((finding.get('SourceMetadata') or {}).get('Data') or {}).get('Git') or {})
        repository_url = git.get('repository') or ''
        path = urlparse(repository_url).path.strip('/').removesuffix('.git').lower()
        repo_name = names.get(path)
        if local_repository and len(repositories) == 1 and repository_url.startswith('file://'):
            repo_name = repositories[0]['name']
        if repo_name:
            counts[repo_name] += 1
        else:
            unmapped += 1
    return counts, unmapped


def check_secret_scan(count, *, available=True, error=None, reason=None):
    if error:
        return result(ERROR, error, ['Scanner output and credential data were suppressed from the report.'])
    if not available:
        return result(NA, reason or 'TruffleHog scan unavailable')
    if count:
        return result(FAIL, f'{count} verified finding(s)', [
            f'TruffleHog verified {count} credential(s); secret values and locations are withheld.'
        ])
    return result(OK, 'no verified credentials found')


def check_trufflehog_result(exit_code, output, repo, *, local_repository=False):
    if exit_code != 0:
        return check_secret_scan(0, error=f'TruffleHog exited with code {exit_code}')
    try:
        counts, unmapped = parse_trufflehog_output(output, [repo], local_repository=local_repository)
    except ValueError:
        return check_secret_scan(0, error='TruffleHog returned malformed JSON')
    if unmapped:
        return check_secret_scan(0, error=f'{unmapped} verified finding(s) could not be attributed')
    return check_secret_scan(counts[repo['name']])


def check_dependabot_prs(prs, now, stale_days):
    dependabot = [pr for pr in prs if pr['user']['login'] == DEPENDABOT]
    if not dependabot:
        return result(OK, '0 open')
    ages = {pr['number']: age_days(pr['created_at'], now) for pr in dependabot}
    stale = [pr for pr in dependabot if ages[pr['number']] > stale_days]
    very_old = [pr for pr in stale if ages[pr['number']] > VERY_OLD_DEPENDABOT_DAYS]
    summary = f'{len(dependabot)} open, {len(stale)} >{stale_days}d'
    if very_old:
        summary += f', {len(very_old)} >{VERY_OLD_DEPENDABOT_DAYS}d'
    details = [f'Dependabot PR #{pr["number"]} open {ages[pr["number"]]} days: {pr["title"]}' for pr in stale]
    status = FAIL if very_old else WARN if stale else OK
    return result(status, summary, details)


def stale_human_prs(prs, now, days):
    return [pr for pr in prs if not is_bot_user(pr['user']) and age_days(pr['created_at'], now) > days]


def check_human_prs(prs, now, days, reminder_notes=None):
    human = [pr for pr in prs if not is_bot_user(pr['user'])]
    stale = stale_human_prs(prs, now, days)
    if not stale:
        return result(OK, f'{len(human)} open, 0 >{days}d')
    notes = reminder_notes or {}
    details = []
    for pr in stale:
        flags = []
        if pr.get('draft'):
            flags.append('draft')
        if pr['base']['ref'] == 'main' and not pr['head']['ref'].startswith(('release/', 'hotfix/')):
            flags.append('targets main')
        if pr['number'] in notes:
            flags.append(notes[pr['number']])
        suffix = f' [{", ".join(flags)}]' if flags else ''
        details.append(
            f'PR #{pr["number"]} by {pr["user"]["login"]} open {age_days(pr["created_at"], now)} days{suffix}: {pr["title"]}'
        )
    return result(WARN, f'{len(human)} open, {len(stale)} >{days}d', details)


def has_sbom(release):
    return any(
        asset['name'].lower().endswith('.spdx.json') or 'sbom' in asset['name'].lower()
        for asset in release.get('assets', [])
    )


def check_sbom(releases, now, days):
    published = [r for r in releases if not r.get('draft') and r.get('published_at')]
    if not published:
        return result(NA, 'no releases')
    published.sort(key=lambda r: r['published_at'], reverse=True)
    recent = [r for r in published if age_days(r['published_at'], now) <= days]
    evaluated = recent or published[:1]
    missing = [r for r in evaluated if not has_sbom(r)]
    scope = f'last {days}d' if recent else 'latest'
    details = [f'Release {r["tag_name"]} ({r["published_at"][:10]}) has no SBOM asset' for r in missing]
    if missing:
        return result(FAIL, f'{len(missing)}/{len(evaluated)} missing ({scope})', details)
    return result(OK, f'{len(evaluated)} with SBOM ({scope})')


def check_delete_branch(value):
    if value is None:
        return result(NA, 'unknown', ['Merge settings require a token with Contents: write.'])
    return result(OK, 'on') if value else result(FAIL, 'off', ['delete_branch_on_merge is disabled.'])


def check_allow_auto_merge(value):
    if value is None:
        return result(NA, 'unknown', ['Merge settings require a token with Contents: write.'])
    return result(OK, 'enabled') if value else result(FAIL, 'disabled', ['allow_auto_merge is disabled.'])


def check_activity(activity, now, days):
    develop = activity.get('develop')
    branch_name = 'develop' if develop else 'default branch'
    source = develop or activity.get('defaultBranchRef') or {}
    history = (((source.get('target') or {}).get('history')) or {}).get('nodes', [])
    latest_human = activity.get('latestHumanCommit') or latest_human_commit(history)
    days_since_human = age_days(latest_human['committedDate'], now) if latest_human else None
    since = now - timedelta(days=days)
    active_branches = [
        node['name'] for node in (activity.get('refs') or {}).get('nodes', [])
        if node['name'].startswith(WORK_BRANCH_PREFIXES)
        and (node.get('target') or {}).get('committedDate')
        and parse_time(node['target']['committedDate']) >= since
        and not is_automation_commit(node['target'])
    ]
    human_activity_recent = days_since_human is not None and days_since_human <= days
    activity_summary = (
        f'{days_since_human} days since last human commit'
        if days_since_human is not None else 'no human commit found'
    )
    activity_summary += f'; {len(active_branches)} active work branches ({days}d window)'
    if human_activity_recent or active_branches:
        return result(OK, activity_summary)
    return result(
        WARN, activity_summary,
        [f'No human-authored commit on {branch_name} within {days} days and no active '
         f'feature/bugfix/hotfix/release branches. Review for archive.'],
    )


def latest_human_commit(commits):
    human = [commit for commit in commits if not is_automation_commit(commit)]
    return max(human, key=lambda commit: commit['committedDate']) if human else None


def check_workflows(blob_shas, expected):
    missing, outdated = [], []
    for name, sha in expected.items():
        target = f'.github/workflows/{name}'
        if target not in blob_shas:
            missing.append(name)
        elif blob_shas[target] != sha:
            outdated.append(name)
    details = [f'Missing OSPO workflow: {name}' for name in missing] + [f'Out of sync with ospo-resources: {name}' for name in outdated]
    if missing:
        return result(FAIL, f'{len(missing)} missing, {len(outdated)} outdated', details)
    if outdated:
        return result(WARN, f'{len(outdated)} outdated', details)
    return result(OK, f'all {len(expected)} in sync')


def check_auto_backmerge(workflow_present, runs):
    if not workflow_present:
        return result(FAIL, 'workflow missing from default branch', ['.github/workflows/auto-back-merge.yml is missing.'])
    attempts = [run for run in runs if run.get('conclusion') != 'skipped']
    if not attempts:
        return result(NA, 'no back-merge attempts recorded')

    latest = attempts[0]
    run_id = latest.get('run_number', latest.get('id', '?'))
    run_date = latest.get('created_at', '')[:10]
    conclusion = latest.get('conclusion')
    state = latest.get('status')
    run_url = latest.get('html_url')
    run_reference = f'[run #{run_id}]({run_url})' if run_url else f'run #{run_id}'
    details = [f'Latest run: {run_url}'] if run_url else []

    if state != 'completed':
        return result(WARN, f'{state or "in progress"} {run_reference} ({run_date})', details)
    if conclusion == 'success':
        return result(OK, f'passed {run_reference} ({run_date})')
    if conclusion in ('failure', 'timed_out', 'startup_failure'):
        return result(FAIL, f'{conclusion.replace("_", " ")} {run_reference} ({run_date})', details)
    return result(WARN, f'{conclusion or "unknown"} {run_reference} ({run_date})', details)


def reminder_due(comments, bot_login, now):
    for comment in comments:
        if comment['user']['login'] == bot_login and HUMAN_PR_MARKER in (comment.get('body') or ''):
            if now - parse_time(comment['created_at']) < REMINDER_COOLDOWN:
                return False
    return True


def reminder_body(pr, now):
    return (
        f'{HUMAN_PR_MARKER}\n'
        f'@{pr["user"]["login"]} this pull request has been open for {age_days(pr["created_at"], now)} days '
        'without being merged. Please merge, update or close it. If it is still needed, add a short status update.\n\n'
        'This is an automated OSPO governance reminder.'
    )


class Scanner:
    def __init__(self, args, source_root):
        self.args = args
        self.org = args.org
        self.now = datetime.now(timezone.utc)
        self.pr_token = os.environ.get('PR_TOKEN') or None
        self.settings_token = os.environ.get('SETTINGS_TOKEN') or None
        self.oss_files = read_list_file((source_root / 'oss-checklist-files.txt').read_text())
        manifest = read_list_file((source_root / 'organisation-required-workflows.txt').read_text())
        self.expected_workflows = {
            Path(path).name: git_blob_sha((source_root / path).read_bytes())
            for path in manifest if (source_root / path).is_file()
        }
        self.policy_dir = source_root / 'tools/policy-as-code/policy'
        self.conftest = shutil.which('conftest')
        self._inner_source_files = None

    def inner_source_files(self):
        if self._inner_source_files is None:
            text = gh_api(f'repos/{self.args.inner_source_checklist_repo}/contents/inner-source-checklist-files.txt', raw=True)
            self._inner_source_files = read_list_file(text)
        return self._inner_source_files

    def run_conftest(self, content, metadata):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'dependabot.yml'
            data = Path(tmp) / 'repository-metadata.json'
            config.write_text(content)
            data.write_text(json.dumps(metadata))
            proc = subprocess.run(
                [self.conftest, 'test', str(config), '-p', str(self.policy_dir), '--data', str(data),
                 '--namespace', 'github.dependabot', '--output', 'json', '--no-color'],
                text=True, capture_output=True, timeout=60,
            )
        try:
            report = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return [f'could not evaluate: {(proc.stderr or proc.stdout).strip()[:300]}']
        return sorted({failure['msg'] for item in report for failure in item.get('failures') or []})

    def secret_scan(self, repos):
        unavailable = {
            repo['name']: check_secret_scan(0, available=False, reason='TruffleHog requires Docker')
            for repo in repos
        }
        if not shutil.which('docker'):
            return unavailable

        token = os.environ.get('TRUFFLEHOG_GITHUB_TOKEN') or os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
        if not token:
            auth = subprocess.run(
                ['gh', 'auth', 'token', '--hostname', 'github.com'],
                text=True, capture_output=True, timeout=15,
            )
            if auth.returncode == 0:
                token = auth.stdout.strip()
        if not token:
            credential_env = dict(os.environ)
            credential_env['GIT_TERMINAL_PROMPT'] = '0'
            credential = subprocess.run(
                ['git', 'credential', 'fill'],
                input='protocol=https\nhost=github.com\n\n',
                text=True, capture_output=True, timeout=15, env=credential_env,
            )
            if credential.returncode == 0:
                token = next(
                    (line.split('=', 1)[1] for line in credential.stdout.splitlines() if line.startswith('password=')),
                    None,
                )
        if not token:
            return {
                repo['name']: check_secret_scan(0, available=False, reason='GitHub token unavailable')
                for repo in repos
            }

        results = {}
        for repo in repos:
            print(f'Scanning Git history for credentials: {repo["full_name"]}', file=sys.stderr)
            results[repo['name']] = self.scan_git_history(repo, token)
        return results

    def scan_git_history(self, repo, token):
        with tempfile.TemporaryDirectory(prefix='ospo-scan-') as tmp:
            env = dict(os.environ)
            auth = base64.b64encode(f'x-access-token:{token}'.encode()).decode()
            env.update({
                'GIT_CONFIG_COUNT': '2',
                'GIT_CONFIG_KEY_0': 'http.https://github.com/.extraheader',
                'GIT_CONFIG_VALUE_0': f'AUTHORIZATION: basic {auth}',
                'GIT_CONFIG_KEY_1': 'credential.helper',
                'GIT_CONFIG_VALUE_1': '',
                'GIT_TERMINAL_PROMPT': '0',
            })
            container_name = Path(tmp).name
            try:
                clone = subprocess.run(
                    ['git', 'clone', '--no-checkout', f'https://github.com/{repo["full_name"]}.git',
                     str(Path(tmp) / 'repository')],
                    env=env, text=True, capture_output=True, timeout=300,
                )
                if clone.returncode != 0:
                    return check_secret_scan(0, error=f'Git history clone failed (exit {clone.returncode})')
                index = subprocess.run(
                    ['git', '-C', str(Path(tmp) / 'repository'), 'read-tree', 'HEAD'],
                    text=True, capture_output=True, timeout=30,
                )
                if index.returncode != 0:
                    return check_secret_scan(0, error='Git history index could not be prepared')
                # Only the clone receives authentication; scanner containers receive no GitHub token.
                command = [
                    'docker', 'run', '--rm', '--name', container_name,
                    '--mount', f'type=bind,source={tmp},target=/scan,readonly', TRUFFLEHOG_IMAGE,
                    'git', 'file:///scan/repository', '--results=verified', '--json',
                    '--no-update', '--no-color', '--fail-on-scan-errors',
                ]
                scan = subprocess.run(command, text=True, capture_output=True, timeout=600)
                return check_trufflehog_result(scan.returncode, scan.stdout, repo, local_repository=True)
            except (subprocess.TimeoutExpired, OSError) as exc:
                summary = 'Credential scan timed out' if isinstance(exc, subprocess.TimeoutExpired) else 'Credential scan could not start'
                return check_secret_scan(0, error=summary)
            finally:
                subprocess.run(['docker', 'rm', '-f', container_name], capture_output=True, timeout=30)

    def scan(self, repo, secret_result):
        name = repo['name']
        full = repo['full_name']
        default = repo['default_branch']
        entry = {
            'name': name, 'url': repo['html_url'], 'visibility': repo.get('visibility', 'unknown'),
            'default_branch': default, 'fork': repo.get('fork', False), 'checks': {}, 'errors': [],
        }
        checks = entry['checks']
        checks['secret_scan'] = secret_result
        if secret_result['status'] in (ERROR, NA):
            entry['errors'].append(f'secret_scan: {secret_result["summary"]}')

        def run(key, func):
            try:
                checks[key] = func()
            except (ApiError, subprocess.TimeoutExpired, KeyError, ValueError) as exc:
                checks[key] = result(ERROR, 'error', [str(exc)[:300]])
                entry['errors'].append(f'{key}: {str(exc)[:300]}')

        state = {}

        def load_tree():
            tree = gh_api(f'repos/{full}/git/trees/{default}?recursive=1')
            state['blobs'] = {item['path']: item['sha'] for item in tree['tree'] if item['type'] == 'blob'}
            if tree.get('truncated'):
                entry['errors'].append('tree: listing truncated, file checks may be incomplete')

        def load_activity():
            data = gh_api('graphql', fields={
                'query': GRAPHQL_ACTIVITY, 'owner': self.org, 'name': name,
            })
            state['activity'] = data['data']['repository']
            state['has_develop'] = state['activity'].get('develop') is not None
            ref_name = 'develop' if state['has_develop'] else default
            source = state['activity'].get('develop') or state['activity'].get('defaultBranchRef') or {}
            history = (((source.get('target') or {}).get('history')) or {})
            latest = latest_human_commit(history.get('nodes', []))
            page_info = history.get('pageInfo') or {}
            while latest is None and page_info.get('hasNextPage'):
                page = gh_api('graphql', fields={
                    'query': GRAPHQL_HISTORY_PAGE, 'owner': self.org, 'name': name,
                    'branch': f'refs/heads/{ref_name}', 'after': page_info['endCursor'],
                })
                ref = (page.get('data', {}).get('repository') or {}).get('ref') or {}
                history = (((ref.get('target') or {}).get('history')) or {})
                latest = latest_human_commit(history.get('nodes', []))
                page_info = history.get('pageInfo') or {}
            state['activity']['latestHumanCommit'] = latest

        try:
            load_tree()
            load_activity()
        except (ApiError, subprocess.TimeoutExpired, KeyError, TypeError) as exc:
            entry['errors'].append(f'scan: {str(exc)[:300]}')
            for key, _ in COLUMNS:
                if key != 'secret_scan':
                    checks[key] = result(ERROR, 'not scanned')
            return entry

        blobs = state['blobs']
        paths = set(blobs)
        run('develop', lambda: check_develop(default, state['has_develop']))
        run('files', lambda: check_required_paths(
            paths, self.oss_files if repo.get('visibility') == 'public' else self.inner_source_files(), 'file'))
        run('templates', lambda: check_required_paths(paths, TEMPLATE_FILES, 'template'))
        run('dependabot_config', lambda: self.dependabot_config(full, default, paths, state['has_develop']))
        run('sbom', lambda: check_sbom(gh_api(f'repos/{full}/releases?per_page=100'), self.now, self.args.release_days))
        run('delete_branch', lambda: check_delete_branch(self.repo_setting(full, state, 'delete_branch_on_merge')))
        run('allow_auto_merge', lambda: check_allow_auto_merge(self.repo_setting(full, state, 'allow_auto_merge')))
        run('activity', lambda: check_activity(state['activity'], self.now, self.args.dormant_days))
        run('workflows', lambda: check_workflows(blobs, self.expected_workflows))
        run('auto_backmerge', lambda: self.auto_backmerge(full, paths))

        try:
            prs = gh_api(f'repos/{full}/pulls?state=open&per_page=100', token=self.pr_token, paginate=True)
        except (ApiError, subprocess.TimeoutExpired) as exc:
            for key in ('dependabot_prs', 'human_prs'):
                checks[key] = result(ERROR, 'error', [str(exc)[:300]])
            entry['errors'].append(f'pulls: {str(exc)[:300]}')
            return entry
        run('dependabot_prs', lambda: check_dependabot_prs(prs, self.now, self.args.dependabot_pr_days))
        run('human_prs', lambda: check_human_prs(prs, self.now, self.args.human_pr_days, self.remind(full, prs, entry)))
        return entry

    def dependabot_config(self, full, default, paths, has_develop):
        config_path = next((path for path in DEPENDABOT_CONFIGS if path in paths), None)
        if not config_path or not self.conftest:
            return check_dependabot_config(config_path, [], evaluated=bool(self.conftest))
        content = gh_api(f'repos/{full}/contents/{config_path}?ref={default}', raw=True)
        metadata = {'repository': {'defaultBranch': default, 'hasDevelopBranch': has_develop}}
        return check_dependabot_config(config_path, self.run_conftest(content, metadata))

    def repo_setting(self, full, state, setting):
        if 'settings' not in state:
            state['settings'] = gh_api(f'repos/{full}', token=self.settings_token)
        return state['settings'].get(setting)

    def auto_backmerge(self, full, paths):
        workflow_path = '.github/workflows/auto-back-merge.yml'
        if workflow_path not in paths:
            return check_auto_backmerge(False, [])
        try:
            runs = gh_api(f'repos/{full}/actions/workflows/auto-back-merge.yml/runs?per_page=100')
        except ApiError as exc:
            if re.search(r'HTTP 403|HTTP 404|Resource not accessible by integration|Actions is disabled', str(exc), re.IGNORECASE):
                return result(
                    NA, 'Actions run history unavailable',
                    ['The repository reader App needs Actions: read permission to inspect workflow runs.'],
                )
            raise
        return check_auto_backmerge(True, runs.get('workflow_runs', []))

    def remind(self, full, prs, entry):
        notes = {}
        for pr in stale_human_prs(prs, self.now, self.args.human_pr_days):
            if pr.get('draft'):
                continue
            number = pr['number']
            if not self.args.post_reminders:
                notes[number] = 'would remind'
                continue
            try:
                comments = gh_api(f'repos/{full}/issues/{number}/comments?per_page=100', token=self.pr_token, paginate=True)
                if not reminder_due(comments, self.args.reminder_author, self.now):
                    notes[number] = 'recently reminded'
                    continue
                current = gh_api(f'repos/{full}/pulls/{number}', token=self.pr_token)
                if current['state'] != 'open':
                    notes[number] = 'closed during scan'
                    continue
                gh_api(f'repos/{full}/issues/{number}/comments', token=self.pr_token, method='POST',
                       body={'body': reminder_body(pr, self.now)})
                notes[number] = 'reminded'
            except (ApiError, subprocess.TimeoutExpired, KeyError, ValueError) as exc:
                notes[number] = 'reminder failed'
                entry['errors'].append(f'reminder #{number}: {str(exc)[:300]}')
        return notes


def cell(text):
    return str(text).replace('|', '\\|').replace('\n', ' ')


def markdown_status(status):
    return f'<span style="color:{STATUS_COLORS[status]}"><strong>{status}</strong></span>'


def render_markdown(report):
    args = report['parameters']
    repos = report['repositories']
    legend = report.get('legend', {})
    public_required_files = ', '.join('`' + path + '`' for path in legend.get('public_required_files', []))
    private_required_files = ', '.join('`' + path + '`' for path in legend.get('private_required_files', []))
    lines = [
        f'# OSPO governance dashboard: {report["organisation"]}',
        '',
        f'Generated {report["generated_at"]} UTC. Mode: {report["mode"]}. Repositories scanned: {len(repos)}. '
        f'Archived/disabled skipped: {len(report["skipped"])}.',
        f'Excluded by report policy: {", ".join(report.get("excluded", [])) or "none"}.',
        '',
        f'Thresholds: human PRs >{args["human_pr_days"]}d, Dependabot PRs >{args["dependabot_pr_days"]}d, '
        f'dormant after {args["dormant_days"]}d, releases checked for SBOM within {args["release_days"]}d (else latest).',
        '',
        '## Summary',
        '',
        '| Check | Counts |',
        '| --- | --- |',
    ]
    for key, title in COLUMNS:
        counts = [sum(1 for r in repos if r['checks'].get(key, {}).get('status') == s) for s in STATUSES]
        count_text = '; '.join(f'{markdown_status(status)} {count}' for status, count in zip(STATUSES, counts) if count)
        lines.append(f'| {title} | {count_text or "-"} |')

    lines += [
        '',
        '## Repositories',
        '',
        'Each cell shows the full status and a short result. Expand a repository below for affected files, PRs, releases, and workflow details.',
        '',
        '| Repository | ' + ' | '.join(f'<small>{MATRIX_HEADERS[key]}</small>' for key, _ in COLUMNS) + ' |',
        '| --- | ' + ' | '.join('---' for _ in COLUMNS) + ' |',
    ]
    for repo in repos:
        statuses = [
            f'<small>{markdown_status(check["status"])}<br>{cell(check["summary"])}</small>'
            for key, _ in COLUMNS
            for check in [repo['checks'].get(key, result(NA, '-'))]
        ]
        lines.append(
            f'| [{cell(repo["name"])}]({repo["url"]}) | ' + ' | '.join(statuses) + ' |'
        )

    lines += ['', 'Status details are available in each repository section below.', '', '## Repository details', '']
    for repo in repos:
        lines.append(
            f'<details><summary>{cell(repo["name"])} | {repo["visibility"]} | default: {cell(repo["default_branch"])}</summary>'
        )
        details = [d for key, _ in COLUMNS for d in repo['checks'].get(key, {}).get('details', [])
                   if repo['checks'][key]['status'] in (WARN, FAIL, ERROR)]
        details += [f'Processing error: {e}' for e in repo['errors']]
        if details:
            lines += ['', 'Findings:', '']
            lines += [f'- {cell(d)}' for d in details]
        lines += ['', '</details>', '']

    if report['skipped']:
        lines += ['## Skipped', '', ', '.join(report['skipped']), '']
    if report.get('excluded'):
        lines += ['## Excluded from scan', '', ', '.join(report['excluded']), '']
    lines += [
        '## Legend and check definitions',
        '',
        f'- **Status colours:** {markdown_status(OK)} = passed; {markdown_status(WARN)} = attention; '
        f'{markdown_status(FAIL)} = failed/action required; {markdown_status(NA)} = not available or not applicable; '
        f'{markdown_status(ERROR)} = check could not complete.',
        f'- **Required governance files for public repositories:** {public_required_files}.',
        f'- **Required governance files for private/internal repositories:** {private_required_files}.',
        '- **Pull request template:** `.github/PULL_REQUEST_TEMPLATE.md`.',
        '- **Issue templates:** `.github/ISSUE_TEMPLATE/bug_report.md` and `.github/ISSUE_TEMPLATE/feature_request.md`.',
        '- **Dependabot configuration:** `.github/dependabot.yml` or `.github/dependabot.yaml` on the default branch. '
        'Conftest evaluates the existing `github.dependabot` Rego policies: GitHub Actions entries omit `target-branch`; '
        'other ecosystems in `main` + `develop` GitFlow repos target `develop`; and enabled updates have a valid groups object '
        'with a version-update group unless `open-pull-requests-limit` is zero. This is not full Dependabot YAML schema validation.',
        f'- **Dependabot PR age:** WARN when open >{args["dependabot_pr_days"]} days; FAIL when open >{VERY_OLD_DEPENDABOT_DAYS} days. Age is from PR creation.',
        f'- **Human PR age:** WARN and scheduled reminder when open >{args["human_pr_days"]} days; no separate FAIL age threshold is currently configured. '
        'Draft PRs are reported but not reminded.',
        f'- **Activity:** exact whole days since the latest human-authored commit on `develop` (or default branch when no `develop` exists). '
        f'All bot-authored commits and any commit with `OSPO` anywhere in its subject or body are ignored. Dormant warning threshold: '
        f'>{args["dormant_days"]} days with no recent human work branch.',
        '- **Credential scan:** TruffleHog scans selected active repositories (excluding `.github`) for verified credentials only. '
        'The report records counts/status only; it never stores credential values or finding locations.',
        '- **AI use:** none. The report script uses Python, GitHub CLI/API, Conftest and TruffleHog; it does not call an AI model.',
        '',
    ]
    return '\n'.join(lines)


def html_status(status):
    css_class = status.lower().replace('/', '-')
    return f'<span class="status {css_class}">{html.escape(status)}</span>'


def render_html(report):
    args = report['parameters']
    repos = report['repositories']
    legend = report.get('legend', {})
    esc = lambda value: html.escape(str(value), quote=True)
    parts = [
        '<!doctype html>', '<html lang="en">', '<head>', '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f'<title>OSPO governance dashboard: {esc(report["organisation"])}</title>',
        '<style>',
        'body{margin:1rem;color:#24292f}table{border-collapse:collapse;width:100%}',
        'th,td{border:1px solid #d0d7de;padding:.35rem;vertical-align:top;overflow-wrap:anywhere}',
        '.matrix{table-layout:fixed}.matrix th,.matrix td{font-size:.72rem}.matrix th{font-weight:600}',
        '.status{font-weight:700}.ok{color:#1a7f37}.warn{color:#9a6700}.fail,.error{color:#cf222e}.n-a{color:#6e7781}',
        '.cards{display:none}.card{border:1px solid #d0d7de;border-radius:.4rem;padding:.6rem;margin:.6rem 0}',
        '.check{margin:.2rem 0}.check-name{font-weight:600}',
        '@media(max-width:1100px){.matrix{display:none}.cards{display:block}}',
        '</style>', '</head>', '<body>',
        f'<h1>OSPO governance dashboard: {esc(report["organisation"])}</h1>',
        f'<p>Generated {esc(report["generated_at"])} UTC. Mode: {esc(report["mode"])}. '
        f'Repositories scanned: {len(repos)}. Archived/disabled skipped: {len(report["skipped"])}. '
        f'Excluded: {esc(", ".join(report.get("excluded", [])) or "none")}.</p>',
        f'<p>Thresholds: human PRs &gt;{args["human_pr_days"]}d; Dependabot PRs &gt;{args["dependabot_pr_days"]}d; '
        f'dormant after {args["dormant_days"]}d; release SBOM window {args["release_days"]}d (else latest).</p>',
        '<h2>Summary</h2><table><thead><tr><th>Check</th><th>Counts</th></tr></thead><tbody>',
    ]
    for key, title in COLUMNS:
        counts = [sum(1 for repo in repos if repo['checks'].get(key, {}).get('status') == status) for status in STATUSES]
        rendered = '; '.join(f'{html_status(status)} {count}' for status, count in zip(STATUSES, counts) if count) or '-'
        parts.append(f'<tr><th>{esc(title)}</th><td>{rendered}</td></tr>')
    parts.extend([
        '</tbody></table>', '<h2>Repository matrix</h2>',
        '<table class="matrix"><thead><tr><th>Repository</th>',
    ])
    parts.extend(f'<th>{header.replace("<br>", "<br>")}</th>' for key, _ in COLUMNS for header in [MATRIX_HEADERS[key]])
    parts.append('</tr></thead><tbody>')
    for repo in repos:
        parts.append(f'<tr><th><a href="{esc(repo["url"])}">{esc(repo["name"])}</a></th>')
        for key, _ in COLUMNS:
            check = repo['checks'].get(key, result(NA, '-'))
            parts.append(f'<td>{html_status(check["status"])}<br><small>{esc(check["summary"])}</small></td>')
        parts.append('</tr>')
    parts.extend(['</tbody></table>', '<section class="cards"><h2>Repositories</h2>'])
    for repo in repos:
        parts.append(f'<article class="card"><h3><a href="{esc(repo["url"])}">{esc(repo["name"])}</a></h3>')
        for key, title in COLUMNS:
            check = repo['checks'].get(key, result(NA, '-'))
            parts.append(
                f'<p class="check"><span class="check-name">{esc(title)}:</span> '
                f'{html_status(check["status"])} — {esc(check["summary"])}</p>'
            )
        parts.append('</article>')
    parts.extend(['</section>', '<h2>Repository details</h2>'])
    for repo in repos:
        parts.append(f'<details><summary>{esc(repo["name"])} | {esc(repo["visibility"])} | default: {esc(repo["default_branch"])}</summary><ul>')
        details = [detail for key, _ in COLUMNS for detail in repo['checks'].get(key, {}).get('details', [])
                   if repo['checks'][key]['status'] in (WARN, FAIL, ERROR)]
        details.extend(f'Processing error: {error}' for error in repo['errors'])
        parts.extend(f'<li>{esc(detail)}</li>' for detail in details)
        parts.append('</ul></details>')
    parts.extend([
        '<h2>Legend and check definitions</h2>',
        f'<p>{html_status(OK)} passed; {html_status(WARN)} attention; {html_status(FAIL)} failed/action required; '
        f'{html_status(NA)} not available/not applicable; {html_status(ERROR)} could not complete.</p>',
        '<h3>Required governance files</h3><p>Public repositories:</p><ul>',
    ])
    parts.extend(f'<li><code>{esc(path)}</code></li>' for path in legend.get('public_required_files', []))
    parts.extend(['</ul><p>Private/internal repositories:</p><ul>'])
    parts.extend(f'<li><code>{esc(path)}</code></li>' for path in legend.get('private_required_files', []))
    parts.extend([
        '</ul><h3>Templates and policy</h3>',
        '<p>PR template: <code>.github/PULL_REQUEST_TEMPLATE.md</code>. Issue templates: '
        '<code>.github/ISSUE_TEMPLATE/bug_report.md</code> and '
        '<code>.github/ISSUE_TEMPLATE/feature_request.md</code>.</p>',
        '<p>Dependabot config checks <code>.github/dependabot.yml</code> or <code>.github/dependabot.yaml</code> '
        'with the existing GitFlow target-branch and Dependabot groups Rego rules; it is not full YAML schema validation.</p>',
        f'<p>Dependabot PR: WARN &gt;{args["dependabot_pr_days"]}d, FAIL &gt;{VERY_OLD_DEPENDABOT_DAYS}d. '
        f'Human PR: WARN/reminder &gt;{args["human_pr_days"]}d; no separate FAIL age threshold is configured. '
        f'Activity: exact whole days since latest human commit; dormant warning after {args["dormant_days"]}d.</p>',
        '<p>TruffleHog scans verified credentials only; values and locations are not recorded. '
        'Human-activity age ignores all bot-authored commits and any commit with OSPO in its subject or body. No AI/LLM is used.</p>',
        '<p>The font is inherited from the viewer; no font family is set in this report.</p>',
        '</body></html>',
    ])
    return '\n'.join(parts)


def bounded_int(value):
    number = int(value)
    if not 1 <= number <= 3650:
        raise argparse.ArgumentTypeError('must be between 1 and 3650')
    return number


def partition_repositories(repositories):
    excluded = sorted(repo['name'] for repo in repositories if repo['name'] in EXCLUDED_REPOSITORIES)
    active = sorted(
        (repo for repo in repositories if not repo.get('archived') and not repo.get('disabled')
         and repo['name'] not in EXCLUDED_REPOSITORIES),
        key=lambda repo: repo['name'].lower(),
    )
    skipped = sorted(repo['name'] for repo in repositories if repo.get('archived') or repo.get('disabled'))
    return active, skipped, excluded


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--org', default=os.environ.get('GITHUB_REPOSITORY_OWNER'))
    parser.add_argument('--source-root', type=Path, default=Path(__file__).resolve().parents[2],
                        help='Checkout containing OSPO checklists, workflow manifest and policy-as-code.')
    parser.add_argument('--human-pr-days', type=bounded_int, default=30)
    parser.add_argument('--dependabot-pr-days', type=bounded_int, default=14)
    parser.add_argument('--dormant-days', type=bounded_int, default=180)
    parser.add_argument('--release-days', type=bounded_int, default=90)
    parser.add_argument('--post-reminders', action='store_true',
                        help='Comment on stale non-draft human PRs. Requires --reminder-author.')
    parser.add_argument('--reminder-author', help='Login that posts reminders, e.g. my-app[bot].')
    parser.add_argument('--inner-source-checklist-repo', help='Defaults to ORG/private-ospo-resources.')
    parser.add_argument('--output-dir', default='governance-report')
    parser.add_argument('--repo', action='append', help='Limit to these repository names (repeatable).')
    args = parser.parse_args(argv)
    if not args.org or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]*', args.org):
        parser.error('--org is required and must be a valid organisation name')
    if args.post_reminders and not args.reminder_author:
        parser.error('--post-reminders requires --reminder-author')
    args.inner_source_checklist_repo = args.inner_source_checklist_repo or f'{args.org}/private-ospo-resources'
    return args


def main(argv=None):
    args = parse_args(argv)
    source_root = args.source_root.expanduser().resolve()
    if not source_root.is_dir():
        raise SystemExit(f'OSPO source checkout does not exist: {source_root}')
    scanner = Scanner(args, source_root)
    if not scanner.conftest:
        print('WARNING: conftest not found; Dependabot policy checks will be reported as N/A.', file=sys.stderr)

    all_repos = gh_api(f'orgs/{args.org}/repos?type=all&per_page=100', paginate=True)
    if args.repo:
        all_repos = [r for r in all_repos if r['name'] in args.repo]
    active, skipped, excluded = partition_repositories(all_repos)

    print('Running verified-only TruffleHog scan (credential output is suppressed).', file=sys.stderr)
    secret_results = scanner.secret_scan(active)
    repositories = []
    for repo in active:
        print(f'Scanning {repo["full_name"]}', file=sys.stderr)
        repositories.append(scanner.scan(repo, secret_results[repo['name']]))

    report = {
        'organisation': args.org,
        'generated_at': scanner.now.strftime('%Y-%m-%d %H:%M'),
        'mode': 'post reminders' if args.post_reminders else 'report only',
        'parameters': {key: getattr(args, key) for key in ('human_pr_days', 'dependabot_pr_days', 'dormant_days', 'release_days')},
        'skipped': skipped,
        'excluded': excluded,
        'legend': {
            'public_required_files': scanner.oss_files,
            'private_required_files': scanner.inner_source_files(),
        },
        'repositories': repositories,
    }
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(report)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    (output / 'dashboard.md').write_text(markdown)
    (output / 'dashboard.html').write_text(render_html(report))
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as handle:
            handle.write(markdown)
    print(f'Wrote {output / "dashboard.md"}, {output / "dashboard.html"} and {output / "report.json"}', file=sys.stderr)

    errors = [f'{r["name"]}: {e}' for r in repositories for e in r['errors']]
    for error in errors:
        print(f'ERROR: {error}', file=sys.stderr)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
