"""Export tests: unlisted private files and old Git history must not ship."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('build_release', ROOT / 'tools/build_release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.source = self.base / 'source'
        self.source.mkdir()
        self.output = self.base / 'export'

    def test_exports_only_manifest_even_when_private_files_and_history_exist(self):
        (self.source / 'README.md').write_text('Public example')
        (self.source / 'profile.md').write_text('SYNTHETIC PRIVATE CANARY')
        (self.source / '.git').mkdir()
        (self.source / '.git/HEAD').write_text('private-history')
        (self.source / 'release-files.txt').write_text('README.md\nrelease-files.txt\n')
        result = release.build(self.source, self.output)
        self.assertEqual(result['file_count'], 2)
        self.assertEqual(sorted(p.name for p in self.output.iterdir()), ['README.md', 'release-files.txt'])
        self.assertNotIn('PRIVATE', (self.output / 'README.md').read_text())

    def test_rejects_escape_symlink_and_history_before_creating_output(self):
        for entry in ['../secret', '.git/HEAD', '/absolute-secret']:
            (self.source / 'release-files.txt').write_text(entry)
            with self.assertRaises(ValueError):
                release.build(self.source, self.output)
            self.assertFalse(self.output.exists())
        (self.base / 'secret').write_text('private')
        (self.source / 'linked').symlink_to(self.base / 'secret')
        (self.source / 'release-files.txt').write_text('linked')
        with self.assertRaises(ValueError):
            release.build(self.source, self.output)

    def test_refuses_to_overwrite_existing_release(self):
        self.output.mkdir()
        (self.output / 'keep').write_text('preserve')
        with self.assertRaises(ValueError):
            release.build(self.source, self.output)
        self.assertEqual((self.output / 'keep').read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()
