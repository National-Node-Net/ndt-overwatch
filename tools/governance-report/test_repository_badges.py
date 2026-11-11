# SPDX-License-Identifier: Apache-2.0
# © Crown Copyright 2026. This work has been developed by the National Digital Twin Programme and is legally attributed to the UK's Department for Business, Innovation, Science and Trade (BIST) as the governing entity.

import contextlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import governance_report as gr
import repository_badges as rb

UTC = timezone.utc
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
SVG_NS = '{http://www.w3.org/2000/svg}'


def timestamp(value):
    return value.isoformat().replace('+00:00', 'Z')


def make_repository(name='public-repo', visibility='public'):
    return {
        'name': name,
        'visibility': visibility,
        'scan_branch': 'develop',
        'errors': [],
        'checks': {key: {'status': gr.OK} for key, _title in gr.COLUMNS},
        'activity': {
            'branch': 'develop',
            'last_application_commit_at': timestamp(NOW - timedelta(days=12)),
        },
    }


def make_report(repositories=None, completed_at=NOW):
    return {
        'organisation': 'National-Node-Net',
        'completed_at': timestamp(completed_at) if isinstance(completed_at, datetime) else completed_at,
        'parameters': {'dormant_days': 180},
        'repositories': repositories if repositories is not None else [make_repository()],
        'skipped': ['archived-repo'],
        'excluded': ['excluded-repo'],
    }


def badge_root(svg):
    return ET.fromstring(svg)


def badge_value(svg):
    return badge_root(svg).findall(f'.//{SVG_NS}text')[1].text


def badge_color(svg):
    return badge_root(svg).findall(f'.//{SVG_NS}path')[1].attrib['fill']


class ComplianceBadgeTests(unittest.TestCase):
    def test_all_applicable_checks_pass_and_nonapplicable_na_is_ignored(self):
        repository = make_repository()
        repository['checks']['sbom'] = {'status': gr.NA, 'applicable': False}
        badges = rb.generate_badges(make_report([repository]), NOW)[repository['name']]
        self.assertEqual(badge_value(badges['ospo-compliance.svg']), 'pass')
        self.assertEqual(badge_color(badges['ospo-compliance.svg']), rb.GREEN)

    def test_warn_or_fail_requires_attention(self):
        for status in (gr.WARN, gr.FAIL):
            with self.subTest(status=status):
                repository = make_repository()
                repository['checks']['files'] = {'status': status}
                badge = rb.generate_badges(make_report([repository]), NOW)[repository['name']]['ospo-compliance.svg']
                expected, color = ('attention', rb.AMBER) if status == gr.WARN else ('fail', rb.RED)
                self.assertEqual(badge_value(badge), expected)
                self.assertEqual(badge_color(badge), color)

    def test_error_missing_invalid_and_applicability_unknowns_are_gray(self):
        cases = {
            'error': {'status': gr.ERROR},
            'missing status': {},
            'invalid status': {'status': 'PASS'},
            'applicable N/A': {'status': gr.NA},
            'nonapplicable failure': {'status': gr.FAIL, 'applicable': False},
            'invalid applicable flag': {'status': gr.OK, 'applicable': None},
        }
        for label, check in cases.items():
            with self.subTest(label=label):
                repository = make_repository()
                repository['checks']['files'] = check
                badge = rb.generate_badges(make_report([repository]), NOW)[repository['name']]['ospo-compliance.svg']
                self.assertEqual(badge_value(badge), 'unknown')
                self.assertEqual(badge_color(badge), rb.GRAY)

    def test_missing_check_and_repository_error_are_unknown(self):
        repository = make_repository()
        del repository['checks']['files']
        badge = rb.generate_badges(make_report([repository]), NOW)[repository['name']]['ospo-compliance.svg']
        self.assertEqual(badge_value(badge), 'unknown')
        repository = make_repository()
        repository['errors'] = ['private processing detail']
        badge = rb.generate_badges(make_report([repository]), NOW)[repository['name']]['ospo-compliance.svg']
        self.assertEqual(badge_value(badge), 'unknown')
        self.assertNotIn('private processing detail', badge)

    def test_activity_status_does_not_affect_compliance_badge(self):
        for status in (gr.WARN, gr.FAIL, gr.ERROR, gr.NA):
            with self.subTest(activity_status=status):
                repository = make_repository()
                repository['checks']['activity'] = {'status': status}
                badge = rb.generate_badges(make_report([repository]), NOW)[repository['name']]['ospo-compliance.svg']
                self.assertEqual(badge_value(badge), 'pass')
                self.assertEqual(badge_color(badge), rb.GREEN)


