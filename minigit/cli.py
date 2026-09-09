"""``minigit`` command-line interface — a subset of git's porcelain + plumbing."""

from __future__ import annotations

import argparse
import sys
import time

from . import porcelain
from .objects import parse_tree, read_object, write_object
from .repository import Repository


def _repo() -> Repository:
    return Repository.find()


def cmd_init(ns):
    repo = Repository.init(ns.path)
    print(f"Initialized empty Mini Git repository in {repo.git_dir}")


def cmd_hash_object(ns):
    data = open(ns.file, "rb").read()
    git_dir = _repo().git_dir if ns.write else None
    if ns.write:
        print(write_object(git_dir, ns.type, data))
    else:
        from .objects import hash_bytes
        print(hash_bytes(ns.type, data))


def cmd_cat_file(ns):
    repo = _repo()
    obj_type, payload = read_object(repo.git_dir, ns.object)
    if ns.t:
        print(obj_type)
    elif ns.s:
        print(len(payload))
    elif ns.p:
        if obj_type == "tree":
            for e in parse_tree(payload):
                kind = "tree" if e.is_dir else "blob"
                print(f"{int(e.mode):06d} {kind} {e.sha}\t{e.name}")
        else:
            sys.stdout.buffer.write(payload)
    else:
        sys.exit("specify -t, -s or -p")


def cmd_add(ns):
    staged = porcelain.add(_repo(), ns.paths)
    for p in staged:
        print(f"add '{p}'")


def cmd_status(ns):
    st = porcelain.status(_repo())
    print(f"On branch {st['branch']}")
    _section("Changes to be committed", st["staged"], "new file/modified:")
    _section("Changes not staged for commit", st["modified"], "modified:")
    _section("Deleted", st["deleted"], "deleted:")
    _section("Untracked files", st["untracked"], "")
    if not any(st[k] for k in ("staged", "modified", "deleted", "untracked")):
        print("nothing to commit, working tree clean")


def _section(title, items, label):
    if not items:
        return
    print(f"\n{title}:")
    for it in items:
        print(f"\t{label} {it}".rstrip())


def cmd_write_tree(ns):
    print(porcelain.write_tree(_repo()))


def cmd_commit(ns):
    sha = porcelain.commit(_repo(), ns.message, when=int(time.time()))
    print(f"[{sha[:10]}] {ns.message.splitlines()[0]}")


def cmd_log(ns):
    for sha, c in porcelain.log(_repo(), ns.max_count):
        print(f"commit {sha}")
        print(f"Author: {c.author}")
        print(f"\n    {c.message.strip()}\n")


def cmd_checkout(ns):
    sha = porcelain.checkout(_repo(), ns.target)
    print(f"HEAD is now at {sha[:10]}")


def cmd_ls_files(ns):
    from .index import Index

    idx = Index(_repo().index_path())
    for p in idx.paths():
        print(p)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="minigit")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init"); s.add_argument("path", nargs="?", default="."); s.set_defaults(func=cmd_init)

    s = sub.add_parser("hash-object")
    s.add_argument("file"); s.add_argument("-w", dest="write", action="store_true")
    s.add_argument("-t", dest="type", default="blob"); s.set_defaults(func=cmd_hash_object)

    s = sub.add_parser("cat-file")
    s.add_argument("object")
    s.add_argument("-t", action="store_true"); s.add_argument("-s", action="store_true")
    s.add_argument("-p", action="store_true"); s.set_defaults(func=cmd_cat_file)

    s = sub.add_parser("add"); s.add_argument("paths", nargs="*"); s.set_defaults(func=cmd_add)
    s = sub.add_parser("status"); s.set_defaults(func=cmd_status)
    s = sub.add_parser("write-tree"); s.set_defaults(func=cmd_write_tree)

    s = sub.add_parser("commit"); s.add_argument("-m", dest="message", required=True)
    s.set_defaults(func=cmd_commit)

    s = sub.add_parser("log"); s.add_argument("-n", dest="max_count", type=int, default=None)
    s.set_defaults(func=cmd_log)

    s = sub.add_parser("checkout"); s.add_argument("target"); s.set_defaults(func=cmd_checkout)
    s = sub.add_parser("ls-files"); s.set_defaults(func=cmd_ls_files)
    return p


def main(argv=None) -> int:
    ns = build_parser().parse_args(argv)
    ns.func(ns)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
