#!/usr/bin/env python3
"""Generate (first run) or refresh the se-dev-weaponcore reference from a local WeaponCore git clone.

    python scripts/refresh.py --repo PATH/TO/WeaponCore                    # first run
    python scripts/refresh.py                                              # later runs
    python scripts/refresh.py --fetch origin                               # fetch first

The clone path and ref are remembered in data/build.json after the first run.

Steps: (optional) `git fetch REMOTE`; `git archive <ref>` of the WeaponCore scripts into a
temporary folder; run build_reference.py on it (writes tables/ and data/); delete the temporary
folder. It never checks out, merges, stashes or resets
anything in the clone, so local work there is safe.

Ref: --ref, else the one saved by the last run, else `origin/master`, else `HEAD`. A fork that
tracks Ash-LikeSnow/WeaponCore as `upstream` would pass `--ref upstream/master`.

--parts DIR (repeatable, remembered) adds a weapon mod's CoreParts folder as a source of example
values and comments. It is only read.

It also writes source/ (the WeaponCore scripts at that commit, for reading and for
`wc_graph.py uses`) and, when Graphify is available, a code graph in graph/graphify-out
(`wc_graph.py` queries it).
Graph modes (--graph, or SE_DEV_GRAPHIFY=1/0 like the other se-dev skills):
  auto  build if `graphify` is on PATH, otherwise skip with an install hint (default)
  yes   build; if graphify is not on PATH but uv is, run it through `uvx` (fetches it once)
  no    never build
The build is code-only (local AST parsing, no LLM, no API key) and takes about a minute. It is
skipped when the commit is unchanged and the existing graph is complete.

Afterwards it prints the code files that changed since the previous build. The hand-written
references/*.md cite file:line from the commit named at the top of SKILL.md, so check the
sections that cite changed files.
"""
import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
BUILD = os.path.join(SKILL, "data", "build.json")
PATHS = ["Data/Scripts/CoreSystems"]
SOURCE = os.path.join(SKILL, "source")
GRAPH_DIR = os.path.join(SKILL, "graph")
GRAPH_OUT = os.path.join(GRAPH_DIR, "graphify-out")
UVX_GRAPHIFY = ["uvx", "--python", "3.12", "--from", "graphifyy[leiden]", "graphify"]
INSTALL_HINT = 'uv tool install --python 3.12 "graphifyy[leiden]"   (or: pip install "graphifyy[leiden]")'


def graph_state():
    if not os.path.exists(os.path.join(GRAPH_OUT, "graph.json")):
        return "missing"
    if not os.path.exists(os.path.join(GRAPH_OUT, ".graphify_analysis.json")):
        return "incomplete"
    return "ok"