class ProfileStatusTests(unittest.TestCase):
    def test_profile_status_maps_expected_not_applicable_checks(self):
        cases = (
            ('develop', {'status': gr.NA}, 'pass', rb.GREEN),
            ('sbom', {'status': gr.NA, 'applicable': False}, 'pass', rb.GREEN),
            ('auto_backmerge', {'status': gr.NA}, 'unknown', rb.GRAY),
            ('dependabot_auto_merge', {'status': gr.NA}, 'unknown', rb.GRAY),
            ('secret_scan', {'status': gr.NA}, 'fail', rb.RED),
            ('secret_scan', {'status': gr.ERROR}, 'fail', rb.RED),
            ('dependabot_config', {'status': gr.NA}, 'unknown', rb.GRAY),
            ('delete_branch', {'status': gr.NA}, 'unknown', rb.GRAY),
            ('files', {'status': gr.NA}, 'unknown', rb.GRAY),
            ('sbom', {'status': gr.NA, 'applicable': True}, 'unknown', rb.GRAY),
        )
        for key, check, expected, color in cases:
            with self.subTest(check=key, status=check):
                repository = make_repository()
                repository['checks'][key] = check
                self.assertEqual(rb._profile_status(repository), (expected, color))

    def test_known_failure_is_not_hidden_by_unavailable_check(self):
        repository = make_repository()
        repository['checks']['files'] = {'status': gr.FAIL}
        repository['checks']['auto_backmerge'] = {'status': gr.NA}
        self.assertEqual(rb._profile_status(repository), ('fail', rb.RED))

    def test_unknown_remains_unknown_when_no_failure_exists(self):
        repository = make_repository()
        repository['checks']['files'] = {'status': gr.ERROR}
        self.assertEqual(rb._profile_status(repository), ('unknown', rb.GRAY))


class ActivityBadgeTests(unittest.TestCase):
    def test_activity_badge_shows_whole_days_in_gray_regardless_of_age(self):
        repository = make_repository()
        repository['activity']['last_application_commit_at'] = timestamp(NOW - timedelta(days=180, hours=23))
        badge = rb.generate_badges(make_report([repository]), NOW)[repository['name']]['develop-activity.svg']
        self.assertEqual(badge_value(badge), '180 days')
        self.assertEqual(badge_color(badge), rb.GRAY)
        self.assertIn('Days since last commit to Develop', badge_root(badge).attrib['aria-label'])
        repository['activity']['last_application_commit_at'] = timestamp(NOW - timedelta(days=181))
        badge = rb.generate_badges(make_report([repository]), NOW)[repository['name']]['develop-activity.svg']
        self.assertEqual(badge_value(badge), '181 days')
        self.assertEqual(badge_color(badge), rb.GRAY)

    def test_missing_bad_future_or_non_develop_activity_is_unknown(self):
        for field, value, branch in (
            ('last_application_commit_at', None, 'develop'),
            ('last_application_commit_at', 'not-a-date', 'develop'),
            ('last_application_commit_at', timestamp(NOW + timedelta(seconds=1)), 'develop'),
            ('last_application_commit_at', timestamp(NOW), 'main'),
        ):
            with self.subTest(value=value, branch=branch):
                repository = make_repository()
                repository['activity'] = {'branch': branch, field: value}
                badge = rb.generate_badges(make_report([repository]), NOW)[repository['name']]['develop-activity.svg']
                self.assertEqual(badge_value(badge), 'unknown')
                self.assertEqual(badge_color(badge), rb.GRAY)

    def test_non_develop_scan_does_not_publish_compliance_or_freshness_as_verified(self):
        repository = make_repository()
        repository['scan_branch'] = 'main'
        badges = rb.generate_badges(make_report([repository]), NOW)[repository['name']]
        self.assertEqual(badge_value(badges['ospo-compliance.svg']), 'unknown')
        self.assertEqual(badge_color(badges['ospo-compliance.svg']), rb.GRAY)
        self.assertEqual(badge_value(badges['develop-activity.svg']), 'not checked')
        self.assertEqual(badge_value(badges['last-checked.svg']), 'not checked')
        self.assertEqual(badge_color(badges['last-checked.svg']), rb.GRAY)


