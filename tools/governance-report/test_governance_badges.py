# SPDX-License-Identifier: Apache-2.0
# © Crown Copyright 2026. This work has been developed by the National Digital Twin Programme and is legally attributed to the UK's Department for Business, Innovation, Science and Trade (BIST) as the governing entity.

import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import governance_badges as badges
from governance_report import COLUMNS, ERROR, FAIL, NA, OK, WARN

NOW = datetime(2026, 10, 27, 12, 0, tzinfo=timezone.utc)
OWNER = 'National-Node-Net'
NAME = 'ndt-overwatch'
NAMESPACE = '{http://www.w3.org/2000/svg}'
DEFAULT_REPORT = object()


def report_fixture():
    checks = {key: {'status': OK} for key, _title in COLUMNS}
    return {
        'organisation': OWNER,
        'generated_at': '2026-10-27 11:59',
        'completed_at': NOW.isoformat(),
        'mode': 'report only',
        'parameters': {'dormant_days': 180},
        'skipped': [],
        'excluded': [],
        'legend': {},
        'repositories': [{
            'name': NAME,
            'checks': checks,
            'errors': [],
            'activity': {'branch': 'develop', 'last_commit_at': (NOW - timedelta(days=22)).isoformat()},
        }],
    }


def value_for(svg):
    root = ET.fromstring(svg)
    return root.findall(f'.//{NAMESPACE}text')[1].text


def color_for(svg):
    root = ET.fromstring(svg)
    paths = root.findall(f'.//{NAMESPACE}path')
    return paths[1].attrib['fill']


