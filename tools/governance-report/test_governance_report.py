# SPDX-License-Identifier: Apache-2.0
# © Crown Copyright 2026. This work has been developed by the National Digital Twin Programme and is legally attributed to the UK's Department for Business, Innovation, Science and Trade (BIST) as the governing entity.

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

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
        check = gr.check_sbom([self.release('v0', 1, draft=True)], NOW, 90)
        self.assertEqual(check['status'], gr.NA)
        self.assertIs(check['applicable'], False)

    def test_recent_missing(self):
        releases = [self.release('v2', 5), self.release('v1', 10, ['sbom.spdx.json'])]
        check = gr.check_sbom(releases, NOW, 90)
        self.assertEqual(check['status'], gr.FAIL)
        self.assertEqual(check['summary'], '1/2 missing (last 90d)')

    def test_falls_back_to_latest(self):
        releases = [self.release('v1', 400, ['project-SBOM.json']), self.release('v0', 500)]
        self.assertEqual(gr.check_sbom(releases, NOW, 90)['summary'], '1 with SBOM (latest)')


class ActivityTests(unittest.TestCase):
    def scanner(self):
        scanner = gr.Scanner.__new__(gr.Scanner)
        scanner.governance_paths = gr.read_list_file(gr.GOVERNANCE_PATHS_FILE.read_text())
        scanner.governance_activity_repositories = gr.load_exclusions(gr.GOVERNANCE_ACTIVITY_REPOSITORIES_FILE, 'Org')
        scanner._activity_commit_cache = {}
        scanner.org = 'Org'
        scanner.now = NOW
        scanner.args = SimpleNamespace(dormant_days=180)
        return scanner

    def test_governance_only_paths_and_mixed_changes(self):
        rules = self.scanner().governance_paths
        self.assertTrue(gr.is_governance_only(['.github/workflows/ci.yml', 'LICENSE.md'], rules))
        self.assertFalse(gr.is_governance_only(['.github/workflows/ci.yml', 'src/main.py'], rules))
        self.assertFalse(gr.is_governance_only(['README.md'], rules))
        self.assertFalse(gr.is_governance_only([], rules))

    def test_governance_repositories_count_human_ospo_and_governance_files(self):
        scanner = self.scanner()
        self.assertEqual(scanner.governance_activity_repositories,
                         {'ospo-resources', 'ndt-overwatch', 'private-ospo-resources'})
        for name in scanner.governance_activity_repositories:
            for message in ('feat(OSPO): update policy', 'fix(ci): pin workflow actions'):
                with self.subTest(repository=name, message=message):
                    node = {**commit(2, message=message), 'oid': 'governance-' + message}
                    with patch.object(gr, 'gh_api', return_value={'files': [{'filename': '.github/workflows/ci.yml'}]}):
                        self.assertTrue(scanner.commit_counts_as_activity('Org/' + name, node))
                    self.assertTrue(gr.is_activity_commit(node, include_governance_activity=True))
                    self.assertEqual(gr.is_activity_commit(node), 'ospo' not in message.casefold())

    def test_governance_repositories_still_exclude_bots_and_merges(self):
        scanner = self.scanner()
        with patch.object(gr, 'gh_api') as api:
            for node in (
                commit(1, login='dependabot[bot]', message='build(deps): update'),
                commit(1, login='node-net-repository-writer[bot]', message='feat(OSPO): sync'),
                {**commit(1, message='feat(OSPO): merge'), 'parents': {'totalCount': 2}},
            ):
                self.assertFalse(scanner.commit_counts_as_activity('Org/ospo-resources', node))
        api.assert_not_called()

    def test_application_activity_excludes_ospo_governance_bot_and_merge_commits(self):
        scanner = self.scanner()
        application = {**commit(7, message='feat: update application code'), 'oid': 'application'}
        governance = {**commit(1, message='docs: update governance workflow'), 'oid': 'governance'}
        ospo = {**commit(2, message='chore(OSPO): refresh policy'), 'oid': 'ospo'}
        dependabot = {**commit(3, login='dependabot[bot]', message='build(deps): update'), 'oid': 'dependabot'}
        merge = {**commit(4, message='Merge application release'), 'oid': 'merge', 'parents': {'totalCount': 2}}
        history = {'nodes': [governance, ospo, dependabot, merge, application], 'pageInfo': {'hasNextPage': False}}
        with patch.object(gr, 'gh_api', side_effect=[
                {'files': [{'filename': '.github/workflows/ci.yml'}]},
                {'files': [{'filename': 'src/application.py'}]},
        ]) as api:
            latest_application = scanner.latest_project_commit(
                'Org/ndt-overwatch', 'develop', history, include_governance_activity=False)
        self.assertEqual(latest_application['oid'], 'application')
        self.assertEqual(api.call_count, 2)

        with patch.object(gr, 'gh_api', return_value={'files': [{'filename': '.github/workflows/ci.yml'}]}):
            latest_governance_activity = scanner.latest_project_commit('Org/ndt-overwatch', 'develop', history)
        self.assertEqual(latest_governance_activity['oid'], 'governance')

    def test_governance_exception_applies_to_age_and_branch_activity(self):
        scanner = self.scanner()
        node = {**commit(3, message='feat(OSPO): update governance'), 'oid': 'ospo-work'}
        with patch.object(gr, 'gh_api', return_value={'files': [{'filename': 'LICENSE.md'}]}):
            self.assertTrue(scanner.commit_counts_as_activity('Org/ndt-overwatch', node))
        activity = self.activity([node], [{'name': 'feature/governance', 'target': node}])
        activity['latestHumanCommit'] = node
        activity['includeGovernanceActivity'] = True
        check = gr.check_activity(activity, NOW, 180)
        self.assertEqual(check['status'], gr.OK)
        self.assertIn('3 days since last commit on develop', check['summary'])
        self.assertIn('1 active work branches', check['summary'])

    def test_commit_file_classification_is_cached(self):
        scanner = self.scanner()
        node = {**commit(7, message='fix(ci): pin workflow actions'), 'oid': 'abc'}
        response = {'files': [{'filename': '.github/workflows/ci.yml'}]}
        with patch.object(gr, 'gh_api', return_value=response) as api:
            self.assertFalse(scanner.commit_counts_as_activity('Org/repo', node))
            self.assertFalse(scanner.commit_counts_as_activity('Org/repo', dict(node)))
        self.assertEqual(api.call_count, 1)
        self.assertNotIn('governanceOnly', node)
        self.assertNotIn('includeGovernanceActivity', node)
        self.assertFalse(scanner._activity_commit_cache[('Org/repo', 'abc', False)])

    def test_bot_and_ospo_commits_do_not_request_file_diffs(self):
        scanner = self.scanner()
        with patch.object(gr, 'gh_api') as api:
            self.assertFalse(scanner.commit_counts_as_activity('Org/repo', commit(1, login='dependabot[bot]')))
            self.assertFalse(scanner.commit_counts_as_activity('Org/repo', commit(1, message='fix: OSPO change')))
        api.assert_not_called()

    def test_merge_commits_do_not_refresh_activity(self):
        scanner = self.scanner()
        merge = {**commit(1, message='Promote release'), 'parents': {'totalCount': 2}}
        with patch.object(gr, 'gh_api') as api:
            self.assertFalse(scanner.commit_counts_as_activity('Org/repo', merge))
        api.assert_not_called()
        original = commit(200, message='feat: actual project change')
        self.assertEqual(gr.latest_human_commit([merge, original]), original)

    def test_rename_of_project_file_to_governance_path_counts(self):
        scanner = self.scanner()
        node = {**commit(7), 'oid': 'rename'}
        with patch.object(gr, 'gh_api', return_value={'files': [{
            'filename': '.github/example.py', 'previous_filename': 'src/example.py',
        }]}):
            self.assertTrue(scanner.commit_counts_as_activity('Org/repo', node))

    def test_governance_file_pagination_finds_project_change(self):
        scanner = self.scanner()
        pages = [{'files': [{'filename': '.github/workflows/ci.yml'}] * 100},
                 {'files': [{'filename': 'src/main.py'}]}]
        with patch.object(gr, 'gh_api', side_effect=pages) as api:
            self.assertTrue(scanner.commit_counts_as_activity('Org/repo', {**commit(2), 'oid': 'large'}))
        self.assertIn('page=2', api.call_args_list[-1].args[0])

    def test_incomplete_commit_diff_is_not_counted_as_activity(self):
        scanner = self.scanner()
        with patch.object(gr, 'gh_api', return_value={}), self.assertRaises(gr.ApiError):
            scanner.commit_counts_as_activity('Org/repo', {**commit(2), 'oid': 'incomplete'})

    def test_history_pages_past_governance_to_project_commit(self):
        scanner = self.scanner()
        workflow = {**commit(7, message='fix(ci): pin workflow actions'), 'oid': 'workflow'}
        project = {**commit(200), 'oid': 'project'}
        history = {'nodes': [workflow], 'pageInfo': {'hasNextPage': True, 'endCursor': 'cursor1'}}
        responses = [
            {'files': [{'filename': '.github/workflows/ci.yml'}]},
            {'data': {'repository': {'ref': {'target': {'history': {
                'nodes': [project], 'pageInfo': {'hasNextPage': False},
            }}}}}},
            {'files': [{'filename': 'src/main.py'}]},
        ]
        with patch.object(gr, 'gh_api', side_effect=responses):
            latest = scanner.latest_project_commit('Org/repo', 'develop', history)
        self.assertEqual(latest['oid'], 'project')
        activity = self.activity([workflow])
        activity['latestHumanCommit'] = latest
        self.assertIn('200 days since last commit on develop', gr.check_activity(activity, NOW, 180)['summary'])

    def test_older_project_work_survives_governance_branch_tip(self):
        scanner = self.scanner()
        workflow = {**commit(1), 'oid': 'workflow'}
        project = {**commit(5), 'oid': 'project'}
        activity = self.activity([], [{'name': 'feature/work', 'target': workflow}])
        responses = [
            {'data': {'repository': activity}},
            {'files': [{'filename': '.github/workflows/ci.yml'}]},
            {'data': {'repository': {'ref': {'target': {'history': {
                'nodes': [workflow, project], 'pageInfo': {'hasNextPage': False},
            }}}}}},
            {'files': [{'filename': 'src/main.py'}]},
        ]
        with patch.object(gr, 'gh_api', side_effect=responses):
            activity = scanner.repository_activity('Org/repo', 'main')
        self.assertEqual(activity['refs']['nodes'][0]['target']['oid'], 'project')
        self.assertEqual(gr.check_activity(activity, NOW, 180)['status'], gr.OK)

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

    def test_activity_label_names_actual_default_branch(self):
        activity = {'develop': None, 'activityBranch': 'main',
                    'defaultBranchRef': {'target': {'history': {'nodes': [commit(3)]}}}, 'refs': {'nodes': []}}
        check = gr.check_activity(activity, NOW, 180)
        self.assertIn('3 days since last commit on main', check['summary'])
        self.assertNotIn('on develop', check['summary'])

    def test_exact_days_since_human_commit_ignores_ospo_and_bot_commits(self):
        commits = [
            commit(2, 'Dependabot[bot]', 'dependabot[bot]'),
            commit(1, 'Alice', 'alice', 'docs: update process', 'OSPO review and workflow notes'),
            commit(17, 'Bob', 'bob', 'fix: real project work'),
        ]
        check = gr.check_activity(self.activity(commits), NOW, 180)
        self.assertEqual(check['status'], gr.OK)
        self.assertIn('17 days since last commit on develop', check['summary'])

    def test_ospo_only_commits_are_not_human_activity(self):
        commits = [commit(1, 'Alice', 'alice', 'fix: update config for OSPO request')]
        self.assertIsNone(gr.latest_human_commit(commits))


class WorkflowSourceTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.source_root = Path(directory.name) / 'develop'
        self.workflow_root = Path(directory.name) / 'main'
        for root in (self.source_root, self.workflow_root):
            (root / '.github/workflows').mkdir(parents=True)
        self.workflow_path = '.github/workflows/published.yml'
        (self.source_root / 'oss-checklist-files.txt').write_text('README.md\nLICENSE.md\n')
        (self.source_root / 'tools/policy-as-code/policy').mkdir(parents=True)
        (self.source_root / 'organisation-required-workflows.txt').write_text(
            self.workflow_path + '\n.github/workflows/stale-pr-alerts.yml\n')
        (self.source_root / self.workflow_path).write_bytes(b'develop workflow\n')
        (self.source_root / '.github/workflows/stale-pr-alerts.yml').write_bytes(b'develop only\n')
        (self.workflow_root / 'organisation-required-workflows.txt').write_text(self.workflow_path + '\n')
        (self.workflow_root / self.workflow_path).write_bytes(b'published main workflow\n')
        self.args = gr.parse_args(['--org', 'Org', '--source-root', str(self.source_root),
                                   '--workflow-source-root', str(self.workflow_root)])

    def test_main_manifest_and_hashes_are_independent_of_develop_policy(self):
        scanner = gr.Scanner(self.args, self.source_root, self.workflow_root)
        self.assertEqual(scanner.expected_workflows, {
            'published.yml': gr.git_blob_sha(b'published main workflow\n'),
        })
        self.assertNotIn('stale-pr-alerts.yml', scanner.expected_workflows)
        self.assertEqual(scanner.policy_dir, self.source_root / 'tools/policy-as-code/policy')
        self.assertEqual(scanner.oss_files, ['README.md', 'LICENSE.md'])
        main_blobs = {self.workflow_path: gr.git_blob_sha(b'published main workflow\n')}
        self.assertEqual(gr.check_workflows(main_blobs, scanner.expected_workflows)['status'], gr.OK)
        develop_blobs = {self.workflow_path: gr.git_blob_sha(b'develop workflow\n')}
        self.assertEqual(gr.check_workflows(develop_blobs, scanner.expected_workflows)['status'], gr.WARN)

    def test_default_workflow_root_does_not_follow_policy_source_root(self):
        args = gr.parse_args(['--org', 'Org', '--source-root', str(self.source_root)])
        self.assertEqual(args.workflow_source_root, Path(gr.__file__).resolve().parents[2] / 'ospo-workflows')
        self.assertNotEqual(args.workflow_source_root, args.source_root)

    def test_explicit_workflow_root(self):
        self.assertEqual(self.args.workflow_source_root, self.workflow_root)

    def test_missing_workflow_checkout_aborts_before_api_calls(self):
        for path in (self.workflow_root / 'missing', self.workflow_root / 'organisation-required-workflows.txt'):
            with self.subTest(path=path), patch.object(gr, 'gh_api') as api:
                with self.assertRaisesRegex(SystemExit, 'workflow source checkout does not exist'):
                    gr.main(['--org', 'Org', '--source-root', str(self.source_root),
                             '--workflow-source-root', str(path)])
                api.assert_not_called()

    def test_missing_workflow_manifest_aborts_before_api_calls(self):
        (self.workflow_root / 'organisation-required-workflows.txt').unlink()
        with patch.object(gr, 'gh_api') as api:
            with self.assertRaisesRegex(SystemExit, 'workflow source manifest does not exist'):
                gr.main(['--org', 'Org', '--source-root', str(self.source_root),
                         '--workflow-source-root', str(self.workflow_root)])
            api.assert_not_called()

    def test_missing_listed_workflow_is_not_silently_omitted(self):
        (self.workflow_root / self.workflow_path).unlink()
        with patch.object(gr, 'gh_api') as api:
            with self.assertRaisesRegex(SystemExit, 'Listed OSPO source workflows missing.*published.yml'):
                gr.main(['--org', 'Org', '--source-root', str(self.source_root),
                         '--workflow-source-root', str(self.workflow_root)])
            api.assert_not_called()


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

    def test_scanner_exports_qualified_activity_without_parsing_summary(self):
        scanner = gr.Scanner.__new__(gr.Scanner)
        scanner.now = NOW
        scanner.args = SimpleNamespace(dormant_days=180, release_days=90, dependabot_pr_days=14, human_pr_days=30)
        scanner.oss_files = []
        scanner.expected_workflows = {}
        scanner.pr_token = None
        repo = {'name': 'ndt-overwatch', 'full_name': 'Org/ndt-overwatch', 'default_branch': 'main',
                'html_url': 'https://example.invalid/repo', 'visibility': 'public'}
        for branch in ('develop', 'main'):
            with self.subTest(branch=branch):
                activity = {'activityBranch': branch, 'latestHumanCommit': commit(22),
                            'latestApplicationCommit': commit(70),
                            'develop': {'target': {}} if branch == 'develop' else None}
                def api(endpoint, **kwargs):
                    if '/git/trees/' in endpoint:
                        return {'tree': []}
                    return []
                with patch.object(gr, 'gh_api', side_effect=api), \
                        patch.object(scanner, 'repository_activity', return_value=activity), \
                        patch.object(scanner, 'dependabot_config', return_value=gr.result(gr.OK, 'passed')), \
                        patch.object(scanner, 'repo_setting', return_value=True), \
                        patch.object(scanner, 'dependabot_auto_merge', return_value=gr.result(gr.OK, 'passed')), \
                        patch.object(scanner, 'auto_backmerge', return_value=gr.result(gr.OK, 'passed')), \
                        patch.object(scanner, 'remind', return_value={}):
                    entry = scanner.scan(repo, gr.check_secret_scan(0))
                self.assertEqual(entry['activity'], {
                    'branch': branch,
                    'last_commit_at': iso(22),
                    'last_application_commit_at': iso(70),
                })
                self.assertEqual(entry['errors'], [])

    def test_delete_branch(self):
        self.assertEqual(gr.check_delete_branch(None)['status'], gr.NA)
        self.assertEqual(gr.check_delete_branch(False)['status'], gr.FAIL)
        self.assertEqual(gr.check_delete_branch(True)['status'], gr.OK)

    def test_dependabot_auto_merge_outcomes(self):
        run = {'id': 12, 'run_number': 4, 'html_url': 'https://example.invalid/run/12',
               'created_at': '2026-10-22T00:00:00Z', 'status': 'completed', 'conclusion': 'success'}
        enabled = [{'steps': [{'name': 'Enable auto-merge for the pull request', 'conclusion': 'success'}]}]
        self.assertEqual(gr.check_dependabot_auto_merge(run, enabled)['status'], gr.OK)
        disabled = [{'steps': [{'name': 'Enable auto-merge for the pull request', 'conclusion': 'skipped'}]}]
        self.assertEqual(gr.check_dependabot_auto_merge(run, disabled)['status'], gr.WARN)
        failed = [{ 'steps': [{'name': 'Fetch GitHub App token for target repo', 'conclusion': 'failure'}]}]
        check = gr.check_dependabot_auto_merge({**run, 'conclusion': 'failure'}, failed)
        self.assertEqual(check['status'], gr.FAIL)
        self.assertIn('Fetch GitHub App token', str(check['details']))
        self.assertEqual(gr.check_dependabot_auto_merge({**run, 'status': 'in_progress', 'conclusion': None}, [])['status'], gr.WARN)
        non_actions = [{'steps': [{'name': 'Skip non-GitHub Actions updates', 'conclusion': 'success'}]}]
        self.assertIsNone(gr.check_dependabot_auto_merge(run, non_actions))

    def test_dependabot_auto_merge_missing_and_inaccessible(self):
        scanner = gr.Scanner.__new__(gr.Scanner)
        self.assertEqual(scanner.dependabot_auto_merge('Org/repo', set())['status'], gr.FAIL)
        paths = {'.github/workflows/auto-merge-dependabot-pull-requests.yml'}
        with patch.object(gr, 'gh_api', side_effect=gr.ApiError('HTTP 403')):
            self.assertEqual(scanner.dependabot_auto_merge('Org/repo', paths)['status'], gr.NA)

    def test_dependabot_auto_merge_ignores_skipped_runs(self):
        scanner = gr.Scanner.__new__(gr.Scanner)
        paths = {'.github/workflows/auto-merge-dependabot-pull-requests.yml'}
        runs = [
            {'id': 3, 'conclusion': 'skipped'},
            {'id': 2, 'conclusion': 'success', 'status': 'completed', 'html_url': 'https://example.invalid/run/2'},
            {'id': 1, 'conclusion': 'success', 'status': 'completed', 'html_url': 'https://example.invalid/run/1'},
        ]
        responses = [
            {'workflow_runs': runs},
            {'jobs': [{'steps': [{'name': 'Skip non-GitHub Actions updates', 'conclusion': 'success'}]}]},
            {'jobs': [{'steps': [{'name': 'Enable auto-merge for the pull request', 'conclusion': 'success'}]}]},
        ]
        with patch.object(gr, 'gh_api', side_effect=responses) as api:
            self.assertEqual(scanner.dependabot_auto_merge('Org/repo', paths)['status'], gr.OK)
        self.assertEqual(api.call_count, 3)

    def test_dependabot_auto_merge_no_applicable_runs(self):
        scanner = gr.Scanner.__new__(gr.Scanner)
        paths = {'.github/workflows/auto-merge-dependabot-pull-requests.yml'}
        with patch.object(gr, 'gh_api', return_value={'workflow_runs': [{'conclusion': 'skipped'}]}):
            self.assertEqual(scanner.dependabot_auto_merge('Org/repo', paths)['status'], gr.NA)

    def test_github_dot_repo_is_excluded(self):
        repos = [
            {'name': '.github'}, {'name': 'opa-pov'}, {'name': 'active'},
            {'name': 'archived', 'archived': True}, {'name': 'disabled', 'disabled': True},
        ]
        names = gr.load_exclusions(gr.DEFAULT_EXCLUSIONS_FILE, 'org')
        active, skipped, excluded = gr.partition_repositories(repos, names)
        self.assertEqual([repo['name'] for repo in active], ['active'])
        self.assertEqual(skipped, ['archived', 'disabled'])
        self.assertEqual(excluded, ['.github', 'opa-pov'])

    def test_configurable_exclusions_before_scan_and_totals(self):
        names = gr.parse_args(['--org', 'org', '--exclude-repos', 'Repo-A, Org/repo-b\nrepo-c']).exclude_repos
        repos = [{'name': name} for name in ('.github', 'repo-a', 'repo-b', 'repo-c', 'keep')]
        active, skipped, excluded = gr.partition_repositories(repos, names)
        self.assertEqual([repo['name'] for repo in active], ['keep'])
        self.assertEqual(excluded, ['.github', 'repo-a', 'repo-b', 'repo-c'])
        self.assertEqual(skipped, [])
        self.assertEqual(gr.parse_args(['--org', 'org', '--exclude-repos', 'a,b']).exclude_repos, {'.github', 'opa-pov', 'a', 'b'})

    def test_exclusion_file_comments_case_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'excluded.txt'
            path.write_text('# Exclusions\n\n  Repo-A\norg/REPO-B\nrepo-a\n', encoding='utf-8')
            self.assertEqual(gr.load_exclusions(path, 'Org'), {'repo-a', 'repo-b'})

    def test_custom_exclusion_file_combines_with_runtime_names(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'excluded.txt'
            path.write_text('repo-a\n', encoding='utf-8')
            args = gr.parse_args(['--org', 'org', '--exclusions-file', str(path), '--exclude-repos', 'repo-b'])
            self.assertEqual(args.exclude_repos, {'repo-a', 'repo-b'})

    def test_empty_file_has_no_hardcoded_exclusions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'excluded.txt'
            path.write_text('# No exclusions\n', encoding='utf-8')
            self.assertEqual(gr.load_exclusions(path, 'Org'), set())
            active, _, excluded = gr.partition_repositories([{'name': 'opa-pov'}], gr.load_exclusions(path, 'Org'))
            self.assertEqual([repo['name'] for repo in active], ['opa-pov'])
            self.assertEqual(excluded, [])

    def test_missing_exclusion_file_aborts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing.txt'
            with patch('sys.stderr'), self.assertRaises(SystemExit) as error:
                gr.parse_args(['--org', 'org', '--exclusions-file', str(path)])
            self.assertEqual(error.exception.code, 2)

    def test_invalid_exclusion_names_rejected(self):
        for value in ('other/repo', 'https://github.com/org/repo', 'repo*'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                gr.parse_exclusions(value, 'org')

    def test_group_tables_keep_visibility_separate(self):
        repos = [
            {'name': 'public-repo', 'visibility': 'public'},
            {'name': 'private-repo', 'visibility': 'private'},
            {'name': 'internal-repo', 'visibility': 'internal'},
        ]
        groups = gr.repository_groups(repos)
        self.assertEqual([repo['name'] for repo in groups[0][1]], ['public-repo'])
        self.assertEqual([repo['name'] for repo in groups[1][1]], ['private-repo', 'internal-repo'])
        report = {
            'organisation': 'org', 'generated_at': 'now', 'mode': 'report only', 'skipped': [],
            'parameters': {'human_pr_days': 30, 'dependabot_pr_days': 14, 'dormant_days': 180, 'release_days': 90},
            'repositories': [{**repo, 'url': 'https://example.invalid/' + repo['name'],
                              'default_branch': 'main', 'errors': [], 'checks': {}} for repo in repos],
        }
        for renderer in (gr.render_markdown, gr.render_html):
            output = renderer(report)
            public_section = output.split('Public repositories (1)', 1)[1].split('Private and internal repositories (2)', 1)[0]
            self.assertIn('public-repo', public_section)
            self.assertNotIn('private-repo', public_section)
            self.assertNotIn('internal-repo', public_section)

    def test_status_badges_are_colored_without_inline_css(self):
        badge_root = Path(gr.__file__).resolve().parents[2] / '.github' / 'badges'
        for status, color in gr.STATUS_COLORS.items():
            with self.subTest(status=status):
                badge = gr.markdown_status(status)
                self.assertIn('![' + status + ']', badge)
                self.assertIn(f'{gr.STATUS_BADGE_BASE_URL}/{gr.STATUS_BADGE_FILES[status]}', badge)
                self.assertNotIn('shields.io', badge)
                svg = ET.parse(badge_root / gr.STATUS_BADGE_FILES[status]).getroot()
                self.assertEqual(svg.find('{http://www.w3.org/2000/svg}rect').attrib['fill'], color)

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
        self.assertIn('| Repository | Develop<br>branch |', markdown)
        self.assertIn(gr.markdown_status(gr.FAIL) + '<br><sub><sup>a\\|b</sup></sub>', markdown)
        self.assertIn('### Public repositories (1)', markdown)
        self.assertIn('### Private and internal repositories (0)', markdown)
        self.assertIn('Each cell shows the full status and a short result.', markdown)
        self.assertIn('Missing file: a\\|b', markdown)
        self.assertIn('Human PR age', markdown)
        self.assertIn('no separate FAIL age threshold is currently configured', markdown)
        self.assertIn('published on `National-Node-Net/ospo-resources` `main`, not `develop`', markdown)
        self.assertNotIn('Related tools', markdown)
        self.assertNotIn('Not covered by this report', markdown)
        self.assertNotIn('| Repository | Visibility | Default |', markdown)
        self.assertTrue(markdown.isascii())
        dashboard_html = gr.render_html(report)
        self.assertIn('.warn{color:#9a6700}', dashboard_html)
        self.assertIn('<span class="status fail">FAIL</span>', dashboard_html)
        self.assertIn('.result-summary{font-size:.75em', dashboard_html)
        self.assertNotIn('font-family', dashboard_html)
        self.assertNotIn('The font is inherited from the viewer', dashboard_html)
        self.assertIn('Dependabot GitHub Actions<br>auto-merge workflow', dashboard_html)
        self.assertNotIn('Repository auto-merge enabled', dashboard_html)
        self.assertIn('published on <code>National-Node-Net/ospo-resources</code> <code>main</code>', dashboard_html)
        legend = dashboard_html.split('<h3>Templates and policy</h3>', 1)[1].split('</ul>', 1)[0]
        self.assertEqual(legend.count('<li>'), 11)
        self.assertNotIn('<p>', legend)


if __name__ == '__main__':
    unittest.main()
