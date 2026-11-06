#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © Crown Copyright 2026. This work has been developed by the National Digital Twin Programme and is legally attributed to the UK's Department for Business, Innovation, Science and Trade (BIST) as the governing entity.
"""Generate status-only repository badges from an OSPO governance report."""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, time, timedelta, timezone
from html import escape
from pathlib import Path

from governance_report import COLUMNS, ERROR, FAIL, NA, STATUSES, WARN, safe_output_directory

GREEN = '#1a7f37'
AMBER = '#9a6700'
RED = '#cf222e'
GRAY = '#6e7781'
GRACE = timedelta(hours=6)
BADGE_FILENAMES = ('ospo-compliance.svg', 'develop-activity.svg', 'last-checked.svg')
REPOSITORY_PATTERN = re.compile(r'[A-Za-z0-9_.-]+\Z')


class InvalidReport(ValueError):
    """The report does not match the governance report interface."""


def _timestamp(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _validate_now(now):
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('now must be a timezone-aware datetime')
    return now.astimezone(timezone.utc)


def _validate_report(report):
    if (not isinstance(report, dict)
            or not isinstance(report.get('organisation'), str)
            or not report['organisation']
            or not isinstance(report.get('parameters'), dict)
            or not isinstance(report.get('repositories'), list)):
        raise InvalidReport
    threshold = report['parameters'].get('dormant_days')
    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 1 <= threshold <= 3650:
        raise InvalidReport

    seen_names = set()
    for repository in report['repositories']:
        if (not isinstance(repository, dict)
                or not isinstance(repository.get('name'), str)
                or not REPOSITORY_PATTERN.fullmatch(repository['name'])
                or repository['name'] in ('.', '..')
                or not isinstance(repository.get('checks'), dict)
                or not isinstance(repository.get('errors', []), list)):
            raise InvalidReport
        folded_name = repository['name'].casefold()
        if folded_name in seen_names:
            raise InvalidReport
        seen_names.add(folded_name)
    return threshold


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


def _check_status(check):
    if not isinstance(check, dict):
        return 'unknown'
    status = check.get('status')
    applicable = check.get('applicable', True)
    if not isinstance(applicable, bool):
        return 'unknown'
    if status == NA and applicable is False:
        return None
    if applicable is False or status not in STATUSES or status in (NA, ERROR):
        return 'unknown'
    return status


def _compliance(repository):
    checks = repository['checks']
    statuses = [_check_status(checks.get(key)) for key, _title in COLUMNS]
    known_statuses = [status for status in statuses if status is not None]
    if repository.get('errors') or 'unknown' in known_statuses or not known_statuses:
        return 'unknown', GRAY
    if any(status in (WARN, FAIL) for status in known_statuses):
        return 'attention needed', AMBER
    return 'all checks passed', GREEN


def _activity(repository, completed_at, threshold):
    if completed_at is None:
        return 'unknown', GRAY
    activity = repository.get('activity')
    if not isinstance(activity, dict) or activity.get('branch') != 'develop':
        return 'unknown', GRAY
    committed_at = _timestamp(activity.get('last_application_commit_at'))
    if committed_at is None or committed_at > completed_at:
        return 'unknown', GRAY
    age = (completed_at - committed_at).days
    if age < 0:
        return 'unknown', GRAY
    if age <= threshold:
        return f'{age} days', GREEN
    return f'{age} days', AMBER


def _last_checked(completed_at, now):
    if completed_at is None or completed_at > now:
        return 'not checked', GRAY

    slot = datetime.combine(now.date(), time(3, 0), tzinfo=timezone.utc)
    slot -= timedelta(days=now.weekday())
    if slot > now:
        slot -= timedelta(days=7)
    if now - slot < GRACE:
        slot -= timedelta(days=7)

    value = completed_at.strftime('%Y-%m-%d %H:%M UTC')
    if completed_at >= slot:
        return value, GREEN
    if completed_at >= slot - timedelta(days=7):
        return value, AMBER
    return value, RED


def generate_badges(report, now=None):
    """Return three status-only SVG strings for every repository in the report."""
    threshold = _validate_report(report)
    current_time = _validate_now(now if now is not None else datetime.now(timezone.utc))
    completed_at = _timestamp(report.get('completed_at'))
    if completed_at is not None and completed_at > current_time:
        completed_at = None

    badges = {}
    for repository in report['repositories']:
        compliance, compliance_color = _compliance(repository)
        activity, activity_color = _activity(repository, completed_at, threshold)
        checked, checked_color = _last_checked(completed_at, current_time)
        badges[repository['name']] = {
            BADGE_FILENAMES[0]: _badge_svg('OSPO compliance', compliance, compliance_color),
            BADGE_FILENAMES[1]: _badge_svg('Develop activity', activity, activity_color),
            BADGE_FILENAMES[2]: _badge_svg('Last checked', checked, checked_color),
        }
    return badges


def write_badges(report, output_dir, now=None):
    """Replace OUTPUT/repositories with generated SVGs and return the badge map."""
    badges = generate_badges(report, now=now)
    try:
        working_directory = Path.cwd().resolve()
        output_root = Path(output_dir).expanduser().resolve()
        output_root.relative_to(working_directory)
    except (OSError, RuntimeError, ValueError) as exc:
        raise InvalidReport('badge output directory is outside the working directory') from exc
    repositories_dir = output_root / 'repositories'
    if repositories_dir.is_symlink():
        raise InvalidReport
    if repositories_dir.exists():
        shutil.rmtree(repositories_dir)
    repositories_dir.mkdir(parents=True, exist_ok=True)
    for name, files in badges.items():
        destination = repositories_dir / name
        destination.mkdir(parents=True, exist_ok=True)
        for filename, svg in files.items():
            (destination / filename).write_text(svg, encoding='utf-8')
    return badges


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', required=True, type=Path, help='Governance report JSON file.')
    parser.add_argument('--output-dir', required=True, type=safe_output_directory, help='Badge output directory.')
    args = parser.parse_args(argv)

    try:
        with args.report.open(encoding='utf-8') as handle:
            report = json.load(handle)
        badges = write_badges(report, args.output_dir)
    except (OSError, ValueError):
        parser.error('could not read a valid governance report or write SVG badges')
    print(f'Generated badges for {len(badges)} repositories.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