class GovernanceBadgeTests(unittest.TestCase):
    def setUp(self):
        self.report = report_fixture()

    def badges(self, report=DEFAULT_REPORT, repository=f'{OWNER}/{NAME}', now=NOW):
        return badges.generate_badges(self.report if report is DEFAULT_REPORT else report, repository, now)

    def test_all_pass_and_recent_develop_are_green(self):
        generated = self.badges()
        self.assertEqual(value_for(generated['ospo-compliance.svg']), 'all checks passed')
        self.assertEqual(color_for(generated['ospo-compliance.svg']), badges.GREEN)
        self.assertEqual(value_for(generated['develop-activity.svg']), '22 days')
        self.assertEqual(color_for(generated['develop-activity.svg']), badges.GREEN)
        self.assertEqual(value_for(generated['last-checked.svg']), '2026-10-27 12:00 UTC')
        self.assertEqual(color_for(generated['last-checked.svg']), badges.GREEN)

    def test_each_nonpassing_or_unknown_status_is_amber(self):
        for status in (WARN, FAIL, ERROR, NA, 'MYSTERY'):
            with self.subTest(status=status):
                report = deepcopy(self.report)
                report['repositories'][0]['checks'][COLUMNS[0][0]]['status'] = status
                generated = self.badges(report)
                self.assertEqual(color_for(generated['ospo-compliance.svg']), badges.AMBER)
                if status in (ERROR, NA, 'MYSTERY'):
                    self.assertEqual(color_for(generated['last-checked.svg']), badges.AMBER)
                else:
                    self.assertEqual(color_for(generated['last-checked.svg']), badges.GREEN)

    def test_missing_check_is_amber_and_incomplete(self):
        report = deepcopy(self.report)
        del report['repositories'][0]['checks'][COLUMNS[0][0]]
        generated = self.badges(report)
        self.assertEqual(color_for(generated['ospo-compliance.svg']), badges.AMBER)
        self.assertEqual(color_for(generated['last-checked.svg']), badges.AMBER)

    def test_explicit_not_applicable_is_allowed_but_unknown_na_is_not(self):
        key = COLUMNS[0][0]
        report = deepcopy(self.report)
        report['repositories'][0]['checks'][key] = {'status': NA, 'applicable': False}
        self.assertEqual(color_for(self.badges(report)['ospo-compliance.svg']), badges.GREEN)

        for check in ({'status': NA}, {'status': NA, 'applicable': True}):
            with self.subTest(check=check):
                report = deepcopy(self.report)
                report['repositories'][0]['checks'][key] = check
                generated = self.badges(report)
                self.assertEqual(color_for(generated['ospo-compliance.svg']), badges.AMBER)
                self.assertEqual(color_for(generated['last-checked.svg']), badges.AMBER)

    def test_not_applicable_cannot_hide_a_failure(self):
        report = deepcopy(self.report)
        report['repositories'][0]['checks'][COLUMNS[0][0]] = {'status': FAIL, 'applicable': False}
        generated = self.badges(report)
        self.assertEqual(color_for(generated['ospo-compliance.svg']), badges.AMBER)
        self.assertEqual(color_for(generated['last-checked.svg']), badges.AMBER)

    def test_errors_make_compliance_and_last_checked_amber(self):
        report = deepcopy(self.report)
        report['repositories'][0]['errors'] = ['private scanner failure text']
        generated = self.badges(report)
        self.assertEqual(color_for(generated['ospo-compliance.svg']), badges.AMBER)
        self.assertEqual(color_for(generated['last-checked.svg']), badges.AMBER)

    def test_missing_report_and_missing_completed_at_never_fabricate_dates(self):
        for report in (None, {}):
            generated = self.badges(report)
            self.assertEqual(value_for(generated['ospo-compliance.svg']), 'not checked')
            self.assertEqual(value_for(generated['develop-activity.svg']), 'unknown')
            self.assertEqual(value_for(generated['last-checked.svg']), 'not checked')
            self.assertTrue(all(color_for(svg) == badges.AMBER for svg in generated.values()))

        report = deepcopy(self.report)
        del report['completed_at']
        generated = self.badges(report)
        self.assertEqual(value_for(generated['last-checked.svg']), 'not checked')

    def test_future_malformed_and_naive_scan_timestamps_never_green(self):
        for value in (
            (NOW + timedelta(seconds=1)).isoformat(),
            'not-an-iso-timestamp',
            '2026-10-27T12:00:00',
        ):
            with self.subTest(completed_at=value):
                report = deepcopy(self.report)
                report['completed_at'] = value
                generated = self.badges(report)
                self.assertEqual(value_for(generated['last-checked.svg']), 'not checked')
                self.assertTrue(all(color_for(svg) == badges.AMBER for svg in generated.values()))

    def test_missing_no_develop_or_future_develop_commit_is_unknown(self):
        for activity in (
            None,
            {'branch': 'develop', 'last_commit_at': None},
            {'branch': 'develop', 'last_commit_at': 'bad-date'},
            {'branch': 'develop', 'last_commit_at': (NOW + timedelta(seconds=1)).isoformat()},
        ):
            with self.subTest(activity=activity):
                report = deepcopy(self.report)
                if activity is None:
                    del report['repositories'][0]['activity']
                else:
                    report['repositories'][0]['activity'] = activity
                generated = self.badges(report)
                self.assertEqual(value_for(generated['develop-activity.svg']), 'unknown')
                self.assertEqual(color_for(generated['develop-activity.svg']), badges.AMBER)
                self.assertEqual(color_for(generated['ospo-compliance.svg']), badges.AMBER)

    def test_default_branch_and_work_branch_activity_are_not_develop_activity(self):
        for branch in ('main', 'feature/active-work', 'release/1.0'):
            with self.subTest(branch=branch):
                report = deepcopy(self.report)
                report['repositories'][0]['activity']['branch'] = branch
                generated = self.badges(report)
                self.assertEqual(value_for(generated['develop-activity.svg']), 'unknown')
                self.assertEqual(color_for(generated['ospo-compliance.svg']), badges.AMBER)

    def test_threshold_is_inclusive_and_next_whole_day_is_exclusive(self):
        for age, expected in ((180, badges.GREEN), (181, badges.AMBER), (0, badges.GREEN)):
            with self.subTest(age=age):
                report = deepcopy(self.report)
                report['repositories'][0]['activity']['last_commit_at'] = (NOW - timedelta(days=age)).isoformat()
                generated = self.badges(report)
                self.assertEqual(color_for(generated['develop-activity.svg']), expected)
                self.assertEqual(color_for(generated['ospo-compliance.svg']), expected)

    def test_old_develop_is_not_rescued_by_other_recent_work(self):
        report = deepcopy(self.report)
        report['repositories'][0]['activity']['last_commit_at'] = (NOW - timedelta(days=181)).isoformat()
        report['repositories'][0]['checks']['activity']['status'] = OK
        report['repositories'][0]['other_branch_commit_at'] = NOW.isoformat()
        generated = self.badges(report)
        self.assertEqual(value_for(generated['develop-activity.svg']), '181 days')
        self.assertEqual(color_for(generated['ospo-compliance.svg']), badges.AMBER)

    def test_scan_time_is_used_as_snapshot_for_activity_age(self):
        report = deepcopy(self.report)
        report['completed_at'] = (NOW - timedelta(days=10)).isoformat()
        report['repositories'][0]['activity']['last_commit_at'] = (NOW - timedelta(days=190)).isoformat()
        generated = self.badges(report)
        self.assertEqual(value_for(generated['develop-activity.svg']), '180 days')
        self.assertEqual(color_for(generated['develop-activity.svg']), badges.GREEN)

    def test_offset_scan_timestamp_is_displayed_in_utc(self):
        report = deepcopy(self.report)
        report['completed_at'] = NOW.astimezone(timezone(timedelta(hours=2))).isoformat()
        generated = self.badges(report)
        self.assertEqual(value_for(generated['last-checked.svg']), '2026-10-27 12:00 UTC')

    def test_identity_exclusions_missing_and_duplicate_targets_are_conservative(self):
        variants = []
        wrong_org = deepcopy(self.report)
        wrong_org['organisation'] = 'Another-Org'
        variants.append(wrong_org)
        excluded = deepcopy(self.report)
        excluded['excluded'] = [NAME.upper()]
        variants.append(excluded)
        missing = deepcopy(self.report)
        missing['repositories'] = []
        variants.append(missing)
        duplicate = deepcopy(self.report)
        duplicate['repositories'].append(deepcopy(duplicate['repositories'][0]))
        variants.append(duplicate)
        wrong_full_name = deepcopy(self.report)
        wrong_full_name['repositories'][0]['full_name'] = f'Other-Org/{NAME}'
        variants.append(wrong_full_name)

        for report in variants:
            with self.subTest(report=report):
                generated = self.badges(report)
                self.assertEqual(color_for(generated['ospo-compliance.svg']), badges.AMBER)
                self.assertEqual(value_for(generated['last-checked.svg']), 'not checked')

    def test_repository_name_matching_is_case_insensitive(self):
        generated = self.badges(repository=f'{OWNER.lower()}/{NAME.upper()}')
        self.assertEqual(color_for(generated['ospo-compliance.svg']), badges.GREEN)

    def test_svg_text_is_xml_escaped(self):
        svg = badges._badge_svg('A<&"', 'B<&"', badges.AMBER)
        root = ET.fromstring(svg)
        self.assertEqual(root.attrib['aria-label'], 'A<&": B<&"')
        self.assertEqual(root.find(f'{NAMESPACE}title').text, 'A<&": B<&"')
        self.assertEqual([node.text for node in root.findall(f'.//{NAMESPACE}text')], ['A<&"', 'B<&"'])

    def test_no_report_content_or_credentials_leak_into_badges(self):
        report = deepcopy(self.report)
        report['repositories'][0]['checks'][COLUMNS[0][0]]['summary'] = 'private text TOKEN=secret-value'
        report['repositories'][0]['errors'] = ['another-private-detail password=hunter2']
        serialized = '\n'.join(self.badges(report).values())
        for private_text in ('private text', 'secret-value', 'another-private-detail', 'hunter2', OWNER, NAME):
            self.assertNotIn(private_text, serialized)

    def test_all_fixed_svg_names_and_xml(self):
        generated = self.badges()
        self.assertEqual(set(generated), set(badges.BADGE_FILENAMES))
        for svg in generated.values():
            self.assertEqual(ET.fromstring(svg).tag, f'{NAMESPACE}svg')
            self.assertIn('height="28"', svg)
            self.assertNotIn('<script', svg)
            self.assertNotIn('http://', svg.replace('http://www.w3.org/2000/svg', ''))

    def test_readme_links_resolve_to_valid_saved_badges(self):
        root = Path(badges.__file__).resolve().parents[2]
        readme = (root / 'README.md').read_text(encoding='utf-8')
        for filename in badges.BADGE_FILENAMES:
            relative = f'.github/badges/{filename}'
            self.assertIn(f']({relative})', readme)
            svg = ET.parse(root / relative).getroot()
            self.assertEqual(svg.tag, f'{NAMESPACE}svg')
            self.assertEqual(svg.attrib['role'], 'img')
            self.assertIsNotNone(svg.find(f'{NAMESPACE}title'))

    def test_cli_writes_three_parseable_badges(self):
        script = Path(badges.__file__).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / 'report.json'
            output = root / 'badges'
            cli_report = deepcopy(self.report)
            cli_now = datetime.now(timezone.utc)
            cli_report['completed_at'] = cli_now.isoformat()
            cli_report['repositories'][0]['activity']['last_commit_at'] = (
                cli_now - timedelta(days=22)
            ).isoformat()
            report_path.write_text(json.dumps(cli_report), encoding='utf-8')
            result = subprocess.run(
                [sys.executable, str(script), '--report', str(report_path), '--repository', f'{OWNER}/{NAME}',
                 '--output-dir', str(output)], capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual({path.name for path in output.iterdir()}, set(badges.BADGE_FILENAMES))
            for path in output.iterdir():
                ET.parse(path)

    def test_malformed_cli_report_recovers_with_amber_and_nonzero(self):
        script = Path(badges.__file__).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = root / 'report.json'
            output = root / 'badges'
            report_path.write_text('{ malformed', encoding='utf-8')
            result = subprocess.run(
                [sys.executable, str(script), '--report', str(report_path), '--repository', f'{OWNER}/{NAME}',
                 '--output-dir', str(output)], capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual({path.name for path in output.iterdir()}, set(badges.BADGE_FILENAMES))
            for path in output.iterdir():
                self.assertEqual(color_for(path.read_text(encoding='utf-8')), badges.AMBER)
                ET.parse(path)
            self.assertNotIn('malformed', result.stderr.lower())

    def test_cli_missing_report_recovers_without_nonzero_or_fake_date(self):
        script = Path(badges.__file__).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / 'badges'
            result = subprocess.run(
                [sys.executable, str(script), '--report', str(root / 'missing.json'), '--repository', f'{OWNER}/{NAME}',
                 '--output-dir', str(output)], capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(value_for((output / 'last-checked.svg').read_text(encoding='utf-8')), 'not checked')

    def test_cli_without_report_outputs_placeholders(self):
        script = Path(badges.__file__).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'badges'
            result = subprocess.run(
                [sys.executable, str(script), '--repository', f'{OWNER}/{NAME}', '--output-dir', str(output)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(value_for((output / 'ospo-compliance.svg').read_text(encoding='utf-8')), 'not checked')
            self.assertEqual(value_for((output / 'develop-activity.svg').read_text(encoding='utf-8')), 'unknown')
            self.assertEqual(value_for((output / 'last-checked.svg').read_text(encoding='utf-8')), 'not checked')

    def test_cli_rejects_bad_threshold_and_repository_argument(self):
        script = Path(badges.__file__).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'badges'
            for report in (
                {**self.report, 'parameters': {'dormant_days': 0}},
                {**self.report, 'parameters': {'dormant_days': True}},
            ):
                with self.subTest(threshold=report['parameters']['dormant_days']):
                    report_path = Path(tmp) / 'invalid.json'
                    report_path.write_text(json.dumps(report), encoding='utf-8')
                    result = subprocess.run(
                        [sys.executable, str(script), '--report', str(report_path), '--repository', f'{OWNER}/{NAME}',
                         '--output-dir', str(output)], capture_output=True, text=True, check=False,
                    )
                    self.assertNotEqual(result.returncode, 0)
            result = subprocess.run(
                [sys.executable, str(script), '--repository', 'not-a-repository', '--output-dir', str(output)],
                capture_output=True, text=True, check=False,
            )
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()