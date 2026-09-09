"""User-facing operations: add, status, write-tree, commit, log, checkout."""

from __future__ import annotations

import os
import stat as _stat
from typing import Iterator

from .index import Index
from .objects import (
    Commit,
    TreeEntry,
    format_signature,
    parse_tree,
    read_object,
    serialize_tree,
    write_object,
)
from .repository import Repository

IGNORE = {".minigit", ".git", "__pycache__", ".pytest_cache"}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _iter_worktree(root: str) -> Iterator[str]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE]
        for name in filenames:
            full = os.path.join(dirpath, name)
            yield os.path.relpath(full, root).replace(os.sep, "/")


def _mode_for(path: str) -> str:
    return "100755" if os.stat(path).st_mode & _stat.S_IXUSR else "100644"


def _open_index(repo: Repository) -> Index:
    return Index(repo.index_path())


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------
def add(repo: Repository, paths: list[str]) -> list[str]:
    idx = _open_index(repo)
    staged = []
    targets = paths or ["."]
    for target in targets:
        abstarget = os.path.join(repo.worktree, target)
        prefix = "" if target == "." else target.rstrip("/") + "/"
        if os.path.isdir(abstarget) or target == ".":
            files = [p for p in _iter_worktree(repo.worktree)
                     if target == "." or p == target or p.startswith(prefix)]
            # Staging a directory also stages deletions of tracked files under it.
            for tracked in idx.paths():
                if (target == "." or tracked == target or tracked.startswith(prefix)) \
                        and not os.path.exists(os.path.join(repo.worktree, tracked)):
                    idx.remove(tracked)
                    staged.append(tracked)
        else:
            files = [target]
        for rel in files:
            full = os.path.join(repo.worktree, rel)
            if not os.path.exists(full):
                idx.remove(rel)
                staged.append(rel)
                continue
            with open(full, "rb") as f:
                sha = write_object(repo.git_dir, "blob", f.read())
            idx.add(rel, _mode_for(full), sha)
            staged.append(rel)
    idx.save()
    return staged


def write_tree(repo: Repository) -> str:
    """Build nested tree objects from the index and return the root tree sha."""
    idx = _open_index(repo)

    # group entries into a directory trie
    tree: dict = {}
    for path in idx.paths():
        e = idx.entries[path]
        parts = path.split("/")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = e

    def build(node: dict) -> str:
        entries = []
        for name, child in node.items():
            if isinstance(child, dict):
                entries.append(TreeEntry("40000", name, build(child)))
            else:
                entries.append(TreeEntry(child.mode, name, child.sha))
        return write_object(repo.git_dir, "tree", serialize_tree(entries))

    return build(tree)


def commit(repo: Repository, message: str, *, name: str = "Mini Git User",
           email: str = "user@example.com", when: int | None = None) -> str:
    tree_sha = write_tree(repo)
    parent = repo.resolve_head()
    parents = [parent] if parent else []

    if parent:
        parent_tree = Commit.parse(read_object(repo.git_dir, parent)[1]).tree
        if parent_tree == tree_sha:
            raise SystemExit("nothing to commit, working tree clean")

    sig = format_signature(name, email, when)
    c = Commit(tree=tree_sha, parents=parents, author=sig, committer=sig,
               message=message)
    sha = write_object(repo.git_dir, "commit", c.serialize())

    ref = repo.head_ref()
    if ref:
        repo.update_ref(ref, sha)
    else:
        repo.set_head_to_commit(sha)
    return sha


def log(repo: Repository, max_count: int | None = None) -> list[tuple[str, Commit]]:
    sha = repo.resolve_head()
    out = []
    while sha:
        c = Commit.parse(read_object(repo.git_dir, sha)[1])
        out.append((sha, c))
        if max_count and len(out) >= max_count:
            break
        sha = c.parents[0] if c.parents else None
    return out


def _flatten_tree(repo: Repository, tree_sha: str, prefix: str = "") -> dict[str, tuple[str, str]]:
    """Return ``{path: (mode, blob_sha)}`` for every file under a tree."""
    result: dict[str, tuple[str, str]] = {}
    for e in parse_tree(read_object(repo.git_dir, tree_sha)[1]):
        path = prefix + e.name
        if e.is_dir:
            result.update(_flatten_tree(repo, e.sha, path + "/"))
        else:
            result[path] = (e.mode, e.sha)
    return result


def status(repo: Repository) -> dict[str, list[str]]:
    idx = _open_index(repo)
    index_map = {p: idx.entries[p].sha for p in idx.paths()}

    head_sha = repo.resolve_head()
    head_map: dict[str, tuple[str, str]] = {}
    if head_sha:
        tree = Commit.parse(read_object(repo.git_dir, head_sha)[1]).tree
        head_map = _flatten_tree(repo, tree)

    work_map = {}
    for rel in _iter_worktree(repo.worktree):
        full = os.path.join(repo.worktree, rel)
        with open(full, "rb") as f:
            from .objects import hash_bytes
            work_map[rel] = hash_bytes("blob", f.read())

    staged, modified, untracked, deleted = [], [], [], []
    for p, sha in index_map.items():
        head_sha_p = head_map.get(p, (None, None))[1]
        if head_sha_p != sha:
            staged.append(p)
        if p not in work_map:
            deleted.append(p)
        elif work_map[p] != sha:
            modified.append(p)
    for p in work_map:
        if p not in index_map:
            untracked.append(p)

    return {
        "staged": sorted(staged),
        "modified": sorted(modified),
        "deleted": sorted(deleted),
        "untracked": sorted(untracked),
        "branch": (repo.head_ref() or "HEAD (detached)").replace("refs/heads/", ""),
    }


def checkout(repo: Repository, target: str) -> str:
    """Restore the worktree + index to a commit or branch. Refuses if dirty."""
    st = status(repo)
    if st["modified"] or st["staged"] or st["deleted"]:
        raise SystemExit("error: your local changes would be overwritten; commit them first")

    if target in repo.branches():
        commit_sha = repo.read_ref(f"refs/heads/{target}")
        repo.set_head_to_branch(target)
    else:
        from .objects import resolve_short
        commit_sha = resolve_short(repo.git_dir, target)
        repo.set_head_to_commit(commit_sha)

    tree = Commit.parse(read_object(repo.git_dir, commit_sha)[1]).tree
    want = _flatten_tree(repo, tree)

    # remove tracked files that aren't in the target
    idx = _open_index(repo)
    for p in idx.paths():
        if p not in want:
            fp = os.path.join(repo.worktree, p)
            if os.path.exists(fp):
                os.remove(fp)

    new_index = Index(repo.index_path())
    new_index.entries.clear()
    for path, (mode, blob_sha) in want.items():
        fp = os.path.join(repo.worktree, path)
        os.makedirs(os.path.dirname(fp) or ".", exist_ok=True)
        data = read_object(repo.git_dir, blob_sha)[1]
        with open(fp, "wb") as f:
            f.write(data)
        if mode == "100755":
            os.chmod(fp, 0o755)
        new_index.add(path, mode, blob_sha)
    new_index.save()
    return commit_sha
