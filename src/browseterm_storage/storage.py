from __future__ import annotations

import os
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol


class StorageLayer(str, Enum):
    LOCAL = "local"
    MINIO = "minio"


@dataclass(frozen=True)
class StorageConfig:
    layer: StorageLayer
    snapshot_dir: str = "/mnt/snapshot"
    minio_endpoint: str | None = None
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    minio_bucket: str | None = None
    minio_secure: bool = False

    @staticmethod
    def from_env() -> "StorageConfig":
        layer_value = os.getenv("STORAGE_LAYER", StorageLayer.LOCAL.value).lower()
        layer = StorageLayer(layer_value)
        snapshot_dir = os.getenv("SNAPSHOT_DIR", "/mnt/snapshot")
        return StorageConfig(
            layer=layer,
            snapshot_dir=snapshot_dir,
            minio_endpoint=os.getenv("MINIO_ENDPOINT"),
            minio_access_key=os.getenv("MINIO_ACCESS_KEY"),
            minio_secret_key=os.getenv("MINIO_SECRET_KEY"),
            minio_bucket=os.getenv("MINIO_BUCKET"),
            minio_secure=os.getenv("MINIO_SECURE", "false").lower() == "true",
        )


class StorageBackend(Protocol):
    def snapshot_path(self, namespace: str, container_id: str) -> str:
        ...


class BrowsetermStorage(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def snapshot_path(self, namespace: str, container_id: str) -> str:
        """Get the storage path/key for a snapshot."""
        pass

    @abstractmethod
    def read(self, path: str) -> bytes:
        """Read data from storage.
        
        Args:
            path: Storage path (local: file path, minio: object key)
        
        Returns:
            bytes: Data read from storage
        """
        pass

    @abstractmethod
    def write(self, path: str, data: bytes | str) -> None:
        """Write data to storage.
        
        Args:
            path: Storage path (local: file path, minio: object key)
            data: Data to write (bytes or string)
        """
        pass


class LocalPVCStorage(BrowsetermStorage):
    def __init__(self, snapshot_dir: str) -> None:
        self.snapshot_dir = snapshot_dir

    def snapshot_path(self, namespace: str, container_id: str) -> str:
        return os.path.join(self.snapshot_dir, namespace, container_id, "full_fs_snapshot.tar.gz")

    def read(self, path: str) -> bytes:
        """Read file from local PVC."""
        try:
            with open(path, "rb") as f:
                return f.read()
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Snapshot not found at {path}") from e
        except Exception as e:
            raise IOError(f"Failed to read from {path}: {e}") from e

    def write(self, path: str, data: bytes | str) -> None:
        """Write file to local PVC."""
        try:
            # Ensure directory exists
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            
            # Write data
            if isinstance(data, str):
                data = data.encode("utf-8")
            
            with open(path, "wb") as f:
                f.write(data)
        except Exception as e:
            raise IOError(f"Failed to write to {path}: {e}") from e


class MinioStorage(BrowsetermStorage):
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str, secure: bool = False) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.secure = secure
        self._client = None

    @property
    def client(self):
        """Lazy-load MinIO client."""
        if self._client is None:
            try:
                from minio import Minio
            except ImportError:
                raise ImportError("minio package required for MinIO storage. Install with: pip install minio")
            
            self._client = Minio(
                self.endpoint,
                access_key=self.access_key,
                secret_key=self.secret_key,
                secure=self.secure,
            )
        return self._client

    def snapshot_path(self, namespace: str, container_id: str) -> str:
        return f"{namespace}/{container_id}/full_fs_snapshot.tar.gz"

    def read(self, path: str) -> bytes:
        """Read object from MinIO."""
        try:
            response = self.client.get_object(self.bucket, path)
            data = response.read()
            response.close()
            return data
        except Exception as e:
            raise IOError(f"Failed to read from MinIO {path}: {e}") from e

    def write(self, path: str, data: bytes | str) -> None:
        """Write object to MinIO."""
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


def get_storage(config: StorageConfig | None = None) -> BrowsetermStorage:
    cfg = config or StorageConfig.from_env()

    if cfg.layer == StorageLayer.LOCAL:
        return LocalPVCStorage(snapshot_dir=cfg.snapshot_dir)

    if cfg.layer == StorageLayer.MINIO:
        missing = [
            name for name, value in {
                "MINIO_ENDPOINT": cfg.minio_endpoint,
                "MINIO_ACCESS_KEY": cfg.minio_access_key,
                "MINIO_SECRET_KEY": cfg.minio_secret_key,
                "MINIO_BUCKET": cfg.minio_bucket,
            }.items() if not value
        ]
        if missing:
            raise ValueError(f"Missing MinIO config: {', '.join(missing)}")
        return MinioStorage(
            endpoint=cfg.minio_endpoint,
            access_key=cfg.minio_access_key,
            secret_key=cfg.minio_secret_key,
            bucket=cfg.minio_bucket,
            secure=cfg.minio_secure,
        )

    raise ValueError(f"Unsupported STORAGE_LAYER: {cfg.layer}")
