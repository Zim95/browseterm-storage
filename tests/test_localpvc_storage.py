"""
Tests for LocalPVCStorage implementation.
"""
import unittest
import tempfile
import shutil
from pathlib import Path

from browseterm_storage.storage import get_storage, StorageLayer


class TestLocalPVCStorage(unittest.TestCase):
    """Test cases for LocalPVCStorage class."""

    def setUp(self):
        """Create a temporary directory for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.storage = get_storage(StorageLayer.LOCAL, {'snapshot_dir': self.temp_dir})

    def tearDown(self):
        """Clean up the temporary directory."""
        shutil.rmtree(self.temp_dir)

    def test_write_and_read_bytes(self):
        """Test writing and reading bytes data."""
        namespace = "test-namespace"
        container_id = "test-container-123"
        test_data = b"This is test data for snapshot"
        
        # Get the expected path
        timestamp = "ts"
        expected_path = self.storage.snapshot_path(namespace, container_id, timestamp)
        
        # Write data
        self.storage.write(expected_path, test_data)
        
        # Verify file exists
        self.assertTrue(Path(expected_path).exists(), f"File should exist at {expected_path}")
        
        # Read data back
        read_data = self.storage.read(expected_path)
        
        # Verify data matches
        self.assertEqual(test_data, read_data)

    def test_write_and_read_string(self):
        """Test writing and reading string data."""
        namespace = "test-namespace"
        container_id = "test-container-456"
        test_data = "This is test string data"
        
        # Get the expected path
        timestamp = "ts"
        expected_path = self.storage.snapshot_path(namespace, container_id, timestamp)
        
        # Write string data
        self.storage.write(expected_path, test_data)
        
        # Verify file exists
        self.assertTrue(Path(expected_path).exists())
        
        # Read data back
        read_data = self.storage.read(expected_path)
        
        # Verify data matches (string should be encoded as bytes)
        self.assertEqual(test_data.encode("utf-8"), read_data)

    def test_snapshot_path_structure(self):
        """Test that snapshot_path creates proper directory structure."""
        namespace = "my-namespace"
        container_id = "container-xyz"
        
        timestamp = "ts"
        path = self.storage.snapshot_path(namespace, container_id, timestamp)
        
        # Verify path structure
        self.assertIn(namespace, path)
        self.assertIn(container_id, path)
        self.assertTrue(path.endswith(f"fs_snapshot_{timestamp}.tar.gz"))

    def test_write_creates_directories(self):
        """Test that write creates parent directories if they don't exist."""
        namespace = "deep-namespace"
        container_id = "deep-container"
        test_data = b"data in deep directories"
        
        timestamp = "ts"
        path = self.storage.snapshot_path(namespace, container_id, timestamp)
        
        # Verify directories don't exist yet
        self.assertFalse(Path(path).parent.exists())
        
        # Write data
        self.storage.write(path, test_data)
        
        # Verify directories were created
        self.assertTrue(Path(path).parent.exists())
        self.assertTrue(Path(path).exists())

    def test_read_nonexistent_file_raises_error(self):
        """Test that reading a nonexistent file raises FileNotFoundError."""
        nonexistent_path = f"{self.temp_dir}/nonexistent/file.tar.gz"
        
        with self.assertRaises(FileNotFoundError):
            self.storage.read(nonexistent_path)

    def test_multiple_snapshots_same_namespace(self):
        """Test writing multiple snapshots in the same namespace."""
        namespace = "multi-namespace"
        
        # Write first snapshot
        container_id_1 = "container-1"
        data_1 = b"Data for container 1"
        timestamp = "ts"
        path_1 = self.storage.snapshot_path(namespace, container_id_1, timestamp)
        self.storage.write(path_1, data_1)
        
        # Write second snapshot
        container_id_2 = "container-2"
        data_2 = b"Data for container 2"
        path_2 = self.storage.snapshot_path(namespace, container_id_2, timestamp)
        self.storage.write(path_2, data_2)
        
        # Verify both files exist and have correct data
        self.assertEqual(self.storage.read(path_1), data_1)
        self.assertEqual(self.storage.read(path_2), data_2)

    def test_overwrite_existing_file(self):
        """Test overwriting an existing file."""
        namespace = "test-namespace"
        container_id = "test-container"
        timestamp = "ts"
        path = self.storage.snapshot_path(namespace, container_id, timestamp)
        
        # Write initial data
        initial_data = b"Initial data"
        self.storage.write(path, initial_data)
        
        # Overwrite with new data
        new_data = b"Updated data"
        self.storage.write(path, new_data)
        
        # Verify new data is present
        self.assertEqual(self.storage.read(path), new_data)


if __name__ == "__main__":
    unittest.main()
