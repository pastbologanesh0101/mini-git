"""The content-addressable object store.

Mini Git uses **exactly Git's on-disk object format**, so a repository created
here can be inspected with the real thing::

    git --git-dir=.minigit cat-file -p HEAD
    git --git-dir=.minigit log --stat

An object is::

    "<type> <size>\\0<payload>"

zlib-compressed and written to ``objects/<sha1[:2]>/<sha1[2:]>`` where ``sha1``
is the SHA-1 of the *uncompressed* bytes. That hash is the object's identity —
change one byte of content and it lands at a different path, which is the whole
trick behind Git's integrity and deduplication.

Three object types matter here:

* **blob**   — a file's raw bytes.
* **tree**   — a directory listing: ``mode name\\0<20-byte binary sha>`` entries,
  sorted, one per child (blob or sub-tree).
* **commit** — ``tree``, zero or more ``parent`` lines, ``author``,
  ``committer``, blank line, message.
"""

from __future__ import annotations

import hashlib
import os
import zlib
from dataclasses import dataclass, field
from typing import Optional

# --------------------------------------------------------------------------
# hashing / raw object io
# --------------------------------------------------------------------------
def hash_bytes(obj_type: str, payload: bytes) -> str:
    header = f"{obj_type} {len(payload)}".encode() + b"\x00"
    return hashlib.sha1(header + payload).hexdigest()


def object_path(git_dir: str, sha: str) -> str:
    return os.path.join(git_dir, "objects", sha[:2], sha[2:])


def write_object(git_dir: str, obj_type: str, payload: bytes) -> str:
    sha = hash_bytes(obj_type, payload)
    path = object_path(git_dir, sha)
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        store = f"{obj_type} {len(payload)}".encode() + b"\x00" + payload
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(zlib.compress(store, 1))
        os.replace(tmp, path)
    return sha


def read_object(git_dir: str, sha: str) -> tuple[str, bytes]:
    sha = resolve_short(git_dir, sha)
    with open(object_path(git_dir, sha), "rb") as f:
        raw = zlib.decompress(f.read())
    nul = raw.index(b"\x00")
    obj_type, size = raw[:nul].decode().split(" ")
    payload = raw[nul + 1:]
    if len(payload) != int(size):
        raise ValueError(f"object {sha}: size {len(payload)} != header {size}")
    if hash_bytes(obj_type, payload) != sha:
        raise ValueError(f"object {sha}: content hash mismatch (corruption)")
    return obj_type, payload


def resolve_short(git_dir: str, prefix: str) -> str:
    """Expand an unambiguous >=4 char object-id prefix to a full sha."""
    if len(prefix) == 40:
        return prefix
    if len(prefix) < 4:
        raise ValueError("object id prefix too short")
    d = os.path.join(git_dir, "objects", prefix[:2])
    if not os.path.isdir(d):
        raise KeyError(prefix)
    matches = [prefix[:2] + name for name in os.listdir(d)
               if name.startswith(prefix[2:])]
    if not matches:
        raise KeyError(prefix)
    if len(matches) > 1:
        raise ValueError(f"ambiguous object prefix {prefix!r}")
    return matches[0]


# --------------------------------------------------------------------------
# typed views
# --------------------------------------------------------------------------
@dataclass
class TreeEntry:
    mode: str          # "100644" file, "100755" exec, "40000" dir
    name: str
    sha: str

    @property
    def is_dir(self) -> bool:
        return self.mode == "40000"


def serialize_tree(entries: list[TreeEntry]) -> bytes:
    out = bytearray()
    # Git sorts entries by name, with a subtlety: a directory sorts as if its
    # name had a trailing "/".
    for e in sorted(entries, key=lambda e: e.name + ("/" if e.is_dir else "")):
        out += f"{e.mode} {e.name}".encode() + b"\x00" + bytes.fromhex(e.sha)
    return bytes(out)


def parse_tree(payload: bytes) -> list[TreeEntry]:
    entries, i = [], 0
    while i < len(payload):
        sp = payload.index(b" ", i)
        nul = payload.index(b"\x00", sp)
        mode = payload[i:sp].decode()
        name = payload[sp + 1:nul].decode()
        sha = payload[nul + 1:nul + 21].hex()
        entries.append(TreeEntry(mode, name, sha))
        i = nul + 21
    return entries


@dataclass
class Commit:
    tree: str
    parents: list[str] = field(default_factory=list)
    author: str = ""
    committer: str = ""
    message: str = ""

    def serialize(self) -> bytes:
        lines = [f"tree {self.tree}"]
        lines += [f"parent {p}" for p in self.parents]
        lines.append(f"author {self.author}")
        lines.append(f"committer {self.committer}")
        lines.append("")
        lines.append(self.message.rstrip("\n") + "\n")
        return "\n".join(lines).encode()

    @classmethod
    def parse(cls, payload: bytes) -> "Commit":
        head, _, message = payload.partition(b"\n\n")
        c = cls(tree="", message=message.decode())
        for line in head.decode().splitlines():
            key, _, val = line.partition(" ")
            if key == "tree":
                c.tree = val
            elif key == "parent":
                c.parents.append(val)
            elif key == "author":
                c.author = val
            elif key == "committer":
                c.committer = val
        return c


def format_signature(name: str, email: str, when: Optional[int] = None,
                     tz: str = "+0000") -> str:
    import time as _time

    when = int(_time.time()) if when is None else when
    return f"{name} <{email}> {when} {tz}"
