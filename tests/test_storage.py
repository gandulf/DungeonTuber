"""Contract tests run against every storage backend (the S3 one against an in-memory fake client)."""
import io

import pytest

from core.storage import AlreadyExists, InvalidPath, LocalStorage, NotFound, create_storage, normalize
from core.storage.s3 import S3Storage
from fake_s3 import FakeS3Client


@pytest.fixture(params=["local", "s3"])
def storage(request, tmp_path):
    if request.param == "local":
        return LocalStorage(tmp_path / "library")
    return S3Storage("bucket", prefix="rpg", client=FakeS3Client())


def test_write_read_and_stat(storage):
    storage.write("Battle/Boss.mp3", b"0123456789")

    entry = storage.stat("Battle/Boss.mp3")
    assert (entry.is_dir, entry.size, entry.name) == (False, 10, "Boss.mp3")
    assert storage.stat("Battle").is_dir
    assert storage.read_bytes("Battle/Boss.mp3") == b"0123456789"
    assert b"".join(storage.read("Battle/Boss.mp3", 2, 5)) == b"2345"
    assert b"".join(storage.read("Battle/Boss.mp3", 7)) == b"789"


def test_write_does_not_overwrite_unless_asked(storage):
    storage.write("a.mp3", b"one")
    with pytest.raises(AlreadyExists):
        storage.write("a.mp3", b"two")
    storage.write("a.mp3", io.BytesIO(b"two"), overwrite=True)
    assert storage.read_bytes("a.mp3") == b"two"


def test_list_returns_direct_children_only(storage):
    for name in ("one.mp3", "two.mp3", "three.mp3", "Sub/deep.mp3", "Sub/Deeper/deepest.mp3"):
        storage.write(name, b"x")

    root = {(e.path, e.is_dir) for e in storage.list()}
    assert root == {("one.mp3", False), ("two.mp3", False), ("three.mp3", False), ("Sub", True)}
    assert {(e.path, e.is_dir) for e in storage.list("Sub")} == {("Sub/deep.mp3", False), ("Sub/Deeper", True)}


def test_walk_yields_all_files(storage):
    for name in ("a.mp3", "Sub/b.mp3", "Sub/Deeper/c.mp3"):
        storage.write(name, b"x")

    assert sorted(e.path for e in storage.walk()) == ["Sub/Deeper/c.mp3", "Sub/b.mp3", "a.mp3"]
    assert sorted(e.path for e in storage.walk("Sub")) == ["Sub/Deeper/c.mp3", "Sub/b.mp3"]


def test_mkdir_and_empty_directory(storage):
    storage.mkdir("Empty")

    assert storage.stat("Empty").is_dir
    assert storage.list("Empty") == []
    with pytest.raises(AlreadyExists):
        storage.mkdir("Empty")


def test_missing_paths(storage):
    with pytest.raises(NotFound):
        storage.stat("nope.mp3")
    with pytest.raises(NotFound):
        storage.list("nope")
    with pytest.raises(NotFound):
        b"".join(storage.read("nope.mp3"))
    with pytest.raises(NotFound):
        storage.delete("nope.mp3")
    assert not storage.exists("nope.mp3")


def test_move_file_and_directory(storage):
    storage.write("Sub/a.mp3", b"a")
    storage.write("Sub/Deeper/b.mp3", b"b")
    storage.mkdir("Target")

    storage.move("Sub/a.mp3", "Target/a.mp3")
    storage.move("Sub", "Target/Sub")

    assert storage.read_bytes("Target/a.mp3") == b"a"
    assert storage.read_bytes("Target/Sub/Deeper/b.mp3") == b"b"
    assert not storage.exists("Sub") and not storage.exists("Sub/a.mp3")


def test_move_conflicts(storage):
    storage.write("a.mp3", b"a")
    storage.write("b.mp3", b"b")
    storage.write("Dir/x.mp3", b"x")

    with pytest.raises(AlreadyExists):
        storage.move("a.mp3", "b.mp3")
    with pytest.raises(InvalidPath):
        storage.move("Dir", "Dir/Inner")
    with pytest.raises(NotFound):
        storage.move("missing.mp3", "c.mp3")


