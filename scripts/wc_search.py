#!/usr/bin/env python3
"""Search the se-dev-weaponcore tables (data/*.json), and optionally the WeaponCore source.

Examples:
    python wc_search.py MaxTrajectory                 # definition fields whose path matches
    python wc_search.py "Smarts\\." --brief           # every guidance field, one line each
    python wc_search.py Aggressiveness --exact        # exact field name (case-sensitive)
    python wc_search.py "projectile.*shield" --desc   # also search comments
    python wc_search.py --enum GuidanceType           # values of an enum
    python wc_search.py --api Heat                    # WcApi / WcPbApi methods
    python wc_search.py --settings Override           # server/client config fields
    python wc_search.py --src "DesiredSpeed"          # git grep the WeaponCore clone at the built commit

Patterns are case-insensitive regular expressions on the modder-facing path (ammo paths start at
`AmmoDef`). Output per field: C# type, ProtoMember number, an example value and comment from
WeaponCore's own CoreParts, where the runtime code reads it, and the lines that compare it with
0/-1 or clamp it (these decide what an unset field means; definition fields have no defaults).
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
DATA = os.path.join(SKILL, "data")
NOT_BUILT = ("The se-dev-weaponcore tables have not been generated yet. Run once:\n"
             "    python %s --repo PATH/TO/WeaponCore" % os.path.join(HERE, "refresh.py"))


def load(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        sys.exit(NOT_BUILT)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_build():
    try:
        with open(os.path.join(DATA, "build.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def show_field(r, brief, sites):
    typ = r["type"] + ("  (enum %s)" % r["enum"] if r.get("enum") else "")
    if brief:
        ex = r.get("examples") or []
        print("%-70s %-28s proto %-3s %s" % (r["path"], r["type"], r.get("proto"),
                                             ("e.g. " + ex[0][0][:30]) if ex else ""))
        return
    print(r["path"])
    print("  type:     %s   proto %s" % (typ, r.get("proto")))
    print("  declared: %s:%d%s" % (r["file"], r["line"],
                                   ("   (mod copy Api/CoreSystemsApiDefs.cs:%d)" % r["api_line"]) if r.get("api_line") else
                                   "   (NOT in mod copy Api/CoreSystemsApiDefs.cs)"))
    if r.get("comment"):
        print("  decl:     // %s" % r["comment"])
    ex = r.get("examples") or []
    if ex:
        print("  example:  %s" % "; ".join("%s (%s:%d)" % (v[:60], f, l) for v, f, l in ex[:3]) +
              (" +%d more" % (len(ex) - 3) if len(ex) > 3 else ""))
    if r.get("parts_comment"):
        print("  parts:    // %s" % r["parts_comment"])
    if r.get("struct"):
        print("  holds:    %s (search \"%s\\.\" for its fields)" % (r["struct"], re.escape(r["path"])))
    n = r.get("reads", 0)
    loose = " (loose match: field name in files that name the parent)" if r.get("reads_loose") else ""
    print("  reads:    %d%s%s" % (n, loose, (": " + ", ".join(r["read_sites"][:sites])) if n else
                                  "  (no direct read found; try wc_graph.py uses %s)" % r["field"]))
    for h in r.get("rule_hints", [])[:sites]:
        print("  rule?:    %s  %s" % (h["at"], h["code"][:120]))
    print()


def src_grep(pattern, repo, ref, limit):
    cmd = ["git", "-C", repo, "grep", "-n", "-I", "-E", "-i", pattern, ref, "--", "Data/Scripts"]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode not in (0, 1):
        print(out.stderr.strip(), file=sys.stderr)
        return out.returncode
    lines = out.stdout.splitlines()
    pre = ref + ":Data/Scripts/CoreSystems/"
    for ln in lines[:limit]:
        print(ln[len(pre):] if ln.startswith(pre) else ln)
    if len(lines) > limit:
        print("... %d more (raise --limit)" % (len(lines) - limit))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pattern", nargs="?", help="regex on the field path (case-insensitive)")
    ap.add_argument("--exact", action="store_true", help="exact field name, case-sensitive")
    ap.add_argument("--desc", action="store_true", help="also match declaration and CoreParts comments")
    ap.add_argument("--brief", action="store_true", help="one line per field")
    ap.add_argument("--sites", type=int, default=4, help="read sites / rule lines to show per field")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--enum", metavar="REGEX", help="show enums whose name matches")
    ap.add_argument("--api", metavar="REGEX", help="WcApi and WcPbApi methods whose name or key matches")
    ap.add_argument("--settings", metavar="REGEX", help="server/client settings fields whose class or name matches")
    ap.add_argument("--src", metavar="REGEX", help="git grep the WeaponCore source instead")
    ap.add_argument("--repo", help="WeaponCore clone for --src (default: the one the tables came from, or WC_REPO)")
    ap.add_argument("--ref", help="git ref for --src (default: the commit the tables came from)")
    ap.add_argument("--version", action="store_true", help="print which WeaponCore commit the tables came from")
    a = ap.parse_args()

    if a.src:
        b = load_build()
        repo = a.repo or os.environ.get("WC_REPO") or b.get("repo")
        ref = a.ref or b.get("commit")
        if not repo or not ref:
            sys.exit(NOT_BUILT)
        return src_grep(a.src, repo, ref, a.limit)

    b = load_build()
    if not b:
        sys.exit(NOT_BUILT)
    if a.version or not (a.pattern or a.enum or a.api or a.settings):
        print("Tables built from WeaponCore ModVersion %s, %s commit %s (%s): %s fields, %s enums, "
              "%s WcApi + %s WcPbApi methods." % (b.get("mod_version", "?"), b.get("ref"), b.get("commit"), b.get("date"),
                                                   b.get("fields"), b.get("enums"), b.get("api_methods"), b.get("pb_api_methods")))
        if not (a.pattern or a.enum or a.api or a.settings):
            return 0

    found = 0
    if a.enum:
        rx = re.compile(a.enum, re.I)
        for full, e in load("enums.json").items():
            if rx.search(full):
                found += 1
                print("%s  (%s:%d)" % (full, e["file"], e["line"]))
                print("  " + ", ".join("%s=%s" % (v["name"], v["value"]) for v in e["values"]))
                print()
    if a.api:
        rx = re.compile(a.api, re.I)
        api = load("api.json")
        for kind, label in (("client", "WcApi"), ("pb", "WcPbApi")):
            for m in api[kind]["methods"]:
                if rx.search(m["name"]) or rx.search(m.get("key") or ""):
                    found += 1
                    print("%s.%s  (%s:%d)" % (label, m["name"], api[kind]["file"], m["line"]))
                    print("  %s" % m["signature"])
                    be = None
                    for dname, entries in api["backend"].items():
                        if m.get("key") in entries:
                            e = entries[m["key"]]
                            be = "%s[\"%s\"] -> %s (Api/ApiBackend.cs:%s)" % (dname, m["key"], e["method"], e.get("method_line") or e["line"])
                            break
                    print("  key:  %s" % (be or (m.get("key") or "(no delegate found)")))
                    if m.get("no_null_guard"):
                        print("  note: calls the delegate without ?. : throws if the API never arrived")
                    if m.get("doc"):
                        print("  doc:  %s" % m["doc"][:200])
                    print()
    if a.settings:
        rx = re.compile(a.settings, re.I)
        for t in load("settings.json"):
            for f in t["fields"]:
                if rx.search(t["type"]) or rx.search(f["name"]):
                    found += 1
                    print("%s.%s  %s  proto %s%s  (Definitions/SerializedConfigs/CoreSettings.cs:%d)" % (
                        t["type"], f["name"], f["type"], f["proto"], ("  = " + f["init"]) if f.get("init") else "", f["line"]))
    if a.pattern:
        recs = load("fields.json")
        rx = re.compile(a.pattern, re.I)
        hits = []
        for r in recs:
            if a.exact:
                ok = r["field"] == a.pattern
            else:
                ok = bool(rx.search(r["path"]))
                if not ok and a.desc:
                    ok = bool(rx.search(r.get("comment") or "")) or bool(rx.search(r.get("parts_comment") or ""))
            if ok:
                hits.append(r)
        for r in hits[:a.limit]:
            show_field(r, a.brief, a.sites)
        if len(hits) > a.limit:
            print("... %d more matches (raise --limit or narrow the pattern)" % (len(hits) - a.limit))
        found += len(hits)
    if not found:
        print("No match. Field names are case-sensitive in C#; try a shorter regex, --desc, or --src for the code.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
