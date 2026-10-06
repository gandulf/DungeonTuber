"""In-memory stand-in for the boto3 S3 client used by the storage tests."""
import io
from datetime import datetime, timezone


class _NoSuchKey(Exception):
    response = {"Error": {"Code": "404"}}


class FakeS3Client:
    """The subset of the boto3 S3 client used by S3Storage."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise _NoSuchKey()
        return {"ContentLength": len(self.objects[Key]), "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc)}

    def get_object(self, Bucket, Key, Range=None):
        if Key not in self.objects:
            raise _NoSuchKey()
        data = self.objects[Key]
        if Range:
            start, _, end = Range.removeprefix("bytes=").partition("-")
            data = data[int(start):(int(end) + 1) if end else None]
        return {"Body": io.BytesIO(data)}

    def upload_fileobj(self, fileobj, Bucket, Key):
        self.objects[Key] = fileobj.read()

    def put_object(self, Bucket, Key, Body):
        self.objects[Key] = Body

    def copy_object(self, Bucket, Key, CopySource):
        self.objects[Key] = self.objects[CopySource["Key"]]

    def delete_objects(self, Bucket, Delete):
        for item in Delete["Objects"]:
            self.objects.pop(item["Key"], None)

    def generate_presigned_url(self, op, Params, ExpiresIn):
        return f"https://example.test/{Params['Bucket']}/{Params['Key']}?expires={ExpiresIn}"

    def list_objects_v2(self, Bucket, Prefix="", Delimiter=None, MaxKeys=2, ContinuationToken=None):
        keys = sorted(k for k in self.objects if k.startswith(Prefix))
        prefixes, contents = [], []
        for key in keys:
            rest = key[len(Prefix):]
            if Delimiter and Delimiter in rest:
                common = Prefix + rest.split(Delimiter)[0] + Delimiter
                if common not in prefixes:
                    prefixes.append(common)
            else:
                contents.append({"Key": key, "Size": len(self.objects[key]), "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc)})
        # paginate the contents to exercise continuation tokens
        offset = int(ContinuationToken or 0)
        page = contents[offset:offset + 2]
        truncated = offset + 2 < len(contents)
        return {"CommonPrefixes": [{"Prefix": p} for p in prefixes] if not offset else [], "Contents": page, "KeyCount": len(page) + len(prefixes),
                "IsTruncated": truncated, "NextContinuationToken": str(offset + 2) if truncated else None}
