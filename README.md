# browseterm-storage
Storage abstraction for Browseterm.

This library provides a small, backend-agnostic abstraction for reading and
writing container filesystem snapshots. Snapshots are stored as gzipped
tarballs named `fs_snapshot_<timestamp>.tar.gz`, organized by namespace and
container id.

## Overview

The core abstraction is `BrowsetermStorage` (an ABC). Every backend implements
three methods:

- `snapshot_path(namespace, container_id, timestamp) -> str` — build the
  storage path / object key for a snapshot.
- `read(path) -> bytes` — read snapshot bytes from storage.
- `write(path, data) -> None` — write snapshot bytes (or a `str`) to storage.

Backends are selected via the `StorageLayer` enum and constructed through the
`get_storage()` factory.

## Backends

Two backends are available:

### `LocalPVCStorage` (`StorageLayer.LOCAL`)

Stores snapshots on a local filesystem path (intended to be a mounted PVC).
Snapshots are written to:

```
<snapshot_dir>/<namespace>/<container_id>/fs_snapshot_<timestamp>.tar.gz
```

Config (`LocalPVCStorageConfig`):

- `snapshot_dir` — root directory where snapshots are stored.

### `MinioStorage` (`StorageLayer.MINIO`)

Stores snapshots as objects in a MinIO (S3-compatible) bucket using the object
key:

```
<namespace>/<container_id>/fs_snapshot_<timestamp>.tar.gz
```

Config (`MinioStorageConfig`):

- `minio_endpoint` — MinIO endpoint (host:port).
- `minio_access_key` — access key.
- `minio_secret_key` — secret key.
- `minio_bucket` — target bucket.
- `minio_secure` — whether to use TLS (defaults to `False`).

All four of endpoint/access key/secret key/bucket are required; a
`ValueError` is raised if any are missing. This backend requires the `minio`
package to be installed.

> Note: MinIO infrastructure is not yet deployed, so `LOCAL` is the default
> backend today.

## Usage

Select a backend and build it with the `get_storage()` factory, passing the
backend config as a plain `dict`:

```python
from browseterm_storage.storage import StorageLayer, get_storage

# Local backend (default)
storage = get_storage(StorageLayer.LOCAL, {"snapshot_dir": "/data/snapshots"})

# MinIO backend
storage = get_storage(
    StorageLayer.MINIO,
    {
        "minio_endpoint": "minio:9000",
        "minio_access_key": "...",
        "minio_secret_key": "...",
        "minio_bucket": "browseterm-snapshots",
        "minio_secure": False,
    },
)

path = storage.snapshot_path("my-namespace", "container-123", "20260718T000000")
storage.write(path, tarball_bytes)
data = storage.read(path)
```

## Who uses it

- **container-maker** writes filesystem snapshot tarballs to storage.
- **snapshot_job** reads those tarballs back from storage.

## Installation

```bash
$ poetry install
```

Or add it as a dependency of another project:

```bash
$ poetry add git+https://github.com/Zim95/browseterm-storage.git#main
```

## Running tests

Tests use Python's built-in `unittest` framework and live under `tests/`.
They are pure unit tests — the MinIO client is mocked — so no live MinIO or
other infrastructure is required to run them.

First install the package and its dependencies into a virtual environment:

```bash
$ pip install -e .
```

Run all tests:

```bash
$ python -m unittest discover -s tests -p "test_*.py"
```

Run a single test module:

```bash
$ python -m unittest tests.test_minio_storage
```
