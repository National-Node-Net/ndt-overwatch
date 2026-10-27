#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © Crown Copyright 2026. This work has been developed by the National Digital Twin Programme and is legally attributed to the UK's Department for Business, Innovation, Science and Trade (BIST) as the governing entity.
"""Generate self-hosted, accessible SVG badges from an OSPO governance report."""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from governance_report import COLUMNS, ERROR, FAIL, NA, OK, STATUSES, WARN

GREEN = '#1a7f37'
AMBER = '#9a6700'
BADGE_FILENAMES = ('ospo-compliance.svg', 'develop-activity.svg', 'last-checked.svg')
REPORT_KEYS = ('organisation', 'generated_at', 'mode', 'parameters', 'skipped', 'excluded', 'legend', 'repositories')
OWNER_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9-]*\Z')
REPOSITORY_PATTERN = re.compile(r'[A-Za-z0-9_.-]+\Z')


class InvalidReport(ValueError):
    """The report cannot be trusted as a governance report document."""


def parse_repository(value):
    """Validate the required OWNER/NAME CLI argument and return its components."""
    if value.count('/') != 1:
        raise argparse.ArgumentTypeError('must be OWNER/NAME')
    owner, name = value.split('/', 1)
    if not OWNER_PATTERN.fullmatch(owner) or not REPOSITORY_PATTERN.fullmatch(name):
        raise argparse.ArgumentTypeError('must be a valid OWNER/NAME')
    return owner, name


def _timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _valid_now(now):
    return isinstance(now, datetime) and now.tzinfo is not None and now.utcoffset() is not None


def _placeholder_values():
    return ('not checked', 'unknown', 'not checked')


def _badge_svg(label, value, color):
    left = len(label) * 7 + 24
    right = len(value) * 7 + 24
    width = left + right
    title = escape(f'{label}: {value}', quote=True)
    safe_label = escape(label, quote=True)
    safe_value = escape(value, quote=True)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="28" viewBox="0 0 {width} 28" role="img" aria-label="{title}">
  <title>{title}</title>
  <clipPath id="rounded"><rect width="{width}" height="28" rx="5"/></clipPath>
  <g clip-path="url(#rounded)">
    <path fill="#374151" d="M0 0h{left}v28H0z"/>
    <path fill="{color}" d="M{left} 0h{right}v28H{left}z"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Arial,sans-serif" font-size="12">
    <text x="{left / 2}" y="18">{safe_label}</text>
    <text x="{left + right / 2}" y="18">{safe_value}</text>
  </g>
