"""No-PHP and stub-command regression checks for read-only inventory."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from libs.app.php_manager.discovery import _sections, candidate_binaries, discover_php, inspect_cli


class PHPDiscoveryTests(unittest.TestCase):
    def test_sections(self):
        self.assertEqual(_sections("[PHP Modules]\njson\n[Zend Modules]\nOPcache\n"),
                         {"PHP Modules": ["json"], "Zend Modules": ["OPcache"]})

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("libs.app.php_manager.discovery.shutil.which", return_value=None):
                self.assertEqual(candidate_binaries([directory]), [])
                self.assertEqual(discover_php([directory])["installations"], [])

    def test_bad_executable_returns_error(self):
        observed = inspect_cli("/path/that/is/not/a/php/binary")
        self.assertIn("error", observed)
        self.assertEqual(observed["sapi"], "cli")

    def test_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "php8.2"
            p.write_text("not an executable", encoding="utf-8")
            with patch("libs.app.php_manager.discovery.shutil.which", return_value=None):
                self.assertEqual(candidate_binaries([directory]), [str(p)])


if __name__ == "__main__":
    unittest.main()
