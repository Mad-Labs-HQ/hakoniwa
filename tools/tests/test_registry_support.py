"""Falsify accidental widening of the disposable registry transformation."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import tomllib

from tools.registry_support import NAME, VERSION, check_lock, registry_manifest
from tools.run_registry import freeze_product


class RegistrySupportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = """[package]
name = "sandbox-fixture"
[target.'cfg(target_os = "linux")'.dependencies]
hakoniwa = { package = "mad-hakoniwa", path = "../../../mad-hakoniwa/hakoniwa", version = "=1.8.0-mad.1", features = ["landlock"] }
other = "1"
"""

    def test_only_dependency_source_changes(self) -> None:
        before = tomllib.loads(self.text)
        expected = copy.deepcopy(before)
        dependency = expected["target"]['cfg(target_os = "linux")']["dependencies"][
            "hakoniwa"
        ]
        del dependency["path"]
        dependency["registry"] = "review"
        self.assertEqual(tomllib.loads(registry_manifest(self.text)), expected)

    def test_refuse_version_feature_or_declaration_drift(self) -> None:
        for text in (
            self.text.replace(VERSION, "2.0.0-mad.1"),
            self.text.replace('["landlock"]', "[]"),
            self.text.replace("path = ", "git = "),
        ):
            with self.assertRaises(ValueError):
                registry_manifest(text)

    def test_lock_allows_only_fork_source_and_checksum(self) -> None:
        before = f'''version = 4
[[package]]
name = "{NAME}"
version = "{VERSION}"
dependencies = ["libc"]
[[package]]
name = "libc"
version = "0.2.186"
'''
        registry = "sparse+http://127.0.0.1:1234/index/"
        after = before.replace(
            'dependencies = ["libc"]',
            'dependencies = ["libc"]\nsource = "registry+'
            + registry
            + '"\nchecksum = "abc"',
        )
        check_lock(before, after, registry, "abc")
        check_lock(
            before, after.replace("registry+sparse+", "sparse+"), registry, "abc"
        )
        for text in (
            after.replace("0.2.186", "0.2.187"),
            after.replace("abc", "bad"),
            after.replace(VERSION, "2.0.0-mad.1"),
        ):
            with self.assertRaises(ValueError):
                check_lock(before, text, registry, "abc")


class ProductSnapshotTests(unittest.TestCase):
    def test_internal_license_link_is_copied_as_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            (repo / "crates/item").mkdir(parents=True)
            (repo / "LICENSE").write_text("original license")
            (repo / "crates/item/LICENSE").symlink_to("../../LICENSE")
            with patch(
                "tools.run_registry.subprocess.check_output",
                return_value=b"LICENSE\0crates/item/LICENSE\0",
            ):
                freeze_product(repo, root / "snapshot")
            self.assertEqual(
                (root / "snapshot/crates/item/LICENSE").read_text(), "original license"
            )
            self.assertFalse((root / "snapshot/crates/item/LICENSE").is_symlink())

    def test_external_symlink_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            (root / "outside").write_text("external")
            (repo / "LICENSE").symlink_to("../outside")
            with (
                patch(
                    "tools.run_registry.subprocess.check_output",
                    return_value=b"LICENSE\0",
                ),
                self.assertRaisesRegex(ValueError, "escapes"),
            ):
                freeze_product(repo, root / "snapshot")


if __name__ == "__main__":
    unittest.main()