</svg>
'''


def _badges(compliance, activity, last_checked, *, compliance_color=AMBER,
            activity_color=AMBER, last_checked_color=AMBER):
    return {
        BADGE_FILENAMES[0]: _badge_svg('OSPO compliance', compliance, compliance_color),
        BADGE_FILENAMES[1]: _badge_svg('Develop activity', activity, activity_color),
        BADGE_FILENAMES[2]: _badge_svg('Last checked', last_checked, last_checked_color),
    }


def _validate_report_structure(report):
    if not isinstance(report, dict) or any(key not in report for key in REPORT_KEYS):
        raise InvalidReport
    if (not isinstance(report['organisation'], str) or not report['organisation']
            or not isinstance(report['generated_at'], str) or not isinstance(report['mode'], str)
            or not isinstance(report['parameters'], dict)
            or not isinstance(report['skipped'], list) or not isinstance(report['excluded'], list)
            or not isinstance(report['legend'], dict) or not isinstance(report['repositories'], list)):
        raise InvalidReport
    threshold = report['parameters'].get('dormant_days')
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 1 <= threshold <= 3650:
        raise InvalidReport
    for repository in report['repositories']:
        if (not isinstance(repository, dict) or not isinstance(repository.get('name'), str)
                or not isinstance(repository.get('checks'), dict)
                or not isinstance(repository.get('errors'), list)
                or ('full_name' in repository and not isinstance(repository['full_name'], str))):
            raise InvalidReport
    for name in report['excluded'] + report['skipped']:
        if not isinstance(name, str):
            raise InvalidReport


def _report_completed_at(report, now):
    value = report.get('completed_at')
    if value is None:
        return None
    completed = _timestamp(value)
    if completed is None or completed > now:
        return None
    return completed


def _target_repository(report, owner, name):
    if report['organisation'].casefold() != owner.casefold():
        return None
    wanted = name.casefold()
    if any(_excluded_name(entry, owner, wanted) for entry in report['excluded']):
        return None
    matches = [repository for repository in report['repositories']
               if repository['name'].casefold() == wanted]
    if len(matches) != 1:
        return None
    repository = matches[0]
    full_name = repository.get('full_name')
    if full_name is not None and full_name.casefold() != f'{owner}/{name}'.casefold():
        return None
    return repository


def _excluded_name(entry, owner, wanted):
    if '/' in entry:
        excluded_owner, excluded_repo = entry.split('/', 1)
        return excluded_owner.casefold() == owner.casefold() and excluded_repo.casefold() == wanted
    return entry.casefold() == wanted


def _check_state(repository):
    """Return whether the target checks are complete and whether they all pass."""
    checks = repository['checks']
    complete = True
    all_pass = True
    applicable_count = 0
    for key, _title in COLUMNS:
        check = checks.get(key)
        if not isinstance(check, dict):
            complete = all_pass = False
            continue
        status = check.get('status')
        applicable = check.get('applicable', True)
        if (status == NA and applicable is False):
            continue
        if status not in STATUSES or status == NA or applicable is not True:
            complete = all_pass = False
            continue
        applicable_count += 1
        if status == ERROR:
            complete = False
        if status != OK:
            all_pass = False
    if repository['errors']:
        complete = all_pass = False
    return complete, all_pass and applicable_count > 0


def _develop_age(repository, completed_at):
    activity = repository.get('activity')
    if not isinstance(activity, dict) or activity.get('branch') != 'develop':
        return None
    committed = _timestamp(activity.get('last_commit_at'))
    if committed is None or committed > completed_at:
        return None
    return (completed_at - committed).days


def generate_badges(report, repository, now=None):
    """Return the three fixed SVG badges for OWNER/NAME; unknown data stays amber."""
    current_time = now if now is not None else datetime.now(timezone.utc)
    parsed_repository = repository if isinstance(repository, tuple) else None
    if parsed_repository is None:
        try:
            parsed_repository = parse_repository(repository)
        except (argparse.ArgumentTypeError, AttributeError):
            return _badges(*_placeholder_values())
    owner, name = parsed_repository
    if not _valid_now(current_time):
        return _badges(*_placeholder_values())
    try:
        _validate_report_structure(report)
    except InvalidReport:
        return _badges(*_placeholder_values())
    if report['organisation'].casefold() != owner.casefold():
        return _badges(*_placeholder_values())

    completed_at = _report_completed_at(report, current_time)
    if completed_at is None:
        return _badges(*_placeholder_values())

    target = _target_repository(report, owner, name)
    if target is None:
        return _badges(*_placeholder_values())

    checks_complete, checks_pass = _check_state(target)
    checked_text = completed_at.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    last_checked_color = GREEN if checks_complete else AMBER

    age = _develop_age(target, completed_at)
    threshold = report['parameters']['dormant_days']
    activity_value = f'{age} days' if age is not None and age >= 0 else 'unknown'
    activity_ok = age is not None and 0 <= age <= threshold
    activity_color = GREEN if activity_ok else AMBER

    overall_ok = checks_complete and checks_pass and activity_ok
    compliance_value = 'all checks passed' if overall_ok else 'attention needed'
    return _badges(
        compliance_value,
        activity_value,
        checked_text,
        compliance_color=GREEN if overall_ok else AMBER,
        activity_color=activity_color,
        last_checked_color=last_checked_color,
    )


def _load_report(path):
    try:
        with path.open(encoding='utf-8') as handle:
            report = json.load(handle)
    except FileNotFoundError:
        return None, False
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, True
    try:
        _validate_report_structure(report)
    except InvalidReport:
        return None, True
    return report, False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, help='Governance report JSON; absent/missing files produce placeholders.')
    parser.add_argument('--repository', required=True, type=parse_repository, metavar='OWNER/NAME')
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args(argv)

    report, invalid = _load_report(args.report) if args.report is not None else (None, False)
    current_time = datetime.now(timezone.utc)
    if report is not None:
        completed_at = _report_completed_at(report, current_time)
        if report['organisation'].casefold() != args.repository[0].casefold() or (
                report.get('completed_at') is not None and completed_at is None):
            invalid = True
        # A present but malformed scan timestamp is not a trustworthy report snapshot.
        if report.get('completed_at') is not None and _timestamp(report.get('completed_at')) is None:
            invalid = True

    badges = generate_badges(report, args.repository, current_time)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, svg in badges.items():
        (args.output_dir / filename).write_text(svg, encoding='utf-8')

    if invalid:
        print('Invalid governance report; wrote not-checked badge placeholders.', file=sys.stderr)
        return 1
    if report is None:
        print('No readable governance report; wrote not-checked badge placeholders.', file=sys.stderr)
    else:
        print(f'Wrote {len(badges)} governance badges to the output directory.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())