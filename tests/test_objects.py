import hashlib
import subprocess
import zlib

import pytest

from minigit.objects import (
    Commit,
    TreeEntry,
    hash_bytes,
    parse_tree,
    read_object,
    resolve_short,
    serialize_tree,
    write_object,
)


def test_blob_hash_matches_git_formula():
    payload = b"hello world\n"
    # Git: sha1("blob 12\0hello world\n")
    expected = hashlib.sha1(b"blob 12\x00" + payload).hexdigest()
    assert hash_bytes("blob", payload) == expected
    assert expected == "3b18e512dba79e4c8300dd08aeb37f8e728b8dad"  # known value


def test_write_then_read_roundtrip(tmp_path):
    gd = str(tmp_path)
    import os
    os.makedirs(f"{gd}/objects")
    sha = write_object(gd, "blob", b"content")
    assert read_object(gd, sha) == ("blob", b"content")


def test_object_is_zlib_of_git_framing(tmp_path):
    import os
    gd = str(tmp_path); os.makedirs(f"{gd}/objects")
    sha = write_object(gd, "blob", b"abc")
    raw = open(f"{gd}/objects/{sha[:2]}/{sha[2:]}", "rb").read()
    assert zlib.decompress(raw) == b"blob 3\x00abc"


def test_corruption_is_detected(tmp_path):
    import os
    gd = str(tmp_path); os.makedirs(f"{gd}/objects")
    sha = write_object(gd, "blob", b"data")
    p = f"{gd}/objects/{sha[:2]}/{sha[2:]}"
    open(p, "wb").write(zlib.compress(b"blob 4\x00XXXX"))
    with pytest.raises(ValueError):
        read_object(gd, sha)


def test_tree_serialize_sorts_like_git():
    entries = [
        TreeEntry("100644", "b.txt", "00" * 20),
        TreeEntry("40000", "a", "11" * 20),
        TreeEntry("100644", "a.txt", "22" * 20),
    ]
    blob = serialize_tree(entries)
    names = [e.name for e in parse_tree(blob)]
    # "a" (dir, sorts as "a/") comes after "a.txt" but before "b.txt"
    assert names == ["a.txt", "a", "b.txt"]


def test_commit_roundtrip():
    c = Commit(tree="a" * 40, parents=["b" * 40], author="me <m@x> 100 +0000",
               committer="me <m@x> 100 +0000", message="hello\n")
    c2 = Commit.parse(c.serialize())
    assert (c2.tree, c2.parents, c2.message.strip()) == (c.tree, c.parents, "hello")


def test_resolve_short_prefix(tmp_path):
    import os
    gd = str(tmp_path); os.makedirs(f"{gd}/objects")
    sha = write_object(gd, "blob", b"unique-content-xyz")
    assert resolve_short(gd, sha[:8]) == sha
    with pytest.raises(ValueError):
        resolve_short(gd, "ab")  # too short
