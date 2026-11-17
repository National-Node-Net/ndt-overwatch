# SPDX-License-Identifier: Apache-2.0
# © Crown Copyright 2026. This work has been developed by the National Digital Twin Programme and is legally attributed to the UK's Department for Business, Innovation, Science and Trade (BIST) as the governing entity.

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

import governance_history as history
from repository_badges import BADGE_FILENAMES
from test_governance_history import make_report


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / '.github/workflows/governance-report.yml'


def publishing_script():
    step = WORKFLOW.read_text().split('      - name: Append snapshot to governance history branch\n', 1)[1]
    return textwrap.dedent(step.split('        run: |\n', 1)[1])


class HistoryWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.remote = self.root / 'remotes/Org/overwatch.git'
        self.remote.parent.mkdir(parents=True)
        subprocess.run(['git', 'init', '--quiet', '--bare', str(self.remote)], check=True)
        self.badges = self.root / 'badges'
        self.report = make_report()
        for repository in self.report['repositories']:
            if repository['visibility'] == 'public':
                directory = self.badges / 'repositories' / repository['name']
                directory.mkdir(parents=True)
                for filename in BADGE_FILENAMES:
                    (directory / filename).write_text('<svg>frozen scan</svg>\n')

    def publish(self, run_id='123', attempt='1', source_ref='refs/heads/feature/governance-report'):
        runner = self.root / f'runner-{run_id}-{attempt}-{len(list(self.root.glob("runner-*")))}'
        runner.mkdir()
        history.prepare(self.report, self.badges, runner / 'governance-history',
                        repository='Org/overwatch', run_id=run_id, run_attempt=attempt,
                        source_sha='a' * 40, event='push')
        env = dict(os.environ, RUNNER_TEMP=str(runner), GITHUB_SERVER_URL=(self.root / 'remotes').as_uri(),
                   GITHUB_REPOSITORY='Org/overwatch', GITHUB_RUN_ID=run_id, GITHUB_RUN_ATTEMPT=attempt,
                   SOURCE_REF=source_ref, PUBLISH_TOKEN='offline-test-token', PYTHONDONTWRITEBYTECODE='1',
                   GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1')
        # Ignore caller-specific authentication and Git overrides for this isolated local test.
        for key in list(env):
            if key.startswith(('GIT_CONFIG_KEY_', 'GIT_CONFIG_VALUE_')) or key in ('GIT_CONFIG_COUNT', 'GIT_DIR', 'GIT_WORK_TREE'):
                env.pop(key)
        return subprocess.run(['bash', '-c', publishing_script()], cwd=ROOT, env=env,
                              text=True, capture_output=True)

    def git(self, *args):
        return subprocess.run(['git', '--git-dir', str(self.remote), *args], check=True,
                              text=True, capture_output=True).stdout.strip()

    def test_publisher_creates_branch_appends_preserves_and_is_idempotent(self):
        first = self.publish()
        self.assertEqual(first.returncode, 0, first.stderr)
        first_sha = self.git('rev-parse', 'refs/heads/history/governance')
        first_path = 'snapshots/2026-11-06/run-123-attempt-1/README.md'
        original = self.git('show', f'{first_sha}:{first_path}')
        second = self.publish(run_id='124')
        self.assertEqual(second.returncode, 0, second.stderr)
        head = self.git('rev-parse', 'refs/heads/history/governance')
        self.assertNotEqual(head, first_sha)
        self.assertEqual(self.git('show', f'{head}:{first_path}'), original)
        index = self.git('show', f'{head}:README.md')
        self.assertLess(index.index('run-124-attempt-1'), index.index('run-123-attempt-1'))
        duplicate = self.publish(run_id='124')
        self.assertEqual(duplicate.returncode, 0, duplicate.stderr)
        self.assertEqual(self.git('rev-parse', 'refs/heads/history/governance'), head)
        self.assertEqual(self.git('rev-list', '--count', 'history/governance'), '2')
        files = self.git('ls-tree', '-r', '--name-only', 'history/governance').splitlines()
        self.assertTrue(all(path.endswith(('.md', '.svg')) for path in files))
        self.assertFalse(any('private-project' in path or 'internal-project' in path for path in files))

    def test_publisher_rejects_untrusted_ref_without_creating_branch(self):
        result = self.publish(source_ref='refs/heads/untrusted-feature')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unsupported source branch', result.stderr)
        self.assertEqual(self.git('for-each-ref', '--format=%(refname)'), '')

    def test_publisher_supports_develop_and_main(self):
        for index, ref in enumerate(('refs/heads/develop', 'refs/heads/main'), start=1):
            with self.subTest(ref=ref):
                result = self.publish(run_id=str(index), source_ref=ref)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_shell_syntax_and_history_job_trigger_contract(self):
        checked = subprocess.run(['bash', '-n'], input=publishing_script(), text=True, capture_output=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        workflow = WORKFLOW.read_text()
        scan = workflow.split('  governance-report:\n', 1)[1].split('  publish-governance-badges:\n', 1)[0]
        scan_guard = next(line for line in scan.splitlines() if line.startswith('    if:'))
        for ref in ('feature/governance-report', 'develop', 'main'):
            self.assertIn(f"github.ref == 'refs/heads/{ref}'", scan_guard)
        job = workflow.split('  publish-governance-history:\n', 1)[1]
        self.assertIn("needs.governance-report.result == 'success'", job)
        self.assertNotIn("github.event_name == 'schedule'", job)
        self.assertNotIn('ls-remote "$repository_url"', job)  # No latest-source-SHA gate for history.
        self.assertNotIn('--force ', publishing_script())
        self.assertIn('ref: ${{ github.sha }}', job)
        self.assertIn('persist-credentials: false', job)
        self.assertIn('contents: write', job)
        self.assertIn('name: governance-history', job)
        self.assertNotIn('name: governance-report\n', job)  # Full report is not downloaded for publication.
        preparation = workflow.split('      - name: Prepare frozen public governance overview\n', 1)[1]
        preparation = preparation.split('      - name: Upload governance report\n', 1)[0]
        self.assertNotIn('if:', preparation)  # All successful scan triggers prepare history.
        self.assertIn('HISTORY_RUN_ATTEMPT: ${{ github.run_attempt }}', preparation)
        self.assertIn('--badges-dir governance-badges', preparation)


if __name__ == '__main__':
    unittest.main()