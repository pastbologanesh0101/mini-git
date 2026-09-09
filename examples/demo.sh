#!/usr/bin/env bash
# A guided tour: build a repo with Mini Git, then verify it with the real git.
set -euo pipefail

MG="python -m minigit"
PLAY=$(mktemp -d)
cd "$PLAY"
echo ">>> playground: $PLAY"

$MG init
echo "hello world"            > hello.txt
mkdir src && echo "print(1)"  > src/main.py
$MG add .
$MG commit -m "initial commit"

echo "goodbye"                > hello.txt
$MG add .
$MG commit -m "update hello.txt"

echo
echo ">>> minigit log"
$MG log

echo
echo ">>> the SAME repository, read by the real git binary:"
git --git-dir=.minigit fsck && echo "    git fsck: clean"
git --git-dir=.minigit log --oneline --stat

echo
echo ">>> object stored by minigit == object git would store:"
git_sha=$(git hash-object hello.txt)
mini_sha=$($MG hash-object hello.txt)
if [ "$git_sha" = "$mini_sha" ]; then
    echo "    hashes match ($mini_sha)"
else
    echo "    MISMATCH: git=$git_sha minigit=$mini_sha"; exit 1
fi

rm -rf "$PLAY"
