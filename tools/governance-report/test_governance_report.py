# SPDX-License-Identifier: Apache-2.0
# © Crown Copyright 2026. This work has been developed by the National Digital Twin Programme and is legally attributed to the UK's Department for Business, Innovation, Science and Trade (BIST) as the governing entity.

import unittest
from unittest.mock import patch
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone

import governance_report as gr

NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).strftime('%Y-%m-%dT%H:%M:%SZ')


def pr(number, login, days_ago, user_type='User', draft=False, base='develop', head='feature/x'):
    return {
        'number': number, 'title': f'PR {number}', 'created_at': iso(days_ago), 'draft': draft,
        'user': {'login': login, 'type': user_type}, 'base': {'ref': base}, 'head': {'ref': head},
    }


def commit(days_ago, name='Alice', login='alice', message='', body=''):
    return {
        'committedDate': iso(days_ago), 'messageHeadline': message, 'messageBody': body,
        'author': {'name': name, 'user': {'login': login} if login else None},
    }


class DevelopTests(unittest.TestCase):
    def test_present(self):
        self.assertEqual(gr.check_develop('main', True)['status'], gr.OK)

    def test_missing_with_main_default(self):
        self.assertEqual(gr.check_develop('main', False)['status'], gr.FAIL)

    def test_other_default_not_applicable(self):
        self.assertEqual(gr.check_develop('process', False)['status'], gr.NA)


class FileTests(unittest.TestCase):
    def test_missing_files_listed(self):
        check = gr.check_required_paths({'README.md'}, ['README.md', 'LICENSE.md'], 'file')
        self.assertEqual(check['status'], gr.FAIL)
        self.assertEqual(check['summary'], 'LICENSE.md')

    def test_all_present(self):
        self.assertEqual(gr.check_required_paths({'a', 'b'}, ['a', 'b'], 'file')['status'], gr.OK)


class DependabotPrTests(unittest.TestCase):
    def test_threshold_is_exclusive(self):
        check = gr.check_dependabot_prs([pr(1, gr.DEPENDABOT, 14, 'Bot')], NOW, 14)
        self.assertEqual(check['status'], gr.OK)

    def test_stale_and_very_old(self):
        prs = [pr(1, gr.DEPENDABOT, 15, 'Bot'), pr(2, gr.DEPENDABOT, 91, 'Bot'), pr(3, 'alice', 200)]
        check = gr.check_dependabot_prs(prs, NOW, 14)
        self.assertEqual(check['status'], gr.FAIL)
        self.assertEqual(check['summary'], '2 open, 2 >14d, 1 >90d')


class HumanPrTests(unittest.TestCase):
    def test_bots_excluded(self):
        prs = [pr(1, gr.DEPENDABOT, 100, 'Bot'), pr(2, 'other-app[bot]', 100, 'Bot')]
        self.assertEqual(gr.check_human_prs(prs, NOW, 30)['status'], gr.OK)

    def test_flags(self):
        prs = [pr(1, 'alice', 31, draft=True), pr(2, 'bob', 40, base='main'), pr(3, 'carol', 40, base='main', head='release/1')]
        check = gr.check_human_prs(prs, NOW, 30, {2: 'reminded'})
        self.assertEqual(check['status'], gr.WARN)
        self.assertIn('[draft]', check['details'][0])
        self.assertIn('[targets main, reminded]', check['details'][1])
        self.assertNotIn('targets main', check['details'][2])


class ReminderTests(unittest.TestCase):
    def comment(self, login, days_ago, marker=True):
        return {'user': {'login': login}, 'created_at': iso(days_ago), 'body': gr.HUMAN_PR_MARKER if marker else 'hi'}

    def test_recent_bot_reminder_suppresses(self):
        self.assertFalse(gr.reminder_due([self.comment('app[bot]', 3)], 'app[bot]', NOW))

    def test_old_reminder_spoof_and_unmarked_do_not_suppress(self):
        comments = [self.comment('app[bot]', 6), self.comment('alice', 1), self.comment('app[bot]', 1, marker=False)]
        self.assertTrue(gr.reminder_due(comments, 'app[bot]', NOW))

    def test_body_mentions_author(self):
        body = gr.reminder_body(pr(1, 'alice', 45), NOW)
        self.assertTrue(body.startswith(gr.HUMAN_PR_MARKER))
        self.assertIn('@alice', body)
        self.assertTrue(body.isascii())


