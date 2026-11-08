#!/usr/bin/env python3
"""Code-graph queries over WeaponCore (CoreSystems): who calls what, how A reaches B, and who reads a field.

    python wc_graph.py status
    python wc_graph.py callers "Weapon.Shoot" [--depth 3]
    python wc_graph.py callees "Projectile.RunSmart"
    python wc_graph.py path "Session.Handler" "Session.PickDef"
    python wc_graph.py explain "ApiBackend.SetWeaponTarget"
    python wc_graph.py uses MaxTrajectory [--writes]

callers/callees/path/explain need the Graphify graph that scripts/refresh.py builds when
Graphify is installed (graph/graphify-out). `uses` needs only the source mirror (source/) that
refresh.py always writes, so it works without Graphify.

Names: methods are `Class.Method` (the "()" is added for you); classes are plain names. When a
name is ambiguous, the candidates are listed with their files; repeat with one of them.
Paths in the output are relative to source/ (= Data/Scripts/CoreSystems at the
commit in data/build.json).

Limits worth knowing: the graph has one `calls` edge per caller/callee pair, so when a method
calls another several times only one line is shown; fields and properties are not graph
nodes (use `uses`); calls through delegates, events and reflection are invisible to it
(WeaponCore dispatches much through delegates and partial classes, so check `uses` too).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SOURCE = os.path.join(SKILL, "source")
GRAPH_DIR = os.path.join(SKILL, "graph")
GRAPH_JSON = os.path.join(GRAPH_DIR, "graphify-out", "graph.json")
ANALYSIS = os.path.join(GRAPH_DIR, "graphify-out", ".graphify_analysis.json")
REFRESH = os.path.join(HERE, "refresh.py")


def load_build():
    try:
        with open(os.path.join(SKILL, "data", "build.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def graphify_cmd():
    b = load_build()
    if b.get("graphify_cmd"):
        return b["graphify_cmd"]
    if shutil.which("graphify"):
        return ["graphify"]
    return None


def graph_state():
    if not os.path.exists(GRAPH_JSON):
        return "missing"
    if not os.path.exists(ANALYSIS):
        return "incomplete"
    return "ok"


def need_graph():
    st = graph_state()
    if st != "ok":
        sys.exit("The code graph is %s. Build it with:\n    python %s --graph yes\n"
                 "(needs Graphify: uv tool install --python 3.12 \"graphifyy[leiden]\"). "
                 "`uses` works without it." % (st, REFRESH))
    cmd = graphify_cmd()
    if not cmd:
        sys.exit("The graph exists but graphify is not on PATH. Install it with:\n"
                 "    uv tool install --python 3.12 \"graphifyy[leiden]\"")
    return cmd


def norm(name):
    name = name.strip()
    if "." in name and not name.endswith(")"):
        name += "()"
    return name


def run_graphify(args):
    cmd = need_graph() + args + ["--graph", GRAPH_JSON]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, out


def show(args, filt=None):
    code, out = run_graphify(args)
    lines = out.splitlines()
    if filt and code == 0:
        lines = [ln for ln in lines if filt(ln)]
    print("\n".join(lines))
    return code


# ---------- uses: field / property references in the source mirror ----------

MOD = r"(?:public|private|protected|internal|static|override|virtual|abstract|async|sealed|new|unsafe|extern|partial|readonly)"
METHOD_RE = re.compile(r"^\s*(?:" + MOD + r"\s+)+[\w<>\[\],\.\?\s]+?\s+(\w+)\s*\([^;]*$")
CTOR_RE = re.compile(r"^\s*(?:public|private|protected|internal|static)\s+(\w+)\s*\([^;]*$")
PROP_RE = re.compile(r"^\s*(?:" + MOD + r"\s+)+[\w<>\[\],\.\?\s]+?\s+(\w+)\s*(?:\{|=>)")
CLASS_RE = re.compile(r"\b(?:class|struct|interface)\s+(\w+)")


def enclosing(lines, idx):
    member = None
    for j in range(idx, -1, -1):
        ln = lines[j]
        if member is None and not CLASS_RE.search(ln):
            m = METHOD_RE.match(ln) or CTOR_RE.match(ln) or PROP_RE.match(ln)
            if m and m.group(1) not in ("if", "for", "foreach", "while", "switch", "catch", "using", "lock", "return"):
                member = m.group(1)
        c = CLASS_RE.search(ln)
        if c and not ln.strip().startswith("//"):
            return c.group(1), member
    return None, member


def classify(line, name):
    s = re.sub(r"^(?:\[[^\]]*\]\s*)+", "", line.strip())  # drop [ProtoMember(n)] etc.
    if s.startswith("//"):
        return "comment"
    if re.search(r'"\[?' + re.escape(name) + r'[:\]"]', s) or re.search(r'\{\s*"' + re.escape(name) + r'"', s):
        return "tag-parse"
    if re.search(r"\bref\s+(?:this\.)?(?:\w+\.)*" + re.escape(name) + r"\b", s):
        return "write(ref)"
    if re.search(r"(?<![=!<>])\b" + re.escape(name) + r"\s*(?:=(?!=)|\+=|-=|\*=|/=|\+\+|--)", s):
        if re.match(r"^(?:" + MOD + r"\s+)+[\w<>\[\],\.\?\s]+?\s+" + re.escape(name) + r"\s*=", s):
            return "decl+init"
        return "write"
    if re.match(r"^(?:" + MOD + r"\s+)+[\w<>\[\],\.\?\s]+?\s+" + re.escape(name) + r"\s*[;{]", s):
        return "decl"
    if re.search(r"\b" + re.escape(name) + r"\s*\.\s*(?:Add|AddRange|Remove|RemoveAt|RemoveAll|Clear|Insert)\s*\(", s):
        return "mutate"
    return "read"


def uses(name, writes_only, limit):
    if not os.path.isdir(SOURCE):
        sys.exit("No source mirror yet. Run: python %s --repo PATH/TO/Modular-Encounters-Systems" % REFRESH)
    rx = re.compile(r"\b" + re.escape(name) + r"\b")
    hits = []
    for dp, _, fns in os.walk(SOURCE):
        for fn in fns:
            if not fn.endswith(".cs"):
                continue
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, SOURCE).replace("\\", "/")
            with open(p, encoding="utf-8-sig", errors="replace") as f:
                lines = f.read().splitlines()
            for i, ln in enumerate(lines):
                if rx.search(ln):
                    kind = classify(ln, name)
                    if kind == "comment":
                        continue
                    if writes_only and not kind.startswith("write"):
                        continue
                    cls, mem = enclosing(lines, i)
                    where = (cls or "?") if kind.startswith("decl") else "%s.%s" % (cls or "?", mem or "?")
                    hits.append((rel, i + 1, kind, where, ln.strip()))
    order = {"read": 0, "mutate": 1, "write": 2, "write(ref)": 3, "tag-parse": 4, "decl+init": 5, "decl": 6}
    hits.sort(key=lambda h: (order.get(h[2], 9), h[0], h[1]))
    for rel, ln, kind, where, text in hits[:limit]:
        if len(text) > 140:
            text = text[:139] + "…"
        print("%-10s %-55s %s:%d\n           %s" % (kind, where, rel, ln, text))
    if len(hits) > limit:
        print("... %d more (raise --limit)" % (len(hits) - limit))
    if not hits:
        print("No references to %s in source/." % name)
        return 1
    print("\n%d reference(s). Feed a method from the list to `callers` to see what reaches it." % len(hits))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("status", help="graph and source mirror state")
    p = sub.add_parser("callers", help="what calls this method (reverse, transitive)")
    p.add_argument("name"); p.add_argument("--depth", type=int, default=2)
    p = sub.add_parser("callees", help="what this method calls directly")
    p.add_argument("name")
    p = sub.add_parser("path", help="shortest call/reference path from A to B")
    p.add_argument("a"); p.add_argument("b")
    p = sub.add_parser("explain", help="a node and its connections")
    p.add_argument("name"); p.add_argument("--all", action="store_true")
    p = sub.add_parser("uses", help="where a field or property name is read or written (no graph needed)")
    p.add_argument("name"); p.add_argument("--writes", action="store_true"); p.add_argument("--limit", type=int, default=60)
    a = ap.parse_args()

    if a.cmd == "status" or a.cmd is None:
        b = load_build()
        print("WC commit:    %s (%s)" % (b.get("commit", "not built"), b.get("ref", "")))
        print("source/:      %s" % ("present" if os.path.isdir(SOURCE) else "missing"))
        print("graph:        %s%s" % (graph_state(), (" (%s)" % b["graph_nodes"]) if b.get("graph_nodes") else ""))
        print("graphify:     %s" % (" ".join(graphify_cmd()) if graphify_cmd() else "not found"))
        return 0
    if a.cmd == "callers":
        return show(["affected", norm(a.name), "--relation", "calls", "--depth", str(a.depth)])
    if a.cmd == "callees":
        return show(["explain", norm(a.name), "--all"],
                    lambda ln: ("[calls]" in ln and "-->" in ln) or ln.startswith("Node:") or "Source:" in ln
                    or ln.startswith("No ") or "Retry" in ln or ln.startswith("  ") and "()" in ln and "[" not in ln)
    if a.cmd == "path":
        return show(["path", norm(a.a), norm(a.b)])
    if a.cmd == "explain":
        return show(["explain", norm(a.name)] + (["--all"] if a.all else []))
    if a.cmd == "uses":
        return uses(a.name, a.writes, a.limit)


if __name__ == "__main__":
    sys.exit(main())
