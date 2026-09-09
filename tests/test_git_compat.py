"""Prove the object store is byte-compatible with real Git by pointing the
real ``git`` binary at a Mini Git repository."""

import os
import shutil
import subprocess

import pytest

from minigit import porcelain
from minigit.repository import Repository

git = shutil.which("git")
pytestmark = pytest.mark.skipif(not git, reason="real git not installed")


def run_git(git_dir, *args):
    return subprocess.run(
        [git, f"--git-dir={git_dir}", *args],
        capture_output=True, text=True, check=True,
    ).stdout


def test_real_git_reads_minigit_objects(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    repo = Repository.init(str(wt))

    (wt / "hello.txt").write_text("hello world\n")
    (wt / "sub").mkdir()
    (wt / "sub" / "nested.txt").write_text("deep\n")
    porcelain.add(repo, ["."])
    sha = porcelain.commit(repo, "initial commit", when=1700000000)

    # real git can cat-file the commit Mini Git wrote
    out = run_git(repo.git_dir, "cat-file", "-p", sha)
    assert "initial commit" in out
    assert out.startswith("tree ")

    # ... and walk the tree, and read the blob
    ls = run_git(repo.git_dir, "ls-tree", "-r", sha)
    assert "hello.txt" in ls and "sub/nested.txt" in ls

    blob_line = [l for l in ls.splitlines() if "hello.txt" in l][0]
    blob_sha = blob_line.split()[2]
    assert run_git(repo.git_dir, "cat-file", "-p", blob_sha) == "hello world\n"

    # real git log walks the history Mini Git built
    log = run_git(repo.git_dir, "log", "--format=%s")
    assert log.strip() == "initial commit"

    # git fsck is happy with the object database
    subprocess.run([git, f"--git-dir={repo.git_dir}", "fsck"], check=True,
                   capture_output=True)


def test_blob_sha_equals_git_hash_object(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    repo = Repository.init(str(wt))
    (wt / "f").write_text("some content here\n")
    [staged] = porcelain.add(repo, ["f"])

    from minigit.index import Index
    mini_sha = Index(repo.index_path()).entries["f"].sha

    git_sha = subprocess.run(
        [git, "hash-object", str(wt / "f")],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert mini_sha == git_sha
