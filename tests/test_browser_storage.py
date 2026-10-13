import os
import subprocess
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


class BrowserStorageArchitectureTests(unittest.TestCase):
    def test_app_contains_no_sqlite_database_module_or_import(self):
        app = PROJECT / 'app'
        self.assertFalse((app / 'db.py').exists(), 'SQLite-backed app/db.py should be removed')
        for path in app.rglob('*.py'):
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('sqlite3', text, str(path))
            self.assertNotIn('from app.db', text, str(path))

    def test_indexeddb_store_is_present_and_named(self):
        source = (app_path := PROJECT / 'app' / 'static' / 'js' / 'arc-store.js').read_text(encoding='utf-8')
        self.assertIn("const DB_NAME = 'arc-workspace'", source)
        self.assertIn("indexedDB.open(DB_NAME, DB_VERSION)", source)
        self.assertIn("createObjectStore('analyses'", source)
        self.assertIn("createObjectStore('discoveries'", source)
        self.assertIn("createObjectStore('insights'", source)
        self.assertIn('allInsights:', source)
        self.assertTrue(app_path.exists())

    def test_app_imports_on_vercel_without_any_database_path(self):
        env = os.environ.copy()
        env.pop('ARC_DB_PATH', None)
        env.pop('ARC_SERVERLESS_DB_PATH', None)
        env['PYTHONPATH'] = str(PROJECT)
        env['VERCEL'] = '1'
        env['GEMINI_API_KEY'] = 'unit-test'
        env['QLOO_API_KEY'] = 'unit-test'
        env['ARC_SESSION_SECRET'] = 'test-session-secret'
        result = subprocess.run([sys.executable, '-c', 'import app.main; print(app.main.app.title)'], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Arc', result.stdout)


if __name__ == '__main__':
    unittest.main()
