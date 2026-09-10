#!/usr/bin/env python3
"""Local job-search state. Python 3.10+, standard library only; no network calls."""
import argparse
from contextlib import contextmanager
from datetime import date
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unicodedata

SKILL = Path(__file__).resolve().parents[1]
WEIGHTS = {'资格': 4, '经验': 6, '技能': 5, '契合': 3, '发展': 2}
STATES = {'ranked', 'preparing', 'prepared', 'applied', 'read', 'interview',
          'offer', 'rejected', 'withdrawn', 'closed', 'no_response'}
ACTIVE = {'applied', 'read', 'interview'}
KINDS = {'read', 'interview', 'offer', 'rejected', 'withdrawn', 'closed',
         'no_response', 'reply', 'followup_sent'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def json_read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def json_write(path, value):
    require(not path.is_symlink(), 'Refusing a symlink destination')
    fd, temp = tempfile.mkstemp(prefix='.state-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def iso(value):
    require(isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value), 'Use YYYY-MM-DD')
    return date.fromisoformat(value)


def clean_text(value, name, required=False):
    require(isinstance(value, str), f'{name} must be text')
    require(not required or value.strip(), f'{name} is required')
    return value


def identity(item):
    parts = [unicodedata.normalize('NFKC', item.get(k, '')).strip().casefold()
             for k in ('company', 'title', 'location', 'requisition_id')]
    return 'job-' + hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:20]


def validate_job_input(item):
    require(isinstance(item, dict), 'Each job must be an object')
    allowed = {'company', 'title', 'jd', 'location', 'requisition_id', 'url', 'track',
               'scores', 'strengths', 'gaps', 'deal_breaker', 'deal_breaker_quote',
               'deadline', 'source', 'score_rationale'}
    require(set(item) <= allowed, 'Unsupported job fields; use the documented schema to avoid data loss')
    out = {k: clean_text(item.get(k, ''), k, k in {'company', 'title', 'jd'})
           for k in ('company', 'title', 'jd', 'location', 'requisition_id', 'url', 'track')}
    source = item.get('source', {})
    require(isinstance(source, dict) and set(source) <= {'type', 'date', 'path', 'note', 'verified_hiring'}, 'Invalid source metadata')
    for key in ('type', 'path', 'note'):
        if key in source:
            clean_text(source[key], key)
    if source.get('date') is not None:
        iso(source['date'])
    if 'verified_hiring' in source:
        require(source['verified_hiring'] is None or type(source['verified_hiring']) is bool, 'verified_hiring must be boolean or null')
    out['source'] = source
    rationale = item.get('score_rationale', {})
    require(isinstance(rationale, dict) and set(rationale) <= set(WEIGHTS) and all(isinstance(v, str) for v in rationale.values()), 'Invalid score rationale')
    out['score_rationale'] = rationale
    scores = item.get('scores', {k: None for k in WEIGHTS})
    require(isinstance(scores, dict) and set(scores) == set(WEIGHTS), 'scores must contain the five documented dimensions')
    require(all(v is None or type(v) is int and 0 <= v <= 5 for v in scores.values()), 'Scores must be integers 0–5 or null')
    out['scores'] = scores
    out['total'] = sum(scores[k] * w for k, w in WEIGHTS.items()) if None not in scores.values() else None
    out['deal_breaker'] = item.get('deal_breaker', False)
    require(type(out['deal_breaker']) is bool, 'deal_breaker must be boolean')
    out['deal_breaker_quote'] = clean_text(item.get('deal_breaker_quote', ''), 'deal_breaker_quote')
    if out['deal_breaker']:
        quote = out['deal_breaker_quote']
        require(quote.strip() and quote in out['jd'], 'A deal-breaker requires a verbatim JD quote')
        out['total'] = 0
    for field in ('strengths', 'gaps'):
        out[field] = item.get(field, [])
        require(isinstance(out[field], list) and all(isinstance(v, str) for v in out[field]), f'{field} must be a text list')
    raw = item.get('deadline', '')
    require(raw is None or isinstance(raw, str), 'deadline must be text or null')
    out['deadline_raw'] = raw
    try:
        out['deadline'] = iso(raw).isoformat()
    except (ValueError, TypeError):
        out['deadline'] = None
    out['id'] = identity(out)
    return out