class SbomTests(unittest.TestCase):
    def release(self, tag, days_ago, assets=(), draft=False):
        return {'tag_name': tag, 'published_at': iso(days_ago), 'draft': draft, 'assets': [{'name': a} for a in assets]}

    def test_no_releases(self):
        self.assertEqual(gr.check_sbom([self.release('v0', 1, draft=True)], NOW, 90)['status'], gr.NA)

    def test_recent_missing(self):
        releases = [self.release('v2', 5), self.release('v1', 10, ['sbom.spdx.json'])]
        check = gr.check_sbom(releases, NOW, 90)
        self.assertEqual(check['status'], gr.FAIL)
        self.assertEqual(check['summary'], '1/2 missing (last 90d)')

    def test_falls_back_to_latest(self):
        releases = [self.release('v1', 400, ['project-SBOM.json']), self.release('v0', 500)]
        self.assertEqual(gr.check_sbom(releases, NOW, 90)['summary'], '1 with SBOM (latest)')


class ActivityTests(unittest.TestCase):
    def activity(self, develop_nodes, refs=()):
        history = {'target': {'history': {'nodes': develop_nodes}}}
        return {'develop': history, 'defaultBranchRef': {'target': {'history': {'nodes': []}}}, 'refs': {'nodes': list(refs)}}

    def test_only_bot_commits_is_dormant(self):
        nodes = [commit(5, 'dependabot[bot]', None), commit(6, 'x', 'node-net-ospo-automation[bot]')]
        refs = [{'name': 'dependabot/npm/x', 'target': commit(1)}, {'name': 'feature/old', 'target': commit(200)}]
        self.assertEqual(gr.check_activity(self.activity(nodes, refs), NOW, 180)['status'], gr.WARN)

    def test_recent_feature_branch_is_active(self):
        refs = [{'name': 'feature/new', 'target': commit(3)}]
        self.assertEqual(gr.check_activity(self.activity([], refs), NOW, 180)['status'], gr.OK)

    def test_ospo_commit_message_does_not_count_as_active_branch(self):
        refs = [{'name': 'feature/ospo', 'target': commit(3, 'Alice', 'alice', 'feature work', 'Discussed with OSPO')}]
        check = gr.check_activity(self.activity([], refs), NOW, 180)
        self.assertEqual(check['status'], gr.WARN)
        self.assertIn('0 active work branches', check['summary'])

    def test_human_commit_is_active(self):
        self.assertEqual(gr.check_activity(self.activity([commit(3, 'Bob', None)]), NOW, 180)['status'], gr.OK)

    def test_exact_days_since_human_commit_ignores_ospo_and_bot_commits(self):
        commits = [
            commit(2, 'Dependabot[bot]', 'dependabot[bot]'),
            commit(1, 'Alice', 'alice', 'docs: update process', 'OSPO review and workflow notes'),
            commit(17, 'Bob', 'bob', 'fix: real project work'),
        ]
        check = gr.check_activity(self.activity(commits), NOW, 180)
        self.assertEqual(check['status'], gr.OK)
        self.assertIn('17 days since last human commit', check['summary'])

    def test_ospo_only_commits_are_not_human_activity(self):
        commits = [commit(1, 'Alice', 'alice', 'fix: update config for OSPO request')]
        self.assertIsNone(gr.latest_human_commit(commits))


