"""Behavior checks against the real CLI, using only synthetic temporary data."""
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'skills/job-assistant/scripts/workspace.py'


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ws = self.root / 'candidate'
        self.call('init')

    def call(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(SCRIPT), '--workspace', str(self.ws), *args],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0 if ok else 2, result.stderr)
        return json.loads(result.stdout) if ok else result.stderr

    def rank(self, **updates):
        job = dict(company='示例公司', title='测试岗位', location='示例城市',
                   jd='仅供测试。需要项目协调经验。', url='https://example.com/jobs/1',
                   scores={'资格': 3, '经验': 4, '技能': 3, '契合': 4, '发展': 2},
                   strengths=['F001 对应项目协调'], gaps=['缺少行业证据'])
        job.update(updates)
        src = self.root / 'input.json'
        src.write_text(json.dumps([job], ensure_ascii=False))
        return self.call('rank', '--input', str(src))['jobs'][0]

    def test_init_preserves_confirmed_facts_and_other_users_are_isolated(self):
        profile = self.ws / 'profile.md'
        profile.write_text('F001 已确认，来源：用户确认。')
        self.call('init')
        self.assertEqual(profile.read_text(), 'F001 已确认，来源：用户确认。')
        self.ws = self.root / 'second'
        self.call('init')
        self.assertNotIn('F001 已确认', (self.ws / 'profile.md').read_text())

    def test_prepare_does_not_claim_application_and_retry_is_idempotent(self):
        job = self.rank()
        first = self.call('prepare', '--job', job['id'], '--request-id', 'draft-one')
        path = Path(first['revision_path'])
        (path / 'resume.html').write_text('draft preserved')
        again = self.call('prepare', '--job', job['id'], '--request-id', 'draft-one')
        self.assertEqual(first['revision_path'], again['revision_path'])
        stored = self.call('list')['jobs'][0]
        self.assertEqual(stored['status'], 'preparing')
        self.assertIsNone(stored['applied_on'])
        self.assertEqual((path / 'resume.html').read_text(), 'draft preserved')
        newer = self.call('prepare', '--job', job['id'], '--request-id', 'draft-two')
        self.assertNotEqual(first['revision_path'], newer['revision_path'])
        self.assertEqual((path / 'resume.html').read_text(), 'draft preserved')

    def complete_materials(self, job):
        result = self.call('prepare', '--job', job['id'], '--request-id', 'draft')
        folder = Path(result['revision_path'])
        for name in ['resume.txt', 'messages.md', 'audit.md', 'checks.json']:
            (folder / name).write_text('{}' if name.endswith('.json') else 'Synthetic artifact')
        (folder / 'checks.json').write_text(json.dumps({
            'fact_audit': 'passed', 'audit_context': 'independent',
            'cross_format_consistency': 'passed', 'pdf_render': 'pending',
            'pdf_text_layer': 'pending', 'human_approval': 'pending', 'notes': []}))
        self.call('ready', '--job', job['id'], '--revision', 'v001')

    def test_applied_requires_confirmation_and_freezes_selected_revision(self):
        job = self.rank()
        self.complete_materials(job)
        self.call('applied', '--job', job['id'], '--revision', 'v001', '--date', '2026-01-10', ok=False)
        self.assertEqual(self.call('list')['jobs'][0]['status'], 'prepared')
        self.call('applied', '--job', job['id'], '--revision', 'v001', '--date', '2026-01-10', '--confirmed')
        self.call('applied', '--job', job['id'], '--revision', 'v001', '--date', '2026-01-10', '--confirmed')
        result = self.call('list')['jobs'][0]
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(result['applied_revision'], 'v001')
        self.assertEqual(len(result['events']), 1)
        self.call('prepare', '--job', job['id'], '--request-id', 'later-draft')
        self.assertEqual(self.call('list')['jobs'][0]['applied_revision'], 'v001')

    def test_followup_draft_does_not_count_and_recent_reply_resets_clock(self):
        job = self.rank()
        self.complete_materials(job)
        self.call('applied', '--job', job['id'], '--revision', 'v001', '--date', '2026-01-01', '--confirmed')
        self.assertEqual(len(self.call('followups', '--today', '2026-01-15')['jobs']), 1)
        self.call('event', '--job', job['id'], '--event-id', 'reply', '--kind', 'interview', '--date', '2026-01-14')
        self.assertEqual(self.call('followups', '--today', '2026-01-15')['jobs'], [])
        self.call('event', '--job', job['id'], '--event-id', 'follow', '--kind', 'followup_sent', '--date', '2026-01-26', ok=False)
        for n, day in [(1, '2026-01-26'), (2, '2026-02-07')]:
            self.call('event', '--job', job['id'], '--event-id', f'follow-{n}', '--kind', 'followup_sent', '--date', day, '--confirmed')
        self.assertEqual(self.call('followups', '--today', '2026-03-01')['jobs'], [])

    def test_rank_merges_same_job_preserves_prepared_state_and_scores_correctly(self):
        first = self.rank()
        self.assertEqual(first['total'], 67)
        self.complete_materials(first)
        second = self.rank(company=' 示例公司 ', url='https://example.com/jobs/1?tracking=2')
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(second['status'], 'prepared')
        self.assertEqual(len(self.call('list')['jobs']), 1)
        other = self.rank(location='另一城市')
        self.assertNotEqual(first['id'], other['id'])

    def test_source_and_score_evidence_survive_storage_and_revision_snapshot(self):
        source = {'type': 'user_paste', 'date': '2026-01-01', 'path': 'inputs/source.md'}
        rationale = {'资格': 'JD 未设门槛', '经验': 'F001 对应协调经验'}
        job = self.rank(source=source, score_rationale=rationale)
        stored = self.call('list')['jobs'][0]
        self.assertEqual(stored.get('source'), source)
        self.assertEqual(stored.get('score_rationale'), rationale)
        result = self.call('prepare', '--job', job['id'], '--request-id', 'evidence')
        snapshot = json.loads((Path(result['revision_path']) / 'assessment.json').read_text())
        self.assertEqual(snapshot['source'], source)
        self.assertEqual(snapshot['score_rationale'], rationale)

    def test_missing_information_is_not_zero_and_invalid_deadline_does_not_expire(self):
        job = self.rank(scores={'资格': None, '经验': 4, '技能': 3, '契合': 4, '发展': 2}, deadline='2026-02-30')
        self.assertIsNone(job['total'])
        self.assertIsNone(job['deadline'])
        self.assertEqual(job['deadline_raw'], '2026-02-30')
        self.assertEqual(len(self.call('list', '--today', '2026-03-01', '--actionable')['jobs']), 1)

    def test_past_deadline_is_excluded_without_hiding_unknown_dates(self):
        self.rank(deadline='2026-01-10')
        self.assertEqual(self.call('list', '--today', '2026-01-10', '--actionable')['jobs'][0]['expired'], False)
        self.assertEqual(self.call('list', '--today', '2026-01-11', '--actionable')['jobs'], [])

    def test_invalid_batch_is_atomic_and_deal_breaker_requires_evidence(self):
        self.rank()
        before = (self.ws / 'jobs.json').read_bytes()
        self.rank_error_input([dict(company='Other', title='Role', jd='text'),
                               dict(company='Broken', title='Role', jd='text', deal_breaker=True)])
        self.assertEqual((self.ws / 'jobs.json').read_bytes(), before)

    def rank_error_input(self, payload):
        src = self.root / 'bad.json'
        src.write_text(json.dumps(payload))
        self.call('rank', '--input', str(src), ok=False)

    def test_csv_quotes_commas_and_newlines_and_rejects_path_traversal(self):
        self.rank(company='示例,公司', title='测试\n岗位')
        out = self.root / 'tracker.csv'
        self.call('export', '--output', str(out))
        row = list(csv.DictReader(io.StringIO(out.read_text(encoding='utf-8-sig'))))[0]
        self.assertEqual(row['company'], '示例,公司')
        self.assertEqual(row['title'], '测试\n岗位')
        self.call('prepare', '--job', '../../escape', '--request-id', 'bad', ok=False)
        self.assertFalse((self.root / 'escape').exists())

    def test_ready_requires_artifacts_but_never_implies_human_approval(self):
        job = self.rank()
        self.call('prepare', '--job', job['id'], '--request-id', 'draft')
        self.call('ready', '--job', job['id'], '--revision', 'v001', ok=False)
        self.assertEqual(self.call('list')['jobs'][0]['status'], 'preparing')

    def test_pending_independent_audit_cannot_be_marked_ready(self):
        job = self.rank()
        self.complete_materials(job)
        folder = self.ws / 'applications' / job['id'] / 'v001'
        checks = json.loads((folder / 'checks.json').read_text())
        checks.update(fact_audit='pending', audit_context='unavailable')
        (folder / 'checks.json').write_text(json.dumps(checks))
        self.call('ready', '--job', job['id'], '--revision', 'v001', ok=False)

    def test_edit_after_audit_requires_recheck_before_submission(self):
        job = self.rank()
        self.complete_materials(job)
        path = self.ws / 'applications' / job['id'] / 'v001' / 'resume.txt'
        path.write_text('Changed after review')
        self.call('applied', '--job', job['id'], '--revision', 'v001', '--date', '2026-01-10', '--confirmed', ok=False)
        self.assertIsNone(self.call('list')['jobs'][0]['applied_on'])

    def test_future_events_and_conflicting_retry_are_rejected_without_mutation(self):
        job = self.rank()
        self.complete_materials(job)
        self.call('applied', '--job', job['id'], '--revision', 'v001', '--date', '2026-01-01', '--confirmed')
        before = (self.ws / 'jobs.json').read_bytes()
        self.call('event', '--job', job['id'], '--event-id', 'future', '--kind', 'read', '--date', '2999-01-01', ok=False)
        self.assertEqual((self.ws / 'jobs.json').read_bytes(), before)
        self.call('event', '--job', job['id'], '--event-id', 'read-one', '--kind', 'read', '--date', '2026-01-02')
        self.call('event', '--job', job['id'], '--event-id', 'read-one', '--kind', 'interview', '--date', '2026-01-02', ok=False)
        self.assertEqual(self.call('list')['jobs'][0]['status'], 'read')

    def test_unconfirmed_and_malformed_scores_do_not_enter_state(self):
        for bad in [True, 2.5, 6, -1, '3']:
            self.rank_error_input([dict(company='示例', title='岗位', jd='测试',
                scores={'资格': bad, '经验': 3, '技能': 3, '契合': 3, '发展': 3})])
        job = self.rank()
        self.assertEqual(len(self.call('list')['jobs']), 1)

    def test_lock_and_symlink_do_not_allow_writes_outside_workspace(self):
        lock = self.ws / '.job-assistant.lock'
        lock.mkdir()
        self.call('list', ok=False)
        lock.rmdir()
        job = self.rank()
        external = self.root / 'external'
        external.mkdir()
        (self.ws / 'applications').symlink_to(external, target_is_directory=True)
        self.call('prepare', '--job', job['id'], '--request-id', 'escaped', ok=False)
        self.assertEqual(list(external.iterdir()), [])

    def test_corrupt_state_is_not_silently_reset(self):
        path = self.ws / 'jobs.json'
        path.write_text('{broken')
        self.call('init', ok=False)
        self.assertEqual(path.read_text(), '{broken')


if __name__ == '__main__':
    unittest.main()
