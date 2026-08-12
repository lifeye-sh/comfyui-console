"""对象存储抽象与本地文件系统实现。"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod


class StorageProvider(ABC):
    @abstractmethod
    def save_bytes(self, data: bytes, key: str) -> str: ...

    @abstractmethod
    def read(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def abs_path(self, key: str) -> str: ...


class LocalFSStorage(StorageProvider):
    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(root)
        os.makedirs(self.root, exist_ok=True)

    def save_bytes(self, data: bytes, key: str) -> str:
        path = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return key

    def read(self, key: str) -> bytes:
        with open(os.path.join(self.root, key), "rb") as f:
            return f.read()

    def exists(self, key: str) -> bool:
        return os.path.exists(os.path.join(self.root, key))

    def delete(self, key: str) -> None:
        path = os.path.join(self.root, key)
        if os.path.exists(path):
            os.remove(path)

    def abs_path(self, key: str) -> str:
        return os.path.join(self.root, key)


storage: StorageProvider | None = None


def get_storage() -> StorageProvider:
    global storage
    if storage is None:
        from app.config import settings
        storage = LocalFSStorage(settings.storage_path)
    return storage