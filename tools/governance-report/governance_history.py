#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# © Crown Copyright 2026. This work has been developed by the National Digital Twin Programme and is legally attributed to the UK's Department for Business, Innovation, Science and Trade (BIST) as the governing entity.
"""Prepare public overview artifacts and append immutable governance snapshots."""

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

from governance_report import COLUMNS, STATUSES
from repository_badges import BADGE_FILENAMES, InvalidReport, _timestamp, _validate_report

EVENTS = ('push', 'workflow_dispatch', 'schedule')
RUN_PATTERN = re.compile(r'run-([1-9][0-9]*)-attempt-([1-9][0-9]*)\Z')
NAME_PATTERN = re.compile(r'[A-Za-z0-9_.-]+\Z')
OWNER_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9-]*\Z')
LABELS = ('OSPO compliance', 'Days since last commit to develop branch', 'Last checked')


class InvalidHistory(ValueError):
    """An unsafe, incomplete, or conflicting history operation."""


def _require(condition):
    if not condition:
        raise InvalidHistory('invalid or unsafe governance history input')


def _safe_name(value):
    return isinstance(value, str) and NAME_PATTERN.fullmatch(value) and value not in ('.', '..')


def _safe_path(value):
    """Reject traversal and symlinks, including dangling links and linked ancestors."""
    path = Path(value).expanduser()
    _require('..' not in path.parts)
    path = path.absolute()
    for component in (*reversed(path.parents), path):
        _require(not component.is_symlink())
    return path


def _read_bytes(path):
    path = _safe_path(path)
    _require(stat.S_ISREG(path.stat().st_mode))
    return path.read_bytes()


def _markdown(value):
    # Numeric entities render as text, never as Markdown/HTML syntax.
    return ''.join(character if character.isascii() and character.isalnum()
                   or character in ' -/.' else f'&#{ord(character)};' for character in value)


def _completed_report(report):
    try:
        _validate_report(report)
    except InvalidReport:
        raise InvalidHistory('invalid or incomplete governance report') from None
    completed = _timestamp(report.get('completed_at'))
    _require(completed is not None and completed <= datetime.now(timezone.utc))
    _require(OWNER_PATTERN.fullmatch(report['organisation']))
    _require(report['parameters'].get('scan_branch') in ('auto', 'main', 'develop'))
    for repository in report['repositories']:
        _require(repository.get('visibility') in ('public', 'private', 'internal'))
        _require(not repository.get('errors'))
        _require(isinstance(repository.get('scan_branch'), str) and repository['scan_branch'])
        for key, _title in COLUMNS:
            check = repository['checks'].get(key)
            _require(isinstance(check, dict) and check.get('status') in STATUSES)
            _require(isinstance(check.get('applicable', True), bool))
    return completed


def _write_snapshot(destination, files):
    """Stage complete bytes on the same filesystem before publishing a new directory."""
    destination = _safe_path(destination)
    _require(not destination.exists())
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.governance-history-', dir=destination.parent) as temporary:
        staged = Path(temporary) / 'snapshot'
        staged.mkdir()
        (staged / 'badges').mkdir()
        for relative, content in files.items():
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        _require(not _safe_path(destination).exists())
        staged.rename(destination)


def prepare(report, badges_dir, output_dir, *, repository, run_id, run_attempt, source_sha, event):
    """Return the new snapshot path; report is an internal, already decoded JSON object."""
    completed = _completed_report(report)
    _require(isinstance(repository, str) and repository.count('/') == 1)
    owner, name = repository.split('/')
    _require(OWNER_PATTERN.fullmatch(owner) and _safe_name(name))
    _require(isinstance(run_id, str) and re.fullmatch(r'[1-9][0-9]*', run_id))
    _require(isinstance(run_attempt, str) and re.fullmatch(r'[1-9][0-9]*', run_attempt))
    _require(isinstance(source_sha, str) and re.fullmatch(r'[0-9a-fA-F]{40}', source_sha))
    _require(event in EVENTS)
    output = _safe_path(output_dir)
    _require(not output.exists() or output.is_dir() and not any(output.iterdir()))
    badges = _safe_path(badges_dir) / 'repositories'
    public = sorted((entry for entry in report['repositories'] if entry['visibility'] == 'public'),
                    key=lambda entry: entry['name'].casefold())
    files = {}
    lines = [
        '# Public OSPO governance overview', '',
        f'- Completed at: {completed.isoformat().replace("+00:00", "Z")} (UTC)',
        f'- Scan branch: {_markdown(report["parameters"]["scan_branch"])}',
        f'- Source SHA: {source_sha}',
        f'- Run: [run {run_id}, attempt {run_attempt}]'
        f'(https://github.com/{repository}/actions/runs/{run_id}/attempts/{run_attempt})',
        f'- Event: {_markdown(event)}', '',
        '## OSPO compliance legend', '',
        '- **Pass (green):** All compliance checks pass or qualify as not applicable.',
        '- **Fail (red):** At least one compliance check fails, such as a verified credential finding.',
        '- **Attention (amber):** No check fails, and at least one check has a warning. Attention takes priority over unknown.',
        '- **Unknown (gray):** No check fails or warns, but a result is unavailable or cannot be verified, '
        'including an unavailable credential scan.',
        '',
        'For a `develop` scan, precedence is fail, then attention, then unknown, then pass. '
        'A repository not scanned on `develop` remains unknown. '
        'Commit age and last checked are separate and do not affect compliance.', '',
        '| Repository | ' + ' | '.join(LABELS) + ' |',
        '| --- | --- | --- | --- |',
    ]
    for entry in public:
        name = entry['name']
        images = []
        for filename, label in zip(BADGE_FILENAMES, LABELS):
            relative = f'badges/{name}/{filename}'
            files[relative] = _read_bytes(badges / name / filename)
            images.append(f'![{label}]({relative})')
        lines.append(f'| [{_markdown(name)}](https://github.com/{report["organisation"]}/{name}) | '
                     + ' | '.join(images) + ' |')
    if not public:
        lines += ['', 'No public repositories in this scan.']
    files['README.md'] = ('\n'.join(lines) + '\n').encode('utf-8')
    destination = output / 'snapshots' / completed.date().isoformat() / f'run-{run_id}-attempt-{run_attempt}'
    _write_snapshot(destination, files)
    return destination


