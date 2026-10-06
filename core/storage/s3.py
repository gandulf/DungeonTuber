"""S3 compatible backend (AWS S3, Cloudflare R2, Backblaze B2, MinIO, Tigris, ...). Needs the optional ``boto3`` extra."""
from __future__ import annotations

import io
from datetime import timezone
from typing import Any, BinaryIO, Iterator

from core.storage.base import AlreadyExists, InvalidPath, NotFound, Storage, StorageEntry, normalize

CHUNK = 1024 * 1024


def _is_missing(error: Exception) -> bool:
    response = getattr(error, "response", None) or {}
    code = str(response.get("Error", {}).get("Code", ""))
    return code in ("404", "NoSuchKey", "NotFound") or response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404


class S3Storage(Storage):
    type = "s3"

    def __init__(self, bucket: str, prefix: str = "", endpoint_url: str | None = None, region: str | None = None,
                 access_key: str | None = None, secret_key: str | None = None, name: str = "", client: Any = None,
                 public_endpoint_url: str | None = None, signer: Any = None):
        """``client`` is a boto3 S3 client; created from the other arguments when omitted (tests inject a fake).

        ``public_endpoint_url`` is the address browsers reach the storage at when it differs from ``endpoint_url`` (e.g. a docker
        service name vs. localhost); direct streaming URLs are signed for it. ``signer`` overrides the client that signs them.
        """
        super().__init__(name or bucket)
        self.bucket = bucket
        self.prefix = normalize(prefix)
        if client is None:
            try:
                import boto3
                from botocore.config import Config
            except ImportError as e:
                raise RuntimeError("S3 storage needs boto3: pip install DungeonTuber[s3]") from e

            def make_client(endpoint: str | None):
                # path style addressing works with every S3 compatible service and does not need DNS entries for buckets
                # boto3 >= 1.36 adds checksum headers to every request by default, which Cloudflare R2, Backblaze B2 and other
                # S3 compatible services reject; only send them where an operation requires them
                config = Config(signature_version="s3v4", retries={"max_attempts": 4}, s3={"addressing_style": "path"} if endpoint else None,
                                request_checksum_calculation="when_required", response_checksum_validation="when_required")
                return boto3.client("s3", endpoint_url=endpoint or None, region_name=region or None, aws_access_key_id=access_key or None,
                                    aws_secret_access_key=secret_key or None, config=config)

            client = make_client(endpoint_url)
            if signer is None and public_endpoint_url and public_endpoint_url != endpoint_url:
                signer = make_client(public_endpoint_url)
        self.client = client
        self._signer = signer or client

    # --- keys ------------------------------------------------------------

    def key(self, path: str) -> str:
        path = normalize(path)
        return f"{self.prefix}/{path}".strip("/") if self.prefix else path

    def _path(self, key: str) -> str:
        return key[len(self.prefix):].strip("/") if self.prefix else key.strip("/")

    def _dir_prefix(self, path: str) -> str:
        key = self.key(path)
        return key + "/" if key else ""

    def _head(self, key: str) -> dict | None:
        try:
            return self.client.head_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            if _is_missing(e):
                return None
            raise

    def _pages(self, **kwargs) -> Iterator[dict]:
        token = None
        while True:
            args = dict(Bucket=self.bucket, **kwargs)
            if token:
                args["ContinuationToken"] = token
            page = self.client.list_objects_v2(**args)
            yield page
            if not page.get("IsTruncated"):
                return
            token = page.get("NextContinuationToken")

    def _dir_exists(self, path: str) -> bool:
        prefix = self._dir_prefix(path)
        if not prefix:
            return True  # root
        return any(page.get("KeyCount", 0) > 0 or page.get("Contents") for page in self._pages(Prefix=prefix, MaxKeys=1))

    # --- queries ---------------------------------------------------------

    def stat(self, path: str) -> StorageEntry:
        path = normalize(path)
        if not path:
            return StorageEntry("", True)
        head = self._head(self.key(path))
        if head is not None:
            return StorageEntry(path, False, int(head.get("ContentLength", 0)), _timestamp(head.get("LastModified")))
        if self._dir_exists(path):
            return StorageEntry(path, True)
        raise NotFound(path)

    def list(self, path: str = "") -> list[StorageEntry]:
        path = normalize(path)
        prefix = self._dir_prefix(path)
        entries = []
        for page in self._pages(Prefix=prefix, Delimiter="/"):
            for common in page.get("CommonPrefixes", []):
                entries.append(StorageEntry(self._path(common["Prefix"]), True))
            for obj in page.get("Contents", []):
                if obj["Key"] == prefix or obj["Key"].endswith("/"):
                    continue  # the "folder" placeholder object
                entries.append(StorageEntry(self._path(obj["Key"]), False, int(obj.get("Size", 0)), _timestamp(obj.get("LastModified"))))
        if not entries and path and not self._dir_exists(path):
            raise NotFound(path)
        return entries

    def walk(self, path: str = "") -> Iterator[StorageEntry]:
        """One flat listing instead of a request per folder."""
        prefix = self._dir_prefix(normalize(path))
        for page in self._pages(Prefix=prefix):
            for obj in page.get("Contents", []):
                if not obj["Key"].endswith("/"):
                    yield StorageEntry(self._path(obj["Key"]), False, int(obj.get("Size", 0)), _timestamp(obj.get("LastModified")))

    # --- reading ---------------------------------------------------------

    def read(self, path: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        args: dict[str, Any] = {"Bucket": self.bucket, "Key": self.key(path)}
        if start or end is not None:
            args["Range"] = f"bytes={start}-{'' if end is None else end}"
        try:
            body = self.client.get_object(**args)["Body"]
        except Exception as e:
            if _is_missing(e):
                raise NotFound(path)
            raise
        try:
            while chunk := body.read(CHUNK):
                yield chunk
        finally:
            body.close()

    def url(self, path: str, expires: int = 3600) -> str | None:
        return self._signer.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": self.key(path)}, ExpiresIn=expires)

    # --- writing ---------------------------------------------------------

    def write(self, path: str, data: BinaryIO | bytes, overwrite: bool = False):
        path = normalize(path)
        if not path:
            raise InvalidPath("Invalid path")
        key = self.key(path)
        if not overwrite and self._head(key) is not None:
            raise AlreadyExists(path)
        self.client.upload_fileobj(io.BytesIO(data) if isinstance(data, bytes) else data, self.bucket, key)

    def mkdir(self, path: str):
        path = normalize(path)
        if not path:
            raise InvalidPath("Invalid path")
        if self.exists(path):
            raise AlreadyExists(path)
        self.client.put_object(Bucket=self.bucket, Key=self._dir_prefix(path), Body=b"")

    def _keys(self, path: str) -> list[str]:
        """Every object key that makes up a file or a directory."""
        key = self.key(path)
        if self._head(key) is not None:
            return [key]
        keys = [obj["Key"] for page in self._pages(Prefix=key + "/") for obj in page.get("Contents", [])]
        if not keys:
            raise NotFound(path)
        return keys

    def delete(self, path: str):
        path = normalize(path)
        if not path:
            raise InvalidPath("Cannot delete the library root")
        keys = self._keys(path)
        for i in range(0, len(keys), 1000):
            self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]], "Quiet": True})

    def move(self, source: str, target: str):
        source, target = normalize(source), normalize(target)
        if not source or not target:
            raise InvalidPath("Invalid path")
        if target == source or target.startswith(source + "/"):
            raise InvalidPath("Cannot move a folder into itself")
        if self.exists(target):
            raise AlreadyExists(target)
        src_key, dst_key = self.key(source), self.key(target)
        keys = self._keys(source)
        for key in keys:
            new_key = dst_key if key == src_key else dst_key + key[len(src_key):]
            self.client.copy_object(Bucket=self.bucket, Key=new_key, CopySource={"Bucket": self.bucket, "Key": key})
        for i in range(0, len(keys), 1000):
            self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": [{"Key": k} for k in keys[i:i + 1000]], "Quiet": True})


def _timestamp(value) -> float:
    """Whole seconds: HEAD responses only have second precision while listings have milliseconds."""
    if value is None:
        return 0.0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return float(int(value.timestamp()))