def load(workspace):
    value = json_read(workspace / 'jobs.json')
    require(isinstance(value, dict) and value.get('schema_version') == 1 and isinstance(value.get('jobs'), list), 'Unsupported or damaged state; preserve and repair the file')
    ids = set()
    for job in value['jobs']:
        require(isinstance(job, dict) and re.fullmatch(r'job-[0-9a-f]{20}', job.get('id', '')), 'Invalid job identity')
        require(job['id'] not in ids and job.get('status') in STATES, 'Duplicate job or invalid status')
        require(isinstance(job.get('revisions'), list) and isinstance(job.get('events'), list), 'Invalid history')
        ids.add(job['id'])
    return value


@contextmanager
def locked(workspace):
    lock = workspace / '.job-assistant.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError('Workspace is locked. Check the other run; remove a stale lock only after confirming it has stopped.')
    try:
        yield
    finally:
        lock.rmdir()


def safe_path(workspace, *parts):
    path = workspace.joinpath(*parts)
    require(path.resolve().is_relative_to(workspace), 'Path escapes workspace')
    for current in [path, *path.parents]:
        if current == workspace:
            break
        require(not current.is_symlink(), 'Symlinks are not allowed in managed state')
    return path


def init(workspace):
    require(not workspace.is_relative_to(SKILL), 'User data must live outside the installed skill')
    workspace.mkdir(parents=True, exist_ok=True)
    with locked(workspace):
        for name in ('jobs.json', 'profile.md', 'preferences.json', 'tracks.md', '.gitignore'):
            safe_path(workspace, name)
        if (workspace / 'jobs.json').exists():
            load(workspace)
        else:
            require(not any((workspace / n).exists() for n in ('profile.md', 'preferences.json', 'tracks.md')), 'Existing unmanaged profile: choose a new workspace; do not overwrite')
            json_write(workspace / 'jobs.json', {'schema_version': 1, 'jobs': []})
        for name in ('profile.md', 'preferences.json', 'tracks.md'):
            target = workspace / name
            if not target.exists():
                shutil.copyfile(SKILL / 'assets' / name, target)
        ignored = workspace / '.gitignore'
        if not ignored.exists():
            ignored.write_text('*\n', encoding='utf-8')
    return {'workspace': str(workspace), 'status': 'initialized'}


def select(data, job_id):
    matches = [j for j in data['jobs'] if j['id'] == job_id]
    require(len(matches) == 1, 'Unknown job ID; use list to select an existing job')
    return matches[0]


def revision(job, version):
    matches = [r for r in job['revisions'] if r['version'] == version]
    require(len(matches) == 1, 'Unknown revision')
    return matches[0]


def material_checks(workspace, rev):
    folder = safe_path(workspace, rev['path'])
    names = ['jd.md', 'resume.html', 'resume.txt', 'messages.md', 'audit.md', 'checks.json']
    require(all(safe_path(workspace, rev['path'], n).is_file() and (folder / n).stat().st_size for n in names), 'Required material or check record is missing')
    checks = json_read(folder / 'checks.json')
    require(isinstance(checks, dict), 'checks.json must be an object')
    for key in ('fact_audit', 'cross_format_consistency', 'pdf_render', 'pdf_text_layer'):
        require(checks.get(key) in {'passed', 'pending', 'failed'}, f'Invalid check status: {key}')
    require(checks.get('human_approval') in {'pending', 'approved'}, 'Invalid human approval status')
    require(checks.get('fact_audit') == 'passed' and checks.get('audit_context') == 'independent', 'Independent fact audit has not passed')
    require(checks.get('cross_format_consistency') == 'passed', 'Cross-format consistency has not passed')
    pdf = safe_path(workspace, rev['path'], 'resume.pdf')
    if checks['pdf_render'] == 'passed' or checks['pdf_text_layer'] == 'passed':
        require(pdf.is_file() and pdf.stat().st_size, 'PDF marked checked but file missing')
    if pdf.is_file():
        names.append('resume.pdf')
    return {n: hashlib.sha256((folder / n).read_bytes()).hexdigest() for n in names}


