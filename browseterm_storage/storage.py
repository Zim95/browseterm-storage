from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class StorageLayer(str, Enum):
    LOCAL = "local"
    MINIO = "minio"


@dataclass
class StorageConfig:
    pass


@dataclass
class LocalPVCStorageConfig(StorageConfig):
    snapshot_dir: str


@dataclass
class MinioStorageConfig(StorageConfig):
    minio_endpoint: str | None = None
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    minio_bucket: str | None = None
    minio_secure: bool = False


class BrowsetermStorage(ABC):
    def __init__(self, config: StorageConfig) -> None:
        self.config = config

    @abstractmethod
    def snapshot_path(self, namespace: str, container_id: str, timestamp: str) -> str:
        """Return storage path or object key."""
        pass

    @abstractmethod
    def read(self, path: str) -> bytes:
        """Read data from storage."""
        pass

    @abstractmethod
    def write(self, path: str, data: bytes | str) -> None:
        """Write data to storage."""
        pass

    @abstractmethod
    def localize(self, path: str, dest_dir: str) -> str:
        """Ensure the object at `path` is available as a local file and return its local
        filesystem path. Local backends return the path as-is; remote backends download it."""
        pass


class LocalPVCStorage(BrowsetermStorage):
    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config)
        self.root = config.snapshot_dir

    def snapshot_path(self, namespace: str, container_id: str, timestamp: str) -> str:
        return os.path.join(
            self.root,
            namespace,
            container_id,
            f"fs_snapshot_{timestamp}.tar.gz",
        )

    def read(self, path: str) -> bytes:
        try:
            with open(path, "rb") as f:
                return f.read()
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Snapshot not found at {path}") from e
        except Exception as e:
            raise IOError(f"Failed to read from {path}: {e}") from e

    def write(self, path: str, data: bytes | str) -> None:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)

            if isinstance(data, str):
                data = data.encode("utf-8")

            with open(path, "wb") as f:
                f.write(data)

        except Exception as e:
            raise IOError(f"Failed to write to {path}: {e}") from e

    def localize(self, path: str, dest_dir: str) -> str:
        # Snapshot already lives on the shared PVC; return the path as-is.
        return path


class MinioStorage(BrowsetermStorage):
    def __init__(self, config: StorageConfig) -> None:
        super().__init__(config)

        required = {
            "MINIO_ENDPOINT": config.minio_endpoint,
            "MINIO_ACCESS_KEY": config.minio_access_key,
            "MINIO_SECRET_KEY": config.minio_secret_key,
            "MINIO_BUCKET": config.minio_bucket,
        }

        missing = [k for k, v in required.items() if not v]
        if missing:
            raise ValueError(f"Missing MinIO configuration: {', '.join(missing)}")

        try:
            from minio import Minio
        except ImportError:
            raise ImportError(
                "minio package required for MinIO storage. Install with: pip install minio"
            )

        self.bucket = config.minio_bucket

        self.client = Minio(
            config.minio_endpoint,
            access_key=config.minio_access_key,
            secret_key=config.minio_secret_key,
            secure=config.minio_secure,
        )

    def snapshot_path(self, namespace: str, container_id: str, timestamp: str) -> str:
        return f"{namespace}/{container_id}/fs_snapshot_{timestamp}.tar.gz"

    def read(self, path: str) -> bytes:
        try:
            response = self.client.get_object(self.bucket, path)
            data = response.read()
            response.close()
            return data
        except Exception as e:
            raise IOError(f"Failed to read from MinIO {path}: {e}") from e

    def write(self, path: str, data: bytes | str) -> None:
        try:
            if isinstance(data, str):
                data = data.encode("utf-8")

            from io import BytesIO

            self.client.put_object(
                self.bucket,
                path,
                BytesIO(data),
                length=len(data),
            )
        except Exception as e:
            raise IOError(f"Failed to write to MinIO {path}: {e}") from e

    def localize(self, path: str, dest_dir: str) -> str:
        try:
            os.makedirs(dest_dir, exist_ok=True)
            local_path = os.path.join(dest_dir, os.path.basename(path))
            # fget_object streams to disk (no full in-memory load, unlike read()).
            self.client.fget_object(self.bucket, path, local_path)
            return local_path
        except Exception as e:
            raise IOError(f"Failed to download from MinIO {path}: {e}") from e


def get_storage(storage_layer: StorageLayer, config: dict) -> BrowsetermStorage:
    cfg_storage_config_map = {
        StorageLayer.LOCAL: LocalPVCStorageConfig,
        StorageLayer.MINIO: MinioStorageConfig
    }
    storage_config: StorageConfig = cfg_storage_config_map.get(storage_layer)
    if storage_config is None:
        raise ValueError(f"Unsupported STORAGE_LAYER: {cfg.layer}")
    cfg_storage_map = {
        StorageLayer.LOCAL: LocalPVCStorage,
        StorageLayer.MINIO: MinioStorage
    }
    storage_class: BrowsetermStorage = cfg_storage_map.get(storage_layer)
    if storage_class is None:
        raise ValueError(f"Unsupported STORAGE_LAYER: {cfg.layer}")
    return storage_class(storage_config(**config))
