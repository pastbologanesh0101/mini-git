# Mini Git

A small version control system built from scratch in pure Python. It implements
Git's **content-addressable object store** exactly — same `blob`/`tree`/`commit`
format, same zlib framing, same SHA-1 addressing — so a repository created by
Mini Git can be inspected and verified by the **real `git` binary**:

```console
$ python -m minigit init
$ echo "hello world" > hello.txt && python -m minigit add .
$ python -m minigit commit -m "initial commit"
[1ffa5bac98] initial commit

$ git --git-dir=.minigit fsck
    git fsck: clean
$ git --git-dir=.minigit log --oneline
1ffa5ba initial commit
```

Built to answer: what actually *is* a commit? Why is Git's history tamper-evident?
How does `git add` / `git commit` turn a directory of files into a graph of
hashed objects on disk?

## Quick start

```bash
git clone https://github.com/pastbologanesh0101/mini-git
cd mini-git
pip install -e ".[dev]"

pytest -q                  # 16 tests, incl. a real-git compatibility suite
bash examples/demo.sh      # guided tour + cross-check against real git
```

```bash
python -m minigit init
python -m minigit add src/ README.md
python -m minigit status
python -m minigit commit -m "first commit"
python -m minigit log
python -m minigit cat-file -p HEAD
python -m minigit checkout <commit-sha>     # restore the worktree
```

## Concepts demonstrated

| Area | Where | What it shows |
|---|---|---|
| **Hashing / integrity** | `minigit/objects.py` | Every object's name is the SHA-1 of `"<type> <len>\0<payload>"`. Change one byte and it hashes to a different address — so a commit id pins its tree, which pins every blob. A tampered object is caught on read (`read_object` re-hashes) and by `git fsck`. |
| **File systems** | `objects.py`, `porcelain.py` | Objects live in a fan-out directory (`objects/ab/cdef…`). `write-tree` walks the worktree into **nested tree objects**; `checkout` walks them back out, creating/removing files and dirs. Atomic writes via `tmp` + `os.replace`. |
| **The Git data model** | `objects.py` | `blob` (file bytes), `tree` (sorted dir listing with the trailing-slash sort quirk), `commit` (tree + parents + author/committer + message). The commit graph is a Merkle DAG. |
| **Refs & HEAD** | `minigit/repository.py` | `HEAD` as a symbolic ref (`ref: refs/heads/main`), branch refs as files holding a sha, detached HEAD, unborn branch. |
| **The staging area** | `minigit/index.py`, `porcelain.status` | A three-way comparison — worktree vs index vs HEAD — produces staged / modified / untracked / deleted, just like `git status`. |
| **Wire/format compatibility** | `tests/test_git_compat.py` | The test suite runs the real `git` binary (`cat-file`, `ls-tree`, `log`, `fsck`, `hash-object`) against repos Mini Git produced. |

## How a commit is built

```
add .            worktree files ─► blob objects ─► entries in .minigit/mini-index
commit -m "…"    index ─► nested tree objects ─► commit object ─► refs/heads/main
```

`commit` refuses if the resulting tree equals the parent's ("nothing to
commit"), and `checkout` refuses if the worktree has uncommitted changes.

## What's compatible with real Git (and what isn't)

**Compatible** — the object database and refs. Real `git` can `cat-file`,
`ls-tree`, `log`, and `fsck` a `.minigit` repo, and `git hash-object` produces
the identical sha for any file Mini Git stages.

**Not compatible** — the staging file. Git's index is a fiddly binary format
with a stat cache; Mini Git uses a simple sorted text file and deliberately
names it `mini-index` (not `index`) so the real `git` binary doesn't try to
parse it.

## Commands

```
init          hash-object -w -t     cat-file -t/-s/-p
add           write-tree            commit -m
status        log -n                checkout <sha|branch>
ls-files
```

## Limitations

- **No diffs, no merges, no rebase, no remotes**, no packfiles (loose objects
  only), no `.gitignore` (a small hardcoded ignore set).
- Single-parent history walking in `log` (follows first parent).
- Text index without a stat cache, so `status` always re-hashes the worktree.

## Project layout

```
minigit/
  objects.py      hashing, zlib, blob/tree/commit read-write-parse
  repository.py   .minigit layout, HEAD & ref resolution
  index.py        the staging area (sorted text)
  porcelain.py    add / write-tree / commit / log / status / checkout
  cli.py          argparse subcommands
tests/
  test_objects.py     hashing matches git, framing, corruption detection
  test_porcelain.py   add/commit/log/status/checkout, nested trees
  test_git_compat.py  real `git` binary reads Mini Git repos
```

## License

MIT
