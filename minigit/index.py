"""The staging area.

Git's real index is a fiddly binary file with stat cache data. Mini Git uses a
simple sorted text format instead — one entry per line::

    <mode> <sha> <path>

This is the one place Mini Git is *not* byte-compatible with Git (the object
store and refs are). It is enough to stage files, build trees and diff
worktree/index/HEAD.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(order=True)
class Entry:
    path: str
    mode: str
    sha: str


class Index:
    def __init__(self, path: str):
        self._path = path
        self.entries: dict[str, Entry] = {}
        if os.path.exists(path):
            self._load()

    def _load(self) -> None:
        with open(self._path) as f:
            for line in f:
                line = line.rstrip("\n")
                if not line:
                    continue
                mode, sha, path = line.split(" ", 2)
                self.entries[path] = Entry(path, mode, sha)

    def save(self) -> None:
        tmp = self._path + ".tmp"
        with open(tmp, "w") as f:
            for path in sorted(self.entries):
                e = self.entries[path]
                f.write(f"{e.mode} {e.sha} {e.path}\n")
        os.replace(tmp, self._path)

    # -- mutation -------------------------------------------
    def add(self, path: str, mode: str, sha: str) -> None:
        self.entries[path] = Entry(path, mode, sha)

    def remove(self, path: str) -> None:
        self.entries.pop(path, None)

    def paths(self) -> list[str]:
        return sorted(self.entries)
