"""Repository layout, ref resolution and the ``.minigit`` directory.

Mirrors Git's ``.git`` on purpose (``objects/``, ``refs/heads/``, ``HEAD`` as a
symbolic ref) so real Git tooling can read a Mini Git repo with
``--git-dir=.minigit``.
"""

from __future__ import annotations

import os

GIT_DIR_NAME = ".minigit"


class Repository:
    def __init__(self, worktree: str):
        self.worktree = os.path.abspath(worktree)
        self.git_dir = os.path.join(self.worktree, GIT_DIR_NAME)

    # -- discovery / creation --------------------------------
    @classmethod
    def find(cls, start: str = ".") -> "Repository":
        path = os.path.abspath(start)
        while True:
            if os.path.isdir(os.path.join(path, GIT_DIR_NAME)):
                return cls(path)
            parent = os.path.dirname(path)
            if parent == path:
                raise SystemExit("fatal: not a Mini Git repository (no .minigit)")
            path = parent

    @classmethod
    def init(cls, worktree: str) -> "Repository":
        repo = cls(worktree)
        for sub in ("objects", "refs/heads", "refs/tags"):
            os.makedirs(os.path.join(repo.git_dir, sub), exist_ok=True)
        head = os.path.join(repo.git_dir, "HEAD")
        if not os.path.exists(head):
            with open(head, "w") as f:
                f.write("ref: refs/heads/main\n")
        return repo

    # -- paths -----------------------------------------------
    def path(self, *parts: str) -> str:
        return os.path.join(self.git_dir, *parts)

    def index_path(self) -> str:
        # Deliberately NOT ".minigit/index": that name makes the real ``git``
        # binary try to parse our text staging file as its binary index and
        # abort. Everything else (objects, refs, HEAD) stays Git-compatible.
        return self.path("mini-index")

    # -- HEAD / refs ----------------------------------------
    def head_ref(self) -> str | None:
        """Return the branch ref HEAD points at, or None if detached."""
        with open(self.path("HEAD")) as f:
            content = f.read().strip()
        if content.startswith("ref: "):
            return content[5:]
        return None

    def read_ref(self, ref: str) -> str | None:
        p = self.path(ref)
        if not os.path.exists(p):
            return None
        with open(p) as f:
            return f.read().strip()

    def update_ref(self, ref: str, sha: str) -> None:
        p = self.path(ref)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(sha + "\n")

    def resolve_head(self) -> str | None:
        """The commit sha HEAD currently resolves to (or None on an unborn branch)."""
        ref = self.head_ref()
        if ref is None:  # detached HEAD holds a raw sha
            with open(self.path("HEAD")) as f:
                return f.read().strip()
        return self.read_ref(ref)

    def set_head_to_commit(self, sha: str) -> None:
        """Detach HEAD onto a specific commit."""
        with open(self.path("HEAD"), "w") as f:
            f.write(sha + "\n")

    def set_head_to_branch(self, branch: str) -> None:
        with open(self.path("HEAD"), "w") as f:
            f.write(f"ref: refs/heads/{branch}\n")

    def branches(self) -> list[str]:
        d = self.path("refs", "heads")
        return sorted(os.listdir(d)) if os.path.isdir(d) else []