def prepare(workspace, job, request_id):
    clean_text(request_id, 'request-id', True)
    existing = [r for r in job['revisions'] if r['request_id'] == request_id]
    if existing:
        r = existing[0]
        require(r['version'] != job.get('applied_revision'), 'This revision was submitted; use a new request-id')
        return {'revision': r['version'], 'revision_path': str(safe_path(workspace, r['path']))}
    base = safe_path(workspace, 'applications', job['id'])
    base.mkdir(parents=True, exist_ok=True)
    number = 1
    while (base / f'v{number:03d}').exists():
        number += 1
    version = f'v{number:03d}'
    folder = base / version
    folder.mkdir()
    (folder / 'jd.md').write_text(job['jd'], encoding='utf-8')
    shutil.copyfile(SKILL / 'assets/resume.html', folder / 'resume.html')
    json_write(folder / 'assessment.json', {k: v for k, v in job.items() if k not in {'events', 'revisions'}})
    job['revisions'].append({'version': version, 'request_id': request_id,
                             'path': folder.relative_to(workspace).as_posix(), 'ready': False})
    if job['applied_on'] is None:
        job['status'] = 'preparing'
    return {'revision': version, 'revision_path': str(folder)}


def run(args):
    workspace = Path(args.workspace).expanduser().resolve()
    if args.command == 'init':
        return init(workspace)
    require(workspace.is_dir(), 'Workspace missing; run init')
    safe_path(workspace, 'jobs.json')
    with locked(workspace):
        data = load(workspace)
        command = args.command
        if command in {'list', 'followups'}:
            today = iso(args.today)
            jobs = []
            for job in data['jobs']:
                view = dict(job)
                view['expired'] = bool(job['deadline'] and iso(job['deadline']) < today)
                view['urgent'] = bool(job['deadline'] and 0 <= (iso(job['deadline']) - today).days <= 7)
                if command == 'list' and args.actionable and (job['applied_on'] or job['deal_breaker'] or view['expired'] or job['status'] in {'closed', 'withdrawn'}):
                    continue
                if command == 'followups':
                    require(args.days >= 1, 'days must be positive')
                    sent = [e for e in job['events'] if e['kind'] == 'followup_sent']
                    if job['status'] not in ACTIVE or len(sent) >= 2 or not job['applied_on']:
                        continue
                    last = max([iso(job['applied_on']), *[iso(e['date']) for e in job['events']]])
                    if (today - last).days <= args.days:
                        continue
                    view['days_since_activity'] = (today - last).days
                    view['followups_sent'] = len(sent)
                jobs.append(view)
            jobs.sort(key=lambda j: (j['total'] is not None, j['total'] or 0, j['urgent']), reverse=True)
            return {'jobs': jobs}
        if command == 'export':
            output = Path(args.output).expanduser().resolve()
            require(output != workspace / 'jobs.json', 'Export cannot replace state')
            fields = ['id', 'company', 'title', 'location', 'track', 'status', 'total', 'applied_on', 'applied_revision']
            with output.open('x', encoding='utf-8-sig', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
                writer.writeheader()
                for job in data['jobs']:
                    writer.writerow({k: ("'" + job[k] if isinstance(job.get(k), str) and job[k].lstrip().startswith(('=', '+', '-', '@')) else job.get(k)) for k in fields})
            return {'output': str(output), 'rows': len(data['jobs'])}
        if command == 'rank':
            raw = json_read(Path(args.input))
            require(isinstance(raw, list) and raw, 'Input must be a non-empty JSON list')
            incoming = [validate_job_input(j) for j in raw]
            results = []
            for item in incoming:
                old = next((j for j in data['jobs'] if j['id'] == item['id']), None)
                if old is None:
                    old = {'status': 'ranked', 'applied_on': None, 'applied_revision': None, 'events': [], 'revisions': []}
                    data['jobs'].append(old)
                old.update(item)
                results.append(old)
            result = {'jobs': results}
        else:
            job = select(data, args.job)
            if command == 'prepare':
                result = prepare(workspace, job, args.request_id)
            elif command == 'ready':
                rev = revision(job, args.revision)
                require(rev['version'] != job.get('applied_revision'), 'Submitted revision is immutable')
                rev['sha256'] = material_checks(workspace, rev)
                rev['ready'] = True
                if job['applied_on'] is None:
                    job['status'] = 'prepared'
                result = {'status': job['status'], 'note': 'Files present; this does not certify content, rendering, or human approval.'}
            elif command == 'applied':
                require(args.confirmed, 'Record only after the user confirms actual submission; pass --confirmed')
                submitted = iso(args.date).isoformat()
                require(iso(submitted) <= date.today(), 'Submission cannot be in the future')
                rev = revision(job, args.revision)
                require(rev['ready'], 'Prepare materials before recording submission')
                require(rev.get('sha256') == material_checks(workspace, rev), 'Materials changed since ready; review changes and run ready again')
                if job['applied_on']:
                    require(job['applied_on'] == submitted and job['applied_revision'] == args.revision, 'Already submitted; preserve the original application')
                else:
                    job.update(status='applied', applied_on=submitted, applied_revision=args.revision)
                    job['events'].append({'id': 'submission', 'kind': 'applied', 'date': submitted, 'note': ''})
                result = {'status': job['status'], 'applied_revision': job['applied_revision']}
            elif command == 'event':
                require(job['applied_on'], 'Only submitted jobs can have application events')
                event_date = iso(args.date).isoformat()
                require(iso(job['applied_on']) <= iso(event_date) <= date.today(), 'Event date must be between submission and today')
                clean_text(args.event_id, 'event-id', True)
                require(args.event_id != 'submission', 'Reserved event ID')
                event = {'id': args.event_id, 'kind': args.kind, 'date': event_date, 'note': args.note}
                old = next((e for e in job['events'] if e['id'] == args.event_id), None)
                if old:
                    require(old == event, 'Event ID already exists with different content')
                else:
                    if args.kind == 'followup_sent':
                        require(args.confirmed, 'Drafting is not sending; pass --confirmed only after actual sending')
                        require(job['status'] in ACTIVE, 'Application is not active')
                        require(sum(e['kind'] == 'followup_sent' for e in job['events']) < 2, 'Two followups already recorded')
                    job['events'].append(event)
                    if args.kind in STATES:
                        states = [e for e in job['events'] if e['kind'] in STATES]
                        job['status'] = sorted(states, key=lambda e: e['date'])[-1]['kind']
                result = {'status': job['status'], 'event': event}
            else:
                raise ValueError('Unknown command')
        json_write(workspace / 'jobs.json', data)
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, help='Explicit user data directory outside the installed skill')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    rank = sub.add_parser('rank')
    rank.add_argument('--input', required=True)
    for command in ('list', 'followups'):
        p = sub.add_parser(command)
        p.add_argument('--today', default=date.today().isoformat())
        if command == 'list':
            p.add_argument('--actionable', action='store_true')
        else:
            p.add_argument('--days', type=int, default=10)
    export = sub.add_parser('export')
    export.add_argument('--output', required=True)
    for command in ('prepare', 'ready', 'applied', 'event'):
        p = sub.add_parser(command)
        p.add_argument('--job', required=True)
        if command == 'prepare':
            p.add_argument('--request-id', required=True)
        if command in {'ready', 'applied'}:
            p.add_argument('--revision', required=True)
        if command in {'applied', 'event'}:
            p.add_argument('--date', required=True)
            p.add_argument('--confirmed', action='store_true')
        if command == 'event':
            p.add_argument('--kind', choices=sorted(KINDS), required=True)
            p.add_argument('--event-id', required=True)
            p.add_argument('--note', default='')
    args = parser.parse_args()
    try:
        print(json.dumps(run(args), ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