class FreshnessBadgeTests(unittest.TestCase):
    def test_weekly_slot_and_grace_boundaries(self):
        last_monday = datetime(2026, 10, 26, 3, 0, tzinfo=UTC)
        this_monday = datetime(2026, 11, 2, 3, 0, tzinfo=UTC)
        before_grace_end = datetime(2026, 11, 2, 8, 59, tzinfo=UTC)
        at_grace_end = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)

        badge = rb.generate_badges(make_report(completed_at=last_monday), before_grace_end)['public-repo']['last-checked.svg']
        self.assertEqual(badge_color(badge), rb.GREEN)
        badge = rb.generate_badges(make_report(completed_at=last_monday), at_grace_end)['public-repo']['last-checked.svg']
        self.assertEqual(badge_color(badge), rb.AMBER)
        badge = rb.generate_badges(make_report(completed_at=this_monday), this_monday)['public-repo']['last-checked.svg']
        self.assertEqual(badge_color(badge), rb.GREEN)

    def test_green_amber_red_slot_boundaries(self):
        now = datetime(2026, 11, 2, 10, 0, tzinfo=UTC)
        slot = datetime(2026, 11, 2, 3, 0, tzinfo=UTC)
        cases = (
            (slot, rb.GREEN),
            (slot - timedelta(days=7), rb.AMBER),
            (slot - timedelta(days=7, seconds=1), rb.RED),
        )
        for completed_at, expected in cases:
            with self.subTest(completed_at=completed_at):
                badge = rb.generate_badges(make_report(completed_at=completed_at), now)['public-repo']['last-checked.svg']
                self.assertEqual(badge_color(badge), expected)
                self.assertEqual(badge_value(badge), completed_at.strftime('%Y-%m-%d %H:%M UTC'))

    def test_missing_invalid_and_future_completion_are_not_checked(self):
        for completed_at in (None, 'not-a-date', NOW + timedelta(seconds=1)):
            with self.subTest(completed_at=completed_at):
                badge = rb.generate_badges(make_report(completed_at=completed_at), NOW)['public-repo']['last-checked.svg']
                self.assertEqual(badge_value(badge), 'not checked')
                self.assertEqual(badge_color(badge), rb.GRAY)


