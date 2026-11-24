# SPDX-License-Identifier: Apache-2.0
# © Crown Copyright 2026. This work has been developed by the National Digital Twin Programme and is legally attributed to the UK's Department for Business, Innovation, Science and Trade (BIST) as the governing entity.

import contextlib
import copy
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import governance_history as gh
import governance_report as gr
import repository_badges as rb


def make_repository(name='public_repo', visibility='public'):
    return {'name': name, 'visibility': visibility, 'scan_branch': 'develop', 'errors': [],
            'url': 'https://untrusted.invalid/private-information',
            'checks': {key: {'status': gr.OK, 'details': ['confidential-check-detail']}
                       for key, _title in gr.COLUMNS}}


def make_report():
    return {'organisation': 'National-Node-Net', 'completed_at': '2026-11-06T12:00:00Z',
            'parameters': {'dormant_days': 180, 'scan_branch': 'develop'},
            'repositories': [make_repository(), make_repository('private-project', 'private'),
                             make_repository('internal-project', 'internal')],
            'skipped': ['secret-skipped'], 'excluded': ['secret-excluded']}


def tree_bytes(root):
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob('*') if path.is_file()}


class GovernanceHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.badges = self.root / 'badges'
        self.report = make_report()
        for repository in self.report['repositories']:
            directory = self.badges / 'repositories' / repository['name']
            directory.mkdir(parents=True)
            for filename in rb.BADGE_FILENAMES:
                (directory / filename).write_bytes(b'<svg>exact scan bytes\r\n</svg>\n')
        self.archive = self.root / 'archive'
        self.archive.mkdir()
        self.metadata = dict(repository='National-Node-Net/ndt-overwatch', run_id='123',
                             run_attempt='1', source_sha='a' * 40, event='push')

    def prepare(self, output='artifact', report=None, **metadata):
        return gh.prepare(self.report if report is None else report, self.badges, self.root / output,
                          **{**self.metadata, **metadata})

    def append(self, output='artifact'):
        return gh.append(self.root / output, self.archive)

    def test_public_only_overview_exact_bytes_relative_images_and_metadata(self):
        snapshot = self.prepare()
        self.assertEqual(snapshot.relative_to(self.root / 'artifact').as_posix(),
                         'snapshots/2026-11-06/run-123-attempt-1')
        files = tree_bytes(self.root / 'artifact')
        self.assertEqual(len(files), 4)
        markdown = (snapshot / 'README.md').read_text()
        for filename in rb.BADGE_FILENAMES:
            relative = f'badges/public_repo/{filename}'
            self.assertIn(f']({relative})', markdown)
            self.assertEqual((snapshot / relative).read_bytes(),
                             (self.badges / 'repositories/public_repo' / filename).read_bytes())
        for label in gh.LABELS:
            self.assertIn(label, markdown)
        for expected in ('2026-11-06T12:00:00Z (UTC)', 'Scan branch: develop', 'a' * 40,
                         'https://github.com/National-Node-Net/public_repo',
                         'https://github.com/National-Node-Net/ndt-overwatch/actions/runs/123/attempts/1',
                         'Event: push'):
            self.assertIn(expected, markdown)
        all_output = b'\n'.join(files.values()).decode()
        for private in ('private-project', 'internal-project', 'secret-skipped', 'secret-excluded',
                        'confidential-check-detail', 'untrusted.invalid', 'report.json'):
            self.assertNotIn(private, all_output)
        self.assertFalse((self.root / 'artifact/README.md').exists())

    def test_failures_including_private_failures_are_archived(self):
        for repository in self.report['repositories']:
            repository['checks']['files']['status'] = gr.FAIL
        self.prepare()
        self.assertTrue(self.append().is_dir())

    def test_legend_is_included_in_public_and_empty_overviews(self):
        for output, repositories in (('public', self.report['repositories']),
                                     ('empty', [make_repository('private-only', 'private')])):
            with self.subTest(output=output):
                report = copy.deepcopy(self.report)
                report['repositories'] = repositories
                markdown = (self.prepare(output=output, report=report) / 'README.md').read_text()
                for text in ('## OSPO compliance legend', '**Pass (green):**', '**Fail (red):**',
                             '**Unknown (gray):**', '**Attention (amber):**',
                             'including an unavailable credential scan',
                             'precedence is fail, then attention, then unknown, then pass',
                             'Commit age and last checked are separate'):
                    self.assertIn(text, markdown)
                self.assertLess(markdown.index('## OSPO compliance legend'), markdown.index('| Repository |'))

    def test_completed_scan_with_unknown_check_results_is_archived(self):
        self.report['repositories'][0]['checks']['auto_backmerge']['status'] = gr.ERROR
        self.report['repositories'][1]['checks']['dependabot_auto_merge']['status'] = gr.ERROR
        self.prepare()
        self.assertTrue(self.append().is_dir())

    def test_snapshot_freezes_gray_activity_badge(self):
        completed = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
        self.report['repositories'][0]['activity'] = {
            'branch': 'develop', 'last_application_commit_at': '2026-11-05T12:00:00Z',
        }
        green = rb.generate_badges(self.report, completed)['public_repo']
        for filename, svg in green.items():
            (self.badges / 'repositories/public_repo' / filename).write_text(svg, encoding='utf-8')
        self.prepare()
        first = self.append()
        frozen = (first / 'badges/public_repo/develop-activity.svg').read_bytes()
        self.assertIn(rb.GRAY.encode(), frozen)

        self.report['repositories'][0]['activity']['last_application_commit_at'] = '2025-01-01T00:00:00Z'
        different_age = rb.generate_badges(self.report, completed)['public_repo']
        for filename, svg in different_age.items():
            (self.badges / 'repositories/public_repo' / filename).write_text(svg, encoding='utf-8')
        self.prepare('paused', run_id='124')
        second = self.append('paused')
        self.assertEqual((first / 'badges/public_repo/develop-activity.svg').read_bytes(), frozen)
        self.assertIn(rb.GRAY, (second / 'badges/public_repo/develop-activity.svg').read_text())
        self.assertIn('674 days', (second / 'badges/public_repo/develop-activity.svg').read_text())

    def test_all_events_are_supported(self):
        for event in gh.EVENTS:
            with self.subTest(event=event):
                self.prepare(output=event, event=event)

    def test_zero_public_repositories_is_valid_and_does_not_read_private_badges(self):
        self.report['repositories'] = [make_repository('no-badges', 'private')]
        snapshot = self.prepare()
        self.assertEqual(set(tree_bytes(snapshot)), {'README.md'})
        self.assertIn('No public repositories', (snapshot / 'README.md').read_text())
        self.append()

    def test_missing_unknown_or_malformed_visibility_fails_closed(self):
        for value in (None, '', 'unknown', 'PUBLIC', [], {}):
            with self.subTest(value=value):
                report = copy.deepcopy(self.report)
                report['repositories'][1]['visibility'] = value
                with self.assertRaises(gh.InvalidHistory):
                    self.prepare(report=report)
                self.assertFalse((self.root / 'artifact').exists())
        del self.report['repositories'][1]['visibility']
        with self.assertRaises(gh.InvalidHistory):
            self.prepare()

    def test_incomplete_and_structurally_invalid_reports_are_rejected(self):
        reports = [None, [], {}, {**self.report, 'repositories': {}},
                   {**self.report, 'organisation': '../private'},
                   {**self.report, 'parameters': {'dormant_days': True, 'scan_branch': 'develop'}}]
        for completed in (None, '', 'invalid', '2026-11-06', '2026-11-06T12:00:00',
                          '2999-01-01T00:00:00Z'):
            reports.append({**self.report, 'completed_at': completed})
        for field, value in (('errors', ['private processing error']), ('checks', {}),
                             ('checks', {'files': {'status': 'invalid'}}),
                             ('scan_branch', None), ('name', '../escape')):
            report = copy.deepcopy(self.report)
            report['repositories'][1][field] = value
            reports.append(report)
        report = copy.deepcopy(self.report)
        report['repositories'].append(make_repository('PUBLIC_REPO'))
        reports.append(report)
        for report in reports:
            with self.subTest(report=report), self.assertRaises(gh.InvalidHistory):
                self.prepare(report=report if report is not None else [])
            self.assertFalse((self.root / 'artifact').exists())

    def test_invalid_run_metadata_is_rejected_before_output(self):
        cases = {'repository': ('../repo', 'org/../repo', 'org/.', 'org/a/b', 'org/a?x'),
                 'run_id': ('../1', '0', '-1', '01', '1.2', '1\n', 1, True),
                 'run_attempt': ('0', '01', 'x', None),
                 'source_sha': ('a' * 39, 'g' * 40, '../escape', None),
                 'event': ('pull_request', 'workflow_run', 'push\n', None)}
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value), self.assertRaises(gh.InvalidHistory):
                    self.prepare(**{field: value})
                self.assertFalse((self.root / 'artifact').exists())

    def test_completion_date_is_utc_and_markdown_names_are_escaped(self):
        self.report['completed_at'] = '2026-11-07T01:00:00+02:00'
        snapshot = self.prepare()
        self.assertEqual(snapshot.parent.name, '2026-11-06')
        self.assertIn('[public&#95;repo]', (snapshot / 'README.md').read_text())

    def test_all_public_badges_preflighted_before_writes(self):
        second = make_repository('zzz-missing')
        self.report['repositories'].append(second)
        with self.assertRaises(OSError):
            self.prepare()
        self.assertFalse((self.root / 'artifact').exists())

    def test_prepare_does_not_overwrite_existing_output(self):
        self.prepare()
        before = tree_bytes(self.root / 'artifact')
        with self.assertRaises(gh.InvalidHistory):
            self.prepare()
        self.assertEqual(tree_bytes(self.root / 'artifact'), before)

    def test_prepare_rejects_badge_and_output_symlinks_and_traversal(self):
        badge = self.badges / 'repositories/public_repo/ospo-compliance.svg'
        original = self.root / 'original.svg'
        badge.rename(original)
        badge.symlink_to(original)
        with self.assertRaises(gh.InvalidHistory):
            self.prepare()
        badge.unlink()
        original.rename(badge)
        (self.root / 'link').symlink_to(self.root / 'absent')
        for output in ('../escape', 'link/output'):
            with self.subTest(output=output), self.assertRaises(gh.InvalidHistory):
                self.prepare(output=output)
        directory = self.badges / 'repositories/public_repo'
        directory.rename(directory.with_name('real'))
        directory.symlink_to(directory.with_name('real'), target_is_directory=True)
        with self.assertRaises(gh.InvalidHistory):
            self.prepare()

    def test_append_multiple_runs_attempts_order_and_prior_bytes_unchanged(self):
        git = self.archive / '.git'
        git.mkdir()
        (git / 'config').write_bytes(b'untouched git data')
        (self.archive / 'keep.txt').write_bytes(b'unrelated')
        expected = []
        for output, day, run, attempt in (
                ('first', '2026-11-05', '999', '1'),
                ('second', '2026-11-06', '9', '1'),
                ('third', '2026-11-06', '10', '1'),
                ('fourth', '2026-11-06', '10', '2')):
            prior = tree_bytes(self.archive / 'snapshots')
            self.report['completed_at'] = day + 'T12:00:00Z'
            self.prepare(output, run_id=run, run_attempt=attempt)
            self.append(output)
            for relative, content in prior.items():
                self.assertEqual((self.archive / 'snapshots' / relative).read_bytes(), content)
            expected.insert(0, f'snapshots/{day}/run-{run}-attempt-{attempt}/README.md')
        index = (self.archive / 'README.md').read_text()
        positions = [index.index(link) for link in expected]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual((git / 'config').read_bytes(), b'untouched git data')
        self.assertEqual((self.archive / 'keep.txt').read_bytes(), b'unrelated')

    def test_append_preserves_legacy_snapshot_without_legend(self):
        legacy = self.prepare('legacy')
        readme = legacy / 'README.md'
        markdown = readme.read_text()
        start = markdown.index('## OSPO compliance legend')
        end = markdown.index('| Repository |', start)
        readme.write_text(markdown[:start] + markdown[end:])
        archived = self.append('legacy')
        prior = tree_bytes(archived)

        self.prepare('new', run_id='124')
        new = self.append('new')
        self.assertIn('## OSPO compliance legend', (new / 'README.md').read_text())
        self.assertEqual(tree_bytes(archived), prior)
        self.assertNotIn('## OSPO compliance legend', (archived / 'README.md').read_text())

    def test_identical_duplicate_is_idempotent_including_snapshot_mtime(self):
        self.prepare()
        destination = self.append()
        before = tree_bytes(self.archive)
        times = {path: path.stat().st_mtime_ns for path in destination.rglob('*')}
        self.append()
        self.assertEqual(tree_bytes(self.archive), before)
        self.assertEqual({path: path.stat().st_mtime_ns for path in destination.rglob('*')}, times)

    def test_conflicting_duplicate_or_same_identity_on_other_date_is_forbidden(self):
        snapshot = self.prepare()
        self.append()
        before = tree_bytes(self.archive)
        readme = snapshot / 'README.md'
        readme.write_bytes(readme.read_bytes() + b'conflict\n')
        with self.assertRaises(gh.InvalidHistory):
            self.append()
        self.assertEqual(tree_bytes(self.archive), before)
        self.report['completed_at'] = '2026-11-07T00:00:00Z'
        self.prepare('other-date')
        with self.assertRaises(gh.InvalidHistory):
            self.append('other-date')
        self.assertEqual(tree_bytes(self.archive), before)

    def test_unexpected_artifact_files_and_directories_rejected(self):
        snapshot = self.prepare()
        for relative in ('report.json', 'snapshots/leak.json',
                         str(snapshot.relative_to(self.root / 'artifact') / 'report.json'),
                         str(snapshot.relative_to(self.root / 'artifact') / 'badges/public_repo/extra.svg')):
            path = self.root / 'artifact' / relative
            path.write_bytes(b'private-data')
            with self.subTest(relative=relative), self.assertRaises(gh.InvalidHistory):
                self.append()
            self.assertEqual(tree_bytes(self.archive), {})
            path.unlink()
        extra = snapshot / 'empty'
        extra.mkdir()
        with self.assertRaises(gh.InvalidHistory):
            self.append()

    def test_badge_only_conflict_never_changes_archive(self):
        snapshot = self.prepare()
        self.append()
        before = tree_bytes(self.archive)
        (snapshot / 'badges/public_repo/last-checked.svg').write_bytes(b'<svg>changed</svg>')
        with self.assertRaises(gh.InvalidHistory):
            self.append()
        self.assertEqual(tree_bytes(self.archive), before)

    def test_two_valid_snapshots_in_one_artifact_are_rejected(self):
        first = self.prepare()
        second = self.prepare('second', run_id='456')
        second.rename(first.with_name(second.name))
        with self.assertRaises(gh.InvalidHistory):
            self.append()
        self.assertEqual(tree_bytes(self.archive), {})

    def test_malformed_existing_history_rejected_before_append(self):
        self.prepare()
        self.append()
        self.prepare('second', run_id='456')
        unexpected = self.archive / 'snapshots/2026-11-06/run-123-attempt-1/report.json'
        unexpected.write_bytes(b'not a supported archive file')
        before = tree_bytes(self.archive)
        with self.assertRaises(gh.InvalidHistory):
            self.append('second')
        self.assertEqual(tree_bytes(self.archive), before)

    def test_missing_badge_and_unexpected_badge_directory_rejected(self):
        snapshot = self.prepare()
        badge = snapshot / 'badges/public_repo/last-checked.svg'
        original = badge.read_bytes()
        badge.unlink()
        with self.assertRaises(gh.InvalidHistory):
            self.append()
        badge.write_bytes(original)
        (snapshot / 'badges/empty-repository').mkdir()
        with self.assertRaises(gh.InvalidHistory):
            self.append()
        self.assertEqual(tree_bytes(self.archive), {})

    def test_existing_snapshot_symlink_and_overlapping_archive_are_rejected(self):
        self.prepare()
        destination = self.append()
        badge = destination / 'badges/public_repo/last-checked.svg'
        badge.unlink()
        badge.symlink_to(self.root / 'absent')
        with self.assertRaises(gh.InvalidHistory):
            self.append()
        with self.assertRaises(gh.InvalidHistory):
            gh.append(self.root / 'artifact', self.root / 'artifact')

    def test_multiple_snapshots_invalid_dates_and_run_names_rejected(self):
        self.prepare()
        run = self.root / 'artifact/snapshots/2026-11-06/run-123-attempt-1'
        for invalid in ('run-0-attempt-1', 'run-123-attempt-01', 'unexpected'):
            target = run.with_name(invalid)
            run.rename(target)
            with self.subTest(invalid=invalid), self.assertRaises(gh.InvalidHistory):
                self.append()
            target.rename(run)
        day = run.parent
        day.rename(day.with_name('2026-02-30'))
        with self.assertRaises(ValueError):
            self.append()
        day.with_name('2026-02-30').rename(day)
        (day / 'run-456-attempt-1').mkdir()
        with self.assertRaises(gh.InvalidHistory):
            self.append()

    def test_source_file_and_ancestor_symlinks_are_rejected(self):
        snapshot = self.prepare()
        readme = snapshot / 'README.md'
        readme.unlink()
        readme.symlink_to(self.root / 'missing')
        with self.assertRaises(gh.InvalidHistory):
            self.append()
        readme.unlink()
        readme.write_bytes(b'overview')
        (self.root / 'artifact-link').symlink_to(self.root / 'artifact', target_is_directory=True)
        with self.assertRaises(gh.InvalidHistory):
            self.append('artifact-link')

    def test_destination_symlinks_rejected_without_writing(self):
        self.prepare()
        outside = self.root / 'outside'
        outside.mkdir()
        for relative in ('README.md', 'snapshots', 'snapshots/2026-11-06'):
            target = self.archive / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(outside, target_is_directory=True)
            with self.subTest(relative=relative), self.assertRaises(gh.InvalidHistory):
                self.append()
            self.assertEqual(tree_bytes(outside), {})
            target.unlink()

    def test_cli_prepare_append_and_safe_concise_error(self):
        report = self.root / 'report.json'
        report.write_text(json.dumps(self.report))
        arguments = ['prepare', '--report', str(report), '--badges-dir', str(self.badges),
                     '--output-dir', str(self.root / 'artifact')]
        for key, value in self.metadata.items():
            arguments += ['--' + key.replace('_', '-'), value]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gh.main(arguments), 0)
            self.assertEqual(gh.main(['append', '--snapshot-dir', str(self.root / 'artifact'),
                                      '--archive-dir', str(self.archive)]), 0)
        report.write_text('{private-report-error')
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            self.assertEqual(gh.main(arguments), 1)
        self.assertEqual(len(error.getvalue().splitlines()), 1)
        self.assertNotIn('private-report-error', error.getvalue())
        self.assertNotIn(str(report), error.getvalue())


if __name__ == '__main__':
    unittest.main()