class OtherCheckTests(unittest.TestCase):
    def test_local_history_scan_uses_reader_token_for_clone_only(self):
        scanner = gr.Scanner.__new__(gr.Scanner)
        repo = {'name': 'repo-a', 'full_name': 'Org/repo-a'}
        calls = []

        def execute(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(returncode=0, stdout='')

        with patch.object(gr.subprocess, 'run', side_effect=execute):
            check = scanner.scan_git_history(repo, 'test-reader-token')
        self.assertEqual(check['status'], gr.OK)
        clone, clone_options = calls[0]
        self.assertEqual(clone[:3], ['git', 'clone', '--no-checkout'])
        self.assertNotIn('test-reader-token', str(clone))
        self.assertIn('AUTHORIZATION: basic ', clone_options['env']['GIT_CONFIG_VALUE_0'])
        self.assertEqual(calls[1][0][-2:], ['read-tree', 'HEAD'])
        scan, scan_options = calls[2]
        self.assertIn('file:///scan/repository', scan)
        self.assertIn('--fail-on-scan-errors', scan)
        self.assertIn('readonly', ' '.join(scan))
        self.assertNotIn('env', scan_options)
        self.assertNotIn('-e', scan)
        self.assertEqual(calls[3][0][:3], ['docker', 'rm', '-f'])

    def test_clone_failure_does_not_run_scanner(self):
        scanner = gr.Scanner.__new__(gr.Scanner)
        repo = {'name': 'repo-a', 'full_name': 'Org/repo-a'}
        with patch.object(gr.subprocess, 'run', return_value=SimpleNamespace(returncode=128, stdout='')) as execute:
            check = scanner.scan_git_history(repo, 'test-reader-token')
        self.assertEqual(check['status'], gr.ERROR)
        self.assertIn('clone failed', check['summary'])
        self.assertEqual(execute.call_count, 2)

    def test_settings_get_uses_writer_token_and_cache(self):
        scanner = gr.Scanner.__new__(gr.Scanner)
        scanner.settings_token = 'test-writer-token'
        state = {}
        with patch.object(gr, 'gh_api', return_value={'delete_branch_on_merge': False, 'allow_auto_merge': True}) as api:
            self.assertFalse(scanner.repo_setting('Org/repo-a', state, 'delete_branch_on_merge'))
            self.assertTrue(scanner.repo_setting('Org/repo-a', state, 'allow_auto_merge'))
        api.assert_called_once_with('repos/Org/repo-a', token='test-writer-token')

    def test_scanner_error_is_processing_error(self):
        scanner = gr.Scanner.__new__(gr.Scanner)
        repo = {'name': 'repo-a', 'full_name': 'Org/repo-a', 'default_branch': 'main', 'html_url': 'https://example.invalid'}
        with patch.object(gr, 'gh_api', side_effect=gr.ApiError('unavailable')):
            entry = scanner.scan(repo, gr.check_secret_scan(0, error='scanner failed'))
        self.assertIn('secret_scan: scanner failed', entry['errors'])

    def test_delete_branch(self):
        self.assertEqual(gr.check_delete_branch(None)['status'], gr.NA)
        self.assertEqual(gr.check_delete_branch(False)['status'], gr.FAIL)
        self.assertEqual(gr.check_delete_branch(True)['status'], gr.OK)

    def test_allow_auto_merge(self):
        self.assertEqual(gr.check_allow_auto_merge(None)['status'], gr.NA)
        self.assertEqual(gr.check_allow_auto_merge(False)['status'], gr.FAIL)
        self.assertEqual(gr.check_allow_auto_merge(True)['status'], gr.OK)

    def test_github_dot_repo_is_excluded(self):
        repos = [
            {'name': '.github'}, {'name': 'active'},
            {'name': 'archived', 'archived': True}, {'name': 'disabled', 'disabled': True},
        ]
        active, skipped, excluded = gr.partition_repositories(repos)
        self.assertEqual([repo['name'] for repo in active], ['active'])
        self.assertEqual(skipped, ['archived', 'disabled'])
        self.assertEqual(excluded, ['.github'])

    def test_trufflehog_output_counts_without_retaining_credentials(self):
        repos = [{'name': 'repo-a', 'full_name': 'Org/repo-a'}]
        stdout = '{"Verified":true,"Raw":"sensitive-example","SourceMetadata":{"Data":{"Git":{"repository":"https://github.com/Org/repo-a.git"}}}}\n'
        counts, unmapped = gr.parse_trufflehog_output(stdout, repos)
        check = gr.check_secret_scan(counts['repo-a'])
        self.assertEqual(counts['repo-a'], 1)
        self.assertEqual(unmapped, 0)
        self.assertEqual(check['status'], gr.FAIL)
        self.assertNotIn('sensitive-example', str(check))

    def test_trufflehog_result_localizes_error_and_suppresses_output(self):
        repo = {'name': 'repo-a', 'full_name': 'Org/repo-a'}
        failed = gr.check_trufflehog_result(1, 'scanner stderr with sensitive data', repo)
        passed = gr.check_trufflehog_result(0, '', repo)
        self.assertEqual(failed['status'], gr.ERROR)
        self.assertNotIn('sensitive data', str(failed))
        self.assertEqual(passed['status'], gr.OK)

    def test_local_git_finding_attribution_and_malformed_output(self):
        repo = {'name': 'repo-a', 'full_name': 'Org/repo-a'}
        finding = '{"Verified":true,"Raw":"sensitive-example","SourceMetadata":{"Data":{"Git":{"repository":"file:///scan/repository.git"}}}}'
        check = gr.check_trufflehog_result(0, finding, repo, local_repository=True)
        self.assertEqual(check['status'], gr.FAIL)
        self.assertIn('1 verified', check['summary'])
        self.assertNotIn('sensitive-example', str(check))
        self.assertEqual(gr.check_trufflehog_result(0, 'not json', repo)['status'], gr.ERROR)

    def test_dependabot_config(self):
        self.assertEqual(gr.check_dependabot_config(None, [])['status'], gr.FAIL)
        self.assertEqual(gr.check_dependabot_config('.github/dependabot.yml', [], evaluated=False)['status'], gr.NA)
        self.assertEqual(gr.check_dependabot_config('.github/dependabot.yml', ['x'])['status'], gr.FAIL)

    def test_workflows(self):
        expected = {'a.yml': 'sha-a', 'b.yml': 'sha-b'}
        self.assertEqual(gr.check_workflows({'.github/workflows/a.yml': 'sha-a'}, expected)['status'], gr.FAIL)
        self.assertEqual(gr.check_workflows(
            {'.github/workflows/a.yml': 'old', '.github/workflows/b.yml': 'sha-b'}, expected)['status'], gr.WARN)

    def test_auto_backmerge_missing_or_no_attempts(self):
        self.assertEqual(gr.check_auto_backmerge(False, [])['status'], gr.FAIL)
        self.assertEqual(gr.check_auto_backmerge(True, [])['status'], gr.NA)
        skipped = [{'status': 'completed', 'conclusion': 'skipped'}]
        self.assertEqual(gr.check_auto_backmerge(True, skipped)['status'], gr.NA)

    def test_auto_backmerge_ignores_skipped_unmerged_pr_runs(self):
        runs = [
            {'status': 'completed', 'conclusion': 'skipped'},
            {'status': 'completed', 'conclusion': 'success', 'run_number': 42, 'created_at': '2026-10-12T00:00:00Z'},
        ]
        check = gr.check_auto_backmerge(True, runs)
        self.assertEqual(check['status'], gr.OK)
        self.assertIn('passed run #42', check['summary'])

    def test_auto_backmerge_failure_and_pending(self):
        failed = gr.check_auto_backmerge(True, [{
            'status': 'completed', 'conclusion': 'failure', 'run_number': 7,
            'created_at': '2026-10-10T00:00:00Z', 'html_url': 'https://example.invalid/run/7',
        }])
        self.assertEqual(failed['status'], gr.FAIL)
        self.assertIn('https://example.invalid/run/7', failed['summary'])
        self.assertIn('https://example.invalid/run/7', failed['details'][0])
        pending = gr.check_auto_backmerge(True, [{'status': 'in_progress', 'conclusion': None, 'run_number': 8}])
        self.assertEqual(pending['status'], gr.WARN)

    def test_git_blob_sha_matches_git(self):
        self.assertEqual(gr.git_blob_sha(b''), 'e69de29bb2d1d6434b8b29ae775ad8c2e48c5391')

    def test_markdown_escapes_and_is_ascii(self):
        report = {
            'organisation': 'org', 'generated_at': 'now', 'mode': 'report only', 'skipped': ['old'],
            'parameters': {'human_pr_days': 30, 'dependabot_pr_days': 14, 'dormant_days': 180, 'release_days': 90},
            'repositories': [{
                'name': 'r', 'url': 'https://example.invalid/r', 'visibility': 'public', 'default_branch': 'main',
                'errors': [], 'checks': {'files': gr.result(gr.FAIL, 'a|b', ['Missing file: a|b'])},
            }],
        }
        markdown = gr.render_markdown(report)
        self.assertIn('| Repository | <small>Develop<br>branch</small> |', markdown)
        self.assertIn('<small><span style="color:#cf222e"><strong>FAIL</strong></span><br>a\\|b</small>', markdown)
        self.assertIn('Each cell shows the full status and a short result.', markdown)
        self.assertIn('Missing file: a\\|b', markdown)
        self.assertIn('Human PR age', markdown)
        self.assertIn('no separate FAIL age threshold is currently configured', markdown)
        self.assertNotIn('Related tools', markdown)
        self.assertNotIn('Not covered by this report', markdown)
        self.assertNotIn('| Repository | Visibility | Default |', markdown)
        self.assertTrue(markdown.isascii())
        dashboard_html = gr.render_html(report)
        self.assertIn('.warn{color:#9a6700}', dashboard_html)
        self.assertIn('<span class="status fail">FAIL</span>', dashboard_html)
        self.assertNotIn('font-family', dashboard_html)


if __name__ == '__main__':
    unittest.main()
