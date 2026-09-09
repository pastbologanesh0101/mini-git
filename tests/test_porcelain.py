import os

import pytest

from minigit import porcelain
from minigit.repository import Repository


@pytest.fixture
def repo(tmp_path):
    wt = tmp_path / "wt"
    wt.mkdir()
    return Repository.init(str(wt))


def write(repo, rel, content):
    p = os.path.join(repo.worktree, rel)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as f:
        f.write(content)


def test_init_layout(repo):
    assert os.path.isdir(repo.path("objects"))
    assert os.path.isdir(repo.path("refs", "heads"))
    assert open(repo.path("HEAD")).read().strip() == "ref: refs/heads/main"


def test_add_and_commit_and_log(repo):
    write(repo, "a.txt", "alpha")
    write(repo, "dir/b.txt", "beta")
    porcelain.add(repo, ["."])
    c1 = porcelain.commit(repo, "first", when=1000)

    write(repo, "a.txt", "ALPHA changed")
    porcelain.add(repo, ["a.txt"])
    c2 = porcelain.commit(repo, "second", when=1001)

    history = porcelain.log(repo)
    assert [h[0] for h in history] == [c2, c1]
    assert history[0][1].parents == [c1]
    assert history[0][1].message.strip() == "second"
    # branch ref advanced
    assert repo.read_ref("refs/heads/main") == c2


def test_commit_refuses_when_nothing_changed(repo):
    write(repo, "a.txt", "x")
    porcelain.add(repo, ["."])
    porcelain.commit(repo, "one", when=1)
    with pytest.raises(SystemExit):
        porcelain.commit(repo, "again", when=2)


def test_status_transitions(repo):
    write(repo, "tracked.txt", "v1")
    porcelain.add(repo, ["."])
    porcelain.commit(repo, "init", when=1)

    write(repo, "tracked.txt", "v2")     # modified in worktree
    write(repo, "new.txt", "brand new")  # untracked
    st = porcelain.status(repo)
    assert st["modified"] == ["tracked.txt"]
    assert st["untracked"] == ["new.txt"]
    assert st["staged"] == []

    porcelain.add(repo, ["tracked.txt", "new.txt"])
    st = porcelain.status(repo)
    assert set(st["staged"]) == {"tracked.txt", "new.txt"}
    assert st["modified"] == []


def test_checkout_restores_worktree(repo):
    write(repo, "keep.txt", "original")
    write(repo, "gone-later.txt", "temp")
    porcelain.add(repo, ["."])
    c1 = porcelain.commit(repo, "c1", when=1)

    os.remove(os.path.join(repo.worktree, "gone-later.txt"))
    write(repo, "keep.txt", "edited")
    write(repo, "added.txt", "new")
    porcelain.add(repo, ["."])
    porcelain.commit(repo, "c2", when=2)

    porcelain.checkout(repo, c1)

    assert open(os.path.join(repo.worktree, "keep.txt")).read() == "original"
    assert os.path.exists(os.path.join(repo.worktree, "gone-later.txt"))
    assert not os.path.exists(os.path.join(repo.worktree, "added.txt"))
    assert porcelain.status(repo)["branch"] == "HEAD (detached)"


def test_checkout_refuses_dirty_tree(repo):
    write(repo, "a.txt", "1")
    porcelain.add(repo, ["."])
    c1 = porcelain.commit(repo, "c1", when=1)
    write(repo, "a.txt", "2")
    porcelain.add(repo, ["."])
    porcelain.commit(repo, "c2", when=2)
    write(repo, "a.txt", "dirty uncommitted")
    with pytest.raises(SystemExit):
        porcelain.checkout(repo, c1)


def test_nested_trees_are_written(repo):
    write(repo, "src/pkg/mod.py", "code")
    write(repo, "src/main.py", "main")
    write(repo, "README", "readme")
    porcelain.add(repo, ["."])
    root = porcelain.write_tree(repo)

    from minigit.objects import parse_tree, read_object
    top = {e.name: e for e in parse_tree(read_object(repo.git_dir, root)[1])}
    assert set(top) == {"src", "README"}
    assert top["src"].is_dir
    src = {e.name: e for e in parse_tree(read_object(repo.git_dir, top["src"].sha)[1])}
    assert set(src) == {"pkg", "main.py"}
