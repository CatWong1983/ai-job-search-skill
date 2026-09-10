#!/usr/bin/env python3
"""Export reviewed files into a new directory without repository history or user data."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys


def build(source, output):
    source = source.resolve()
    output = output.resolve()
    if output.exists() or output.is_relative_to(source):
        raise ValueError('Output must be a new directory outside the source repository')
    manifest = source / 'release-files.txt'
    if manifest.is_symlink():
        raise ValueError('Symlink manifest is not allowed')
    entries = [line.strip() for line in manifest.read_text(encoding='utf-8').splitlines()
               if line.strip() and not line.lstrip().startswith('#')]
    if not entries or len(entries) != len(set(entries)):
        raise ValueError('Manifest must contain unique file paths')
    files = []
    for entry in entries:
        relative = PurePosixPath(entry)
        if relative.is_absolute() or '..' in relative.parts or '\\' in entry or '.git' in relative.parts:
            raise ValueError('Unsafe manifest path')
        path = source.joinpath(*relative.parts)
        if not path.resolve().is_relative_to(source) or not path.is_file():
            raise ValueError('Missing or escaping manifest file')
        if any(p.is_symlink() for p in [path, *path.parents] if p != source and source in p.parents):
            raise ValueError('Symlink files are not allowed')
        files.append((entry, path))
    output.mkdir(parents=True)
    hashes = {}
    for entry, path in files:
        target = output / entry
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        hashes[entry] = hashlib.sha256(target.read_bytes()).hexdigest()
    return {'output': str(output), 'file_count': len(files), 'sha256': hashes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(Path(__file__).resolve().parents[1], args.output), indent=2))
    except (ValueError, OSError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