class OutputTests(unittest.TestCase):
    def test_generates_status_only_badges_for_public_and_private_repositories(self):
        repositories = [make_repository('public-repo', 'public'), make_repository('private-repo', 'private')]
        badges = rb.generate_badges(make_report(repositories), NOW)
        self.assertEqual(set(badges), {'public-repo', 'private-repo'})
        for repository_badges in badges.values():
            self.assertEqual(set(repository_badges), set(rb.BADGE_FILENAMES))
            for svg in repository_badges.values():
                root = badge_root(svg)
                self.assertEqual(root.attrib['height'], '28')
                self.assertEqual(root.attrib['role'], 'img')
                self.assertTrue(root.attrib['aria-label'])
                self.assertIsNotNone(root.find(f'{SVG_NS}title'))
                self.assertNotIn('private-repo', svg)
                self.assertNotIn('public-repo', svg)
                self.assertNotIn('details', svg)
                self.assertNotIn('private processing detail', svg)

    def test_write_replaces_repository_tree_and_writes_only_svg_files(self):
        repositories = [make_repository('public-repo', 'public'), make_repository('private-repo', 'private')]
        with tempfile.TemporaryDirectory() as temporary_directory:
            output = Path(temporary_directory)
            stale = output / 'repositories' / 'stale-repo' / 'old.svg'
            stale.parent.mkdir(parents=True)
            stale.write_text('<svg/>', encoding='utf-8')
            with patch.object(rb.Path, 'cwd', return_value=output):
                result = rb.write_badges(make_report(repositories), output, NOW)
            self.assertEqual(len(result), 2)
            files = sorted(path.relative_to(output).as_posix() for path in output.rglob('*') if path.is_file())
            self.assertEqual(len(files), len(rb.BADGE_FILENAMES) * len(repositories))
            self.assertTrue(all(path.endswith('.svg') for path in files))
            self.assertFalse(any(path.endswith('.json') for path in files))
            self.assertFalse(stale.exists())

    def test_invalid_repository_name_is_rejected_before_output(self):
        report = make_report([make_repository('../escape')])
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch.object(rb.Path, 'cwd', return_value=Path(temporary_directory)), \
                    self.assertRaises(rb.InvalidReport):
                rb.write_badges(report, 'output', NOW)
            self.assertFalse((Path(temporary_directory) / 'repositories').exists())

    def test_write_badges_rejects_output_traversal_and_symlink_escape(self):
        report = make_report([make_repository()])
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            outside = root.parent / f'{root.name}-outside'
            outside.mkdir()
            self.addCleanup(outside.rmdir)
            (root / 'escape').symlink_to(outside, target_is_directory=True)
            with patch.object(rb.Path, 'cwd', return_value=root):
                for output in ('../outside', 'escape/badges', str(outside)):
                    with self.subTest(output=output), self.assertRaises(rb.InvalidReport):
                        rb.write_badges(report, output, NOW)
            self.assertFalse((outside / 'repositories').exists())

    def test_invalid_report_fails_generation(self):
        with self.assertRaises(rb.InvalidReport):
            rb.generate_badges({'repositories': [], 'parameters': {}, 'organisation': 'Org'}, NOW)

    def test_svg_text_and_accessibility_attributes_are_xml_escaped(self):
        svg = rb._badge_svg('A<&', 'value<&', rb.GREEN)
        self.assertIn('A&lt;&amp;', svg)
        self.assertIn('value&lt;&amp;', svg)
        root = badge_root(svg)
        self.assertEqual(root.attrib['aria-label'], 'A<&: value<&')
        self.assertEqual(root.find(f'{SVG_NS}title').text, 'A<&: value<&')

    def test_cli_prints_repository_count_only(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / 'report.json'
            output = Path(temporary_directory) / 'badges'
            report_path.write_text(json.dumps(make_report([make_repository('private-repo', 'private')])), encoding='utf-8')
            stdout = io.StringIO()
            with patch.object(rb.Path, 'cwd', return_value=Path(temporary_directory)), \
                    contextlib.redirect_stdout(stdout):
                self.assertEqual(rb.main(['--report', str(report_path), '--output-dir', 'badges']), 0)
            self.assertEqual(stdout.getvalue(), 'Generated badges for 1 repositories.\n')
            self.assertNotIn('private-repo', stdout.getvalue())
            self.assertTrue((output / 'repositories/private-repo/ospo-compliance.svg').is_file())


if __name__ == '__main__':
    unittest.main()