def build_graph(mode, unchanged, build):
    """Build or update the code graph. Returns a short status string; never raises."""
    if mode == "no":
        return "skipped (--graph no)"
    if unchanged and graph_state() == "ok":
        return "unchanged (graph is current)"
    cmd = ["graphify"] if shutil.which("graphify") else None
    if cmd is None and mode == "yes" and shutil.which("uvx"):
        cmd = UVX_GRAPHIFY
    if cmd is None:
        return "skipped: graphify not found. Install it with %s, then run refresh.py again." % INSTALL_HINT
    if graph_state() == "incomplete":
        shutil.rmtree(GRAPH_OUT, ignore_errors=True)
    # Code-only: no API key reaches graphify, so it can never call an LLM.
    env = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    print("Building the code graph (code-only, about a minute)...")
    r = subprocess.run(cmd + ["extract", SOURCE, "--code-only", "--out", GRAPH_DIR],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    out = (r.stdout or "") + (r.stderr or "")
    if r.returncode != 0 or graph_state() != "ok":
        tail = "\n".join(out.strip().splitlines()[-5:])
        return "FAILED (the tables are fine; the graph is optional):\n%s" % tail
    m = re.search(r"(\d+) nodes, (\d+) edges", out)
    build["graph_nodes"] = "%s nodes, %s edges" % m.groups() if m else ""
    build["graphify_cmd"] = cmd
    return "built: %s" % (build["graph_nodes"] or "ok")


def git(repo, *args, binary=False, check=True):
    r = subprocess.run(["git", "-C", repo] + list(args), capture_output=True)
    if r.returncode != 0:
        if not check:
            return None
        sys.exit("git %s failed: %s" % (" ".join(args), r.stderr.decode(errors="replace").strip()))
    return r.stdout if binary else r.stdout.decode().strip()


def load_build():
    try:
        with open(BUILD, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", help="path to a git clone of Ash-LikeSnow/WeaponCore")
    ap.add_argument("--parts", action="append", metavar="DIR",
                    help="extra weapon-mod CoreParts folder for example values (repeatable; remembered)")
    ap.add_argument("--ref", help="git ref to build from (default: saved, else origin/master, else HEAD)")
    ap.add_argument("--fetch", metavar="REMOTE", help="git fetch this remote first")
    env_mode = {"1": "yes", "0": "no"}.get(os.environ.get("SE_DEV_GRAPHIFY", ""), "auto")
    ap.add_argument("--graph", choices=["auto", "yes", "no"], default=env_mode,
                    help="build the optional code graph (default: auto, or SE_DEV_GRAPHIFY=1/0)")
    a = ap.parse_args()

    prev = load_build()
    repo = a.repo or os.environ.get("WC_REPO") or prev.get("repo")
    if not repo:
        sys.exit("No WeaponCore clone given. Run once with --repo PATH/TO/WeaponCore.")
    parts = a.parts if a.parts is not None else prev.get("extra_parts", [])
    parts = [os.path.abspath(os.path.expanduser(p)) for p in parts]
    repo = os.path.abspath(os.path.expanduser(repo))
    if git(repo, "rev-parse", "--git-dir", check=False) is None:
        sys.exit("%s is not a git clone." % repo)

    if a.fetch:
        git(repo, "fetch", a.fetch)
    ref = a.ref or prev.get("ref")
    if not ref:
        ref = "origin/master" if git(repo, "rev-parse", "--verify", "-q", "origin/master", check=False) else "HEAD"
    sha = git(repo, "rev-parse", ref)
    date = git(repo, "log", "-1", "--format=%cs", sha)
    for p in PATHS:
        if not git(repo, "ls-tree", "-d", sha, p, check=False):
            sys.exit("%s at %s has no %s. Is this the WeaponCore repository?" % (repo, ref, p))

    tmp = tempfile.mkdtemp(prefix="wc-archive-")
    try:
        data = git(repo, "archive", "--format=tar", sha, *PATHS, binary=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as t:
            try:
                t.extractall(tmp, filter="data")
            except TypeError:  # Python without extraction filters
                t.extractall(tmp)
        cmd = [sys.executable, "-I", os.path.join(HERE, "build_reference.py"), tmp,
               "--commit", sha, "--date", date, "--ref", ref, "--out", SKILL]
        for p in parts:
            cmd += ["--parts", p]
        subprocess.run(cmd, check=True)
        unchanged = prev.get("commit") == sha and os.path.isdir(SOURCE)
        if not unchanged:
            if os.path.isdir(SOURCE):
                shutil.rmtree(SOURCE)
            shutil.copytree(os.path.join(tmp, *PATHS[0].split("/")), SOURCE)
            # the export is the only copy of the source; keep the license beside it
            lic = git(repo, "show", "%s:License" % sha, binary=True, check=False)
            if lic:
                with open(os.path.join(SOURCE, "LICENSE-WeaponCore.txt"), "wb") as f:
                    f.write(lic)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    build = load_build()
    build["repo"] = repo
    for k in ("graph_nodes", "graphify_cmd"):  # carried over when the graph is left as is
        if k in prev and k not in build:
            build[k] = prev[k]
    graph_status = build_graph(a.graph, unchanged, build)
    with open(BUILD, "w", encoding="utf-8", newline="\n") as f:
        json.dump(build, f, indent=1)

    print("Built from %s %s (%s), WeaponCore ModVersion %s." % (ref, sha, date, build.get("mod_version", "?")))
    print("Code graph: %s" % graph_status)
    old = prev.get("commit")
    if old and old != sha:
        print("Previous build: %s. Code files changed since then:" % old)
        print(git(repo, "diff", "--stat", old, sha, "--", PATHS[0], check=False) or "  (none, or the old commit is not in this clone)")


if __name__ == "__main__":
    main()
