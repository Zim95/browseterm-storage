"""
Tests for MinioStorage implementation.

MinioStorage imports ``from minio import Minio`` inside ``__init__`` and builds a
``minio.Minio`` client. These tests avoid any real network/minio dependency by
installing a stub ``minio`` module into ``sys.modules`` (so the tests run even
when the ``minio`` package is not installed) and patching ``minio.Minio`` with a
mock for each test.
"""
import os
import sys
import shutil
import tempfile
import types
import unittest
from unittest.mock import patch, MagicMock

# Ensure a ``minio`` module exists so that ``from minio import Minio`` succeeds
# and ``patch('minio.Minio')`` has a target, even without the real package.
if "minio" not in sys.modules:
    _stub_minio = types.ModuleType("minio")
    _stub_minio.Minio = MagicMock(name="Minio")
    sys.modules["minio"] = _stub_minio

from browseterm_storage.storage import get_storage, StorageLayer


def _valid_config():
    return {
        "minio_endpoint": "minio.example.com:9000",
        "minio_access_key": "access-key",
        "minio_secret_key": "secret-key",
        "minio_bucket": "snapshots",
        "minio_secure": True,
    }


class TestMinioStorage(unittest.TestCase):
    """Test cases for MinioStorage class."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        # Patch the Minio client class; the constructor returns our mock client.
        self.minio_patcher = patch("minio.Minio")
        self.mock_minio_cls = self.minio_patcher.start()
        self.mock_client = MagicMock(name="minio_client")
        self.mock_minio_cls.return_value = self.mock_client

    def tearDown(self):
        self.minio_patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_storage_builds_client_with_right_args(self):
        """get_storage(MINIO, config) should construct Minio with the config args."""
        config = _valid_config()
        storage = get_storage(StorageLayer.MINIO, config)

        self.mock_minio_cls.assert_called_once_with(
            "minio.example.com:9000",
            access_key="access-key",
            secret_key="secret-key",
            secure=True,
        )
        self.assertEqual(storage.bucket, "snapshots")
        self.assertIs(storage.client, self.mock_client)

    def test_snapshot_path_structure(self):
        """snapshot_path should return the <ns>/<cid>/fs_snapshot_<ts>.tar.gz key."""
        storage = get_storage(StorageLayer.MINIO, _valid_config())

        path = storage.snapshot_path("my-ns", "container-xyz", "ts")

        self.assertEqual(path, "my-ns/container-xyz/fs_snapshot_ts.tar.gz")

    def test_read_calls_get_object(self):
        """read() should call client.get_object and return the response bytes."""
        storage = get_storage(StorageLayer.MINIO, _valid_config())

        response = MagicMock()
        response.read.return_value = b"snapshot-bytes"
        self.mock_client.get_object.return_value = response

        data = storage.read("my-ns/cid/fs_snapshot_ts.tar.gz")

        self.mock_client.get_object.assert_called_once_with(
            "snapshots", "my-ns/cid/fs_snapshot_ts.tar.gz"
        )
        self.assertEqual(data, b"snapshot-bytes")
        response.close.assert_called_once()

    def test_write_calls_put_object(self):
        """write() should call client.put_object with bucket, path, a stream, and length."""
        storage = get_storage(StorageLayer.MINIO, _valid_config())

        payload = b"hello world"
        storage.write("my-ns/cid/fs_snapshot_ts.tar.gz", payload)

        self.assertEqual(self.mock_client.put_object.call_count, 1)
        args, kwargs = self.mock_client.put_object.call_args
        self.assertEqual(args[0], "snapshots")
        self.assertEqual(args[1], "my-ns/cid/fs_snapshot_ts.tar.gz")
        self.assertEqual(kwargs.get("length"), len(payload))

    def test_write_encodes_string(self):
        """write() should encode str data before uploading (length in bytes)."""
        storage = get_storage(StorageLayer.MINIO, _valid_config())

        storage.write("key", "abc")

        _args, kwargs = self.mock_client.put_object.call_args
        self.assertEqual(kwargs.get("length"), len("abc".encode("utf-8")))

    def test_localize_calls_fget_object_and_returns_local_path(self):
        """localize() should download via fget_object to dest_dir/basename and return it."""
        storage = get_storage(StorageLayer.MINIO, _valid_config())

        dest_dir = os.path.join(self.temp_dir, "downloads")
        remote_key = "my-ns/cid/fs_snapshot_ts.tar.gz"

        result = storage.localize(remote_key, dest_dir)

        expected_local = os.path.join(dest_dir, "fs_snapshot_ts.tar.gz")
        self.mock_client.fget_object.assert_called_once_with(
            "snapshots", remote_key, expected_local
        )
        self.assertEqual(result, expected_local)
        # localize creates the destination directory.
        self.assertTrue(os.path.isdir(dest_dir))

    def test_missing_config_raises_value_error(self):
        """Missing required MinIO configuration should raise ValueError."""
        config = _valid_config()
        config["minio_bucket"] = None

        with self.assertRaises(ValueError):
            get_storage(StorageLayer.MINIO, config)


if __name__ == "__main__":
    unittest.main()