def _children(path):
    path = _safe_path(path)
    _require(path.is_dir())
    children = list(path.iterdir())
    for child in children:
        _safe_path(child)
    return {child.name: child for child in children}


def _snapshot_files(path):
    children = _children(path)
    _require(set(children) == {'README.md', 'badges'})
    files = {'README.md': _read_bytes(children['README.md'])}
    seen = set()
    for name, directory in _children(children['badges']).items():
        _require(_safe_name(name) and name.casefold() not in seen)
        seen.add(name.casefold())
        badges = _children(directory)
        _require(set(badges) == set(BADGE_FILENAMES))
        for filename, badge in badges.items():
            files[f'badges/{name}/{filename}'] = _read_bytes(badge)
    return files


def _snapshots(root):
    """Validate the entire history namespace, not unrelated archive root files."""
    snapshots = {}
    for day, directory in _children(root).items():
        _require(re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', day))
        _require(date.fromisoformat(day).isoformat() == day)
        runs = _children(directory)
        _require(runs)
        for run, snapshot in runs.items():
            _require(RUN_PATTERN.fullmatch(run))
            snapshots[(day, run)] = _snapshot_files(snapshot)
    return snapshots


def _index(snapshots):
    def newest(key):
        day, run = key
        match = RUN_PATTERN.fullmatch(run)
        return day, int(match[1]), int(match[2])

    lines = ['# Public OSPO governance history', '', 'Immutable overviews for completed scans.', '']
    for day, run in sorted(snapshots, key=newest, reverse=True):
        lines.append(f'- [{day} / {run}](snapshots/{day}/{run}/README.md)')
    return ('\n'.join(lines) + '\n').encode('utf-8')


def append(snapshot_dir, archive_dir):
    """Append exactly one artifact snapshot, or accept an identical duplicate."""
    source = _safe_path(snapshot_dir)
    _require(set(_children(source)) == {'snapshots'})
    incoming = _snapshots(source / 'snapshots')
    _require(len(incoming) == 1)
    archive = _safe_path(archive_dir)
    _require(archive.is_dir())
    # Overlapping trees could otherwise turn artifact input into mutable archive data.
    _require(source != archive and source not in archive.parents and archive not in source.parents)
    index = _safe_path(archive / 'README.md')
    _require(not index.exists() or index.is_file())
    history = _safe_path(archive / 'snapshots')
    existing = _snapshots(history) if history.exists() else {}
    key, files = next(iter(incoming.items()))
    day, run = key
    # Run/attempt identity must not be reused under a different completion date.
    duplicates = [old for old in existing if old[1] == run]
    if duplicates:
        _require(duplicates == [key] and existing[key] == files)
    else:
        _write_snapshot(history / day / run, files)
    existing.update(incoming)
    with tempfile.NamedTemporaryFile(prefix='.governance-index-', dir=archive, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(_index(existing))
            handle.close()
            _safe_path(index)
            os.replace(temporary, index)
        finally:
            temporary.unlink(missing_ok=True)
    return history / day / run


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prepare_parser = commands.add_parser('prepare', help='Prepare one public snapshot artifact.')
    for option in ('report', 'badges-dir', 'output-dir', 'repository', 'run-id', 'run-attempt', 'source-sha', 'event'):
        prepare_parser.add_argument('--' + option, required=True)
    append_parser = commands.add_parser('append', help='Append an artifact and rebuild the archive index.')
    append_parser.add_argument('--snapshot-dir', required=True)
    append_parser.add_argument('--archive-dir', required=True)
    args = vars(parser.parse_args(argv))
    command = args.pop('command')
    try:
        if command == 'prepare':
            args['report'] = json.loads(_read_bytes(args['report']))
            prepare(**args)
        else:
            append(**args)
    except (OSError, ValueError, RuntimeError, OverflowError):
        print('error: invalid, incomplete, unsafe, or conflicting governance history input', file=sys.stderr)
        return 1
    print('Prepared public governance snapshot.' if command == 'prepare' else 'Updated public governance history.')
    return 0


if __name__ == '__main__':
    sys.exit(main())