def test_delete_file_and_directory(storage):
    storage.write("Sub/a.mp3", b"a")
    storage.write("Sub/Deeper/b.mp3", b"b")
    storage.write("keep.mp3", b"k")

    storage.delete("Sub/a.mp3")
    assert not storage.exists("Sub/a.mp3")
    storage.delete("Sub")
    assert not storage.exists("Sub/Deeper/b.mp3")
    assert storage.exists("keep.mp3")
    with pytest.raises(InvalidPath):
        storage.delete("")


def test_local_file_gives_a_readable_path(storage):
    storage.write("song.mp3", b"audio")

    with storage.local_file("song.mp3") as path:
        assert path.read_bytes() == b"audio"
        assert path.suffix == ".mp3"


@pytest.mark.parametrize("path", ["../outside", "a/../../outside", "..", "C:/Windows"])
def test_paths_cannot_escape_the_root(storage, path):
    with pytest.raises(InvalidPath):
        storage.stat(path)
    with pytest.raises(InvalidPath):
        storage.write(path, b"x")


def test_normalize():
    assert normalize("/a//b/./c\\d/") == "a/b/c/d"
    assert normalize(None) == ""
    assert normalize("") == ""


def test_local_symlink_cannot_leave_the_root(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.mp3").write_bytes(b"x")
    root = tmp_path / "library"
    root.mkdir()
    try:
        (root / "link").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks not permitted")

    with pytest.raises(InvalidPath):
        LocalStorage(root).stat("link/secret.mp3")


def test_local_absolute_path_mapping(tmp_path):
    storage = LocalStorage(tmp_path)
    storage.write("a/b.mp3", b"x")

    assert storage.relative(tmp_path / "a" / "b.mp3") == "a/b.mp3"
    assert storage.relative(tmp_path) == ""
    assert storage.resolve("a/b.mp3") == (tmp_path / "a" / "b.mp3").resolve()


def test_s3_presigned_url_and_prefix_isolation():
    client = FakeS3Client()
    client.objects["other/x.mp3"] = b"x"
    storage = S3Storage("bucket", prefix="rpg", client=client)
    storage.write("song.mp3", b"s")

    assert "rpg/song.mp3" in client.objects
    assert storage.url("song.mp3", 60) == "https://example.test/bucket/rpg/song.mp3?expires=60"
    assert [e.path for e in storage.list()] == ["song.mp3"]


def test_s3_timestamps_are_whole_seconds():
    from datetime import datetime, timezone

    from core.storage.s3 import _timestamp

    assert _timestamp(datetime(2026, 1, 1, 0, 0, 5, 750000, tzinfo=timezone.utc)) == _timestamp(datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc))


def test_s3_urls_are_signed_for_the_public_endpoint():
    class Signer(FakeS3Client):
        def generate_presigned_url(self, op, Params, ExpiresIn):
            return f"https://public.test/{Params['Key']}"

    storage = S3Storage("bucket", client=FakeS3Client(), signer=Signer())

    assert storage.url("a.mp3") == "https://public.test/a.mp3"


def test_local_has_no_direct_url(tmp_path):
    assert LocalStorage(tmp_path).url("a.mp3") is None


def test_create_storage(tmp_path):
    assert isinstance(create_storage({"type": "local", "path": str(tmp_path), "name": "Music"}), LocalStorage)
    assert create_storage({"path": str(tmp_path)}).name == tmp_path.name
    with pytest.raises(ValueError):
        create_storage({"type": "ftp"})


def test_real_boto3_client_is_configured_for_s3_compatible_services():
    pytest.importorskip("boto3")

    storage = S3Storage("bucket", endpoint_url="https://acc.r2.cloudflarestorage.com", region="auto", access_key="AK", secret_key="SK",
                        public_endpoint_url="https://public.example.com")
    config = storage.client.meta.config

    assert config.request_checksum_calculation == "when_required"
    assert config.response_checksum_validation == "when_required"
    assert config.s3["addressing_style"] == "path"
    assert storage.url("a.mp3").startswith("https://public.example.com/bucket/a.mp3?")
