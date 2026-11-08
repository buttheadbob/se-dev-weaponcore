#!/usr/bin/env python3
"""Regenerate the se-dev-weaponcore field and API tables from a WeaponCore source tree.

Usage:
    python build_reference.py <wc-tree> [--commit SHA] [--date DATE] [--ref REF] [--out <skill-dir>]

Normally run through refresh.py, which exports a git ref first. <wc-tree> is the root of a
WeaponCore checkout or `git archive` export (the folder that holds `Data/Scripts/CoreSystems`).
The script only reads it. It writes `tables/*.md`, `data/fields.json`, `data/api.json`,
`data/enums.json` and `data/build.json` inside the skill folder (default: the folder above
this script).

Where each part comes from:
  * Definition classes: Definitions/CoreDefinitions.cs (what WeaponCore deserializes) and
    Api/CoreSystemsApiDefs.cs (the copy shipped for mods). Field name, C# type, ProtoMember
    number, nesting, and the path a modder writes (e.g. AmmoDef.Trajectory.Smarts.Aggressiveness).
  * Example values and comments: WeaponCore's own CoreParts (Coreparts/Definitions/*.cs), which
    are written the way a weapon mod writes its definitions.
  * Code that reads a field: every `.<Parent>.<Field>` in the runtime code, with the lines that
    compare it against 0/-1 or clamp it flagged, since those decide what 0 or empty means.
    The definition classes have no defaults of their own: an unset field is 0, false or null.
  * Server settings: Definitions/SerializedConfigs/CoreSettings.cs.
  * API: Api/CoreSystemsApiBase.cs (WcApi), Api/CoreSystemsPbApi.cs (WcPbApi), the keys they
    bind, and the backend method in Api/ApiBackend.cs that each key maps to.
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict, OrderedDict

SCRIPTS = "Data/Scripts/CoreSystems"
DEFS = "Definitions/CoreDefinitions.cs"
API_DEFS = "Api/CoreSystemsApiDefs.cs"
SETTINGS = "Definitions/SerializedConfigs/CoreSettings.cs"
PARTS_DIR = "Coreparts/Definitions"
API_CLIENT = "Api/CoreSystemsApiBase.cs"
API_PB = "Api/CoreSystemsPbApi.cs"
API_BACKEND = "Api/ApiBackend.cs"
ROOTS = ["WeaponDefinition", "ArmorDefinition", "UpgradeDefinition", "SupportDefinition",
         "ProjectileTagDefinition", "ProjectileTagAssignment"]
# Paths under these prefixes are shown the way a mod writes them as standalone definitions.
DISPLAY_ROOTS = [("WeaponDefinition.Ammos[]", "AmmoDef")]
PRIMITIVES = {"bool", "byte", "sbyte", "short", "ushort", "int", "uint", "long", "ulong", "float",
              "double", "decimal", "string", "char", "object"}
# Runtime code names a whole AmmoDef ammoDef, AmmoDef, ammo, fAmmo, patternAmmo...
PARENT_ALIASES = {"Ammos": r"(?:\w*[Aa]mmo\w*|a)"}
RUNTIME_EXCLUDE =(DEFS, API_DEFS, "Coreparts/")
HINT_RE = re.compile(r"(?:[<>]=?|[!=]=)\s*-?(?:0|1)(?:\.0+)?[fdD]?\b(?!\.)|\b-?(?:0|1)(?:\.0+)?[fd]?\s*(?:[<>]=?|[!=]=)"
                     r"|MathHelper\.Clamp|Math\.(?:Max|Min)|MathHelperD\.Clamp|\?\?|\?[^?.:]*:")


# ---------------------------------------------------------------- C# helpers

def read(path):
    with open(path, encoding="utf-8-sig", errors="replace") as f:
        return f.read()


def blank_comments_strings(text):
    """Same length as text; comments and string/char literals replaced by spaces (newlines kept)."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if text[k] != "\n":
                    out[k] = " "
            i = j
        elif c == '"' or c == "'":
            verbatim = c == '"' and i > 0 and text[i - 1] == "@"
            j = i + 1
            while j < n:
                if not verbatim and text[j] == "\\":
                    j += 2
                    continue
                if text[j] == c:
                    if verbatim and j + 1 < n and text[j + 1] == '"':
                        j += 2
                        continue
                    break
                if text[j] == "\n" and not verbatim:
                    break
                j += 1
            for k in range(i + 1, min(j, n)):
                if text[k] != "\n":
                    out[k] = " "
            i = j + 1
        else:
            i += 1
    return "".join(out)


def line_comment(raw_line):
    """Text after // outside of strings, or ''."""
    i, n, quote = 0, len(raw_line), None
    while i < n:
        c = raw_line[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif raw_line.startswith("//", i):
            return raw_line[i + 2:].lstrip("/").strip()
        i += 1
    return ""


def brace_depths(code):
    """Depth at the start of every line (code must have comments/strings blanked)."""
    depths, d = [], 0
    for ln in code.split("\n"):
        depths.append(d)
        d += ln.count("{") - ln.count("}")
    return depths


def match_brace(code, open_pos):
    d = 0
    for i in range(open_pos, len(code)):
        if code[i] == "{":
            d += 1
        elif code[i] == "}":
            d -= 1
            if d == 0:
                return i
    return len(code) - 1


TYPE_DECL = re.compile(r"\b(class|struct|enum)\s+([A-Za-z_]\w*)[^{;=()]*\{")
FIELD_RE = re.compile(
    r"^\s*(?:\[ProtoMember\((\d+)[^\]]*\)\]\s*)?(?:\[[^\]]*\]\s*)*"
    r"(?:(?:public|internal|private|protected|static|readonly|const|new)\s+)*"
    r"([A-Za-z_][\w\.]*(?:<[^;=()]*>)?(?:\[\s*,?\s*\])*\??)\s+([A-Za-z_]\w*)\s*(?:=\s*([^;]*))?;")


class TypeInfo:
    def __init__(self, kind, name, full, file, line, parent):
        self.kind, self.name, self.full, self.file, self.line, self.parent = kind, name, full, file, line, parent
        self.fields = []      # dicts
        self.values = []      # enum values
        self.children = {}


def parse_types(rel, text, strip_prefix=None):
    """Return {full_name: TypeInfo} for every class/struct/enum in the file."""
    code = blank_comments_strings(text)
    lines = text.split("\n")
    code_lines = code.split("\n")
    depths = brace_depths(code)
    line_starts = [0]
    for ln in lines:
        line_starts.append(line_starts[-1] + len(ln) + 1)

    def line_of(pos):
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1

    decls = []
    for m in TYPE_DECL.finditer(code):
        ob = m.end() - 1
        decls.append((m.start(), ob, match_brace(code, ob), m.group(1), m.group(2)))
    types = {}
    stack = []
    for start, ob, cb, kind, name in sorted(decls):
        while stack and stack[-1][1] < start:
            stack.pop()
        parent = stack[-1][0] if stack else None
        raw_full = (parent._raw + "." + name) if parent else name
        full = raw_full
        if strip_prefix and full.startswith(strip_prefix + "."):
            full = full[len(strip_prefix) + 1:]
        elif strip_prefix and full == strip_prefix:
            full = None
        t = TypeInfo(kind, name, full, rel, line_of(start), parent)
        t._span = (ob, cb)
        t._raw = raw_full
        if full:
            types[full] = t
        if parent is not None:
            parent.children[name] = t
        stack.append((t, cb))

    for t in types.values():
        ob, cb = t._span
        l0, l1 = line_of(ob), line_of(cb)
        body_depth = depths[l0 - 1] + code_lines[l0 - 1][:ob - line_starts[l0 - 1]].count("{") \
            - code_lines[l0 - 1][:ob - line_starts[l0 - 1]].count("}") + 1
        if t.kind == "enum":
            body = code[ob + 1:cb]
            pos = ob + 1
            idx = -1
            for part in body.split(","):
                nm = re.match(r"\s*([A-Za-z_]\w*)\s*(?:=\s*([^,]+))?\s*$", part)
                if nm:
                    if nm.group(2) is not None:
                        try:
                            idx = int(nm.group(2).strip(), 0)
                        except ValueError:
                            idx = nm.group(2).strip()
                    else:
                        idx = idx + 1 if isinstance(idx, int) else idx
                    p = pos + part.find(nm.group(1))
                    t.values.append({"name": nm.group(1), "value": idx, "line": line_of(p)})
                pos += len(part) + 1
            continue
        for ln_no in range(l0 + 1, l1):
            if depths[ln_no - 1] != body_depth:
                continue
            cl = code_lines[ln_no - 1]
            if re.search(r"\b(class|struct|enum)\b", cl):
                continue
            m = FIELD_RE.match(cl)
            if not m:
                continue
            ftype, fname = m.group(2), m.group(3)
            if ftype in ("return", "using", "throw", "else", "new"):
                continue
            raw = lines[ln_no - 1]
            init = None
            if m.group(4) is not None:
                # recover the initializer from the raw line (strings were blanked)
                rm = re.search(r"\b" + re.escape(fname) + r"\s*=\s*([^;]*);", raw)
                init = rm.group(1).strip() if rm else m.group(4).strip()
            t.fields.append({
                "name": fname, "type": ftype.replace(" ", ""), "proto": int(m.group(1)) if m.group(1) else None,
                "line": ln_no, "init": init, "comment": line_comment(raw),
                "commented_out": False,
            })
    return types


def element_type(ftype):
    t = ftype.rstrip("?")
    is_coll = t.endswith("[]") or t.startswith(("List<", "IList<", "HashSet<", "Dictionary<", "IDictionary<"))
    names = re.findall(r"[A-Za-z_][\w\.]*", t)
    names = [n for n in names if n not in ("List", "IList", "HashSet", "Dictionary", "IDictionary")]
    return (names[-1] if names else t), is_coll


def resolve(types, owner, name):
    """Resolve a type name as C# would from inside `owner` (a TypeInfo), else globally by simple name."""
    name = name.split(".")[-1] if "." in name and name not in types else name
    t = owner
    while t is not None:
        if name in t.children:
            return t.children[name]
        t = t.parent
    if name in types:
        return types[name]
    cands = [x for x in types.values() if x.name == name]
    return cands[0] if len(cands) == 1 else (cands[0] if cands else None)


# ---------------------------------------------------------------- definition paths

def walk_paths(types):
    """Every modder-facing path: list of records."""
    recs = []

    def walk(t, path, seen):
        for f in t.fields:
            if f["proto"] is None:
                continue  # not serialized (ProtoIgnore / runtime-only), a mod cannot set it
            ename, coll = element_type(f["type"])
            sub = None if ename in PRIMITIVES else resolve(types, t, ename)
            p = path + "." + f["name"] + ("[]" if coll and sub is not None and sub.kind != "enum" else "")
            disp = p
            for pre, rep in DISPLAY_ROOTS:
                if disp.startswith(pre + "."):
                    disp = rep + disp[len(pre):]
            r = {"path": disp, "full_path": p, "owner": t.full, "field": f["name"], "type": f["type"],
                 "proto": f["proto"], "file": t.file, "line": f["line"], "comment": f["comment"],
                 "init": f["init"], "enum": sub.full if sub is not None and sub.kind == "enum" else None,
                 "struct": sub.full if sub is not None and sub.kind != "enum" else None,
                 "kind": "struct" if t.kind == "struct" else "class"}
            recs.append(r)
            if sub is not None and sub.kind != "enum" and sub.full not in seen:
                walk(sub, p, seen | {sub.full})

    for root in ROOTS:
        if root in types:
            walk(types[root], root, {root})
    # de-duplicate by display path (AmmoDef reached once via WeaponDefinition.Ammos[])
    out, keys = [], set()
    for r in recs:
        if r["path"] in keys:
            continue
        keys.add(r["path"])
        out.append(r)
    return out


# ---------------------------------------------------------------- CoreParts examples

TOK = re.compile(r'"(?:\\.|[^"\\])*"|@"(?:""|[^"])*"|[A-Za-z_]\w*|\d+(?:\.\d+)?[fdmFDM]?|\S')


def parse_parts(tree, types, extra_dirs=()):
    """Map (owner type full name, field) -> {examples: [(value, file, line)], comment}.
    Reads WeaponCore's own CoreParts, then any extra CoreParts folders (a weapon mod's
    Data/Scripts/CoreParts), whose files are labelled `<folder name>/<file>`."""
    found = defaultdict(lambda: {"examples": [], "comments": []})
    jobs = []
    pdir = os.path.join(tree, SCRIPTS, PARTS_DIR)
    if os.path.isdir(pdir):
        jobs += [(os.path.join(pdir, fn), PARTS_DIR + "/" + fn) for fn in sorted(os.listdir(pdir)) if fn.endswith(".cs")]
    for d in extra_dirs:
        label = os.path.basename(os.path.normpath(d))
        for dp, _, fns in os.walk(d):
            for fn in sorted(fns):
                if fn.endswith(".cs"):
                    p = os.path.join(dp, fn)
                    jobs.append((p, "%s/%s" % (label, os.path.relpath(p, d).replace("\\", "/"))))
    for path, rel in jobs:
        text = read(path)
        stack = []          # entries: (TypeInfo|None, elem TypeInfo|None for arrays)
        pending = None
        for ln_no, raw in enumerate(text.split("\n"), 1):
            code = blank_comments_strings(raw)
            comment = line_comment(raw)
            # restore string contents for value capture
            toks = [m for m in TOK.finditer(raw) if code[m.start()] != " " or raw[m.start()] == '"']
            toks = [m for m in toks if m.start() < (len(raw) - len(raw.lstrip())) or code[m.start():m.end()].strip() or raw[m.start()] == '"']
            i = 0
            while i < len(toks):
                tk = toks[i].group(0)
                nxt = toks[i + 1].group(0) if i + 1 < len(toks) else None
                top = stack[-1] if stack else (None, None)
                if tk == "new" and nxt and re.match(r"[A-Za-z_]", nxt):
                    t = resolve(types, top[0] or top[1], nxt) if (top[0] or top[1]) else resolve(types, None, nxt)
                    is_arr = i + 2 < len(toks) and toks[i + 2].group(0) == "["
                    if t is not None:
                        pending = (None, t) if is_arr else (t, None)
                    i += 2
                    continue
                if tk == "new" and nxt == "[":
                    i += 1
                    continue
                if tk == "{":
                    if pending is not None:
                        stack.append(pending)
                    elif top[1] is not None:
                        stack.append((top[1], None))
                    else:
                        stack.append((None, None))
                    pending = None
                    i += 1
                    continue
                if tk == "}":
                    if stack:
                        stack.pop()
                    pending = None
                    i += 1
                    continue
                if re.match(r"[A-Za-z_]\w*$", tk) and nxt == "=" and (i + 2 >= len(toks) or toks[i + 2].group(0) not in ("=", ">")):
                    owner = top[0]
                    if owner is None and top[1] is None and not stack:
                        i += 1
                        continue
                    if owner is not None:
                        f = next((x for x in owner.fields if x["name"] == tk), None)
                        if f is not None:
                            ename, coll = element_type(f["type"])
                            sub = None if ename in PRIMITIVES else resolve(types, owner, ename)
                            rest = raw[toks[i + 1].end():]
                            rest_code = code[toks[i + 1].end():]
                            starts_new = re.match(r"\s*new\b", rest_code)
                            complex_sub = sub is not None and sub.kind != "enum"
                            if starts_new and complex_sub:
                                pending = (None, sub) if coll else (sub, None)
                            else:
                                val = rest
                                cpos = rest.find("//")
                                if cpos >= 0 and rest_code[cpos:cpos + 2].strip() == "":
                                    val = rest[:cpos]
                                val = val.strip().rstrip(",").strip()
                                if coll and val.startswith("new") and val.count("{") > val.count("}"):
                                    val += " ...}"
                                found[(owner.full, tk)]["examples"].append((val, rel, ln_no))
                                if comment:
                                    found[(owner.full, tk)]["comments"].append(comment)
                                # skip the rest of a one-line value; braces in it are balanced or handled
                                opened = rest_code.count("{") - rest_code.count("}")
                                if opened > 0:
                                    stack.append((None, None))
                                    for _ in range(opened - 1):
                                        stack.append((None, None))
                                elif opened < 0:
                                    for _ in range(-opened):
                                        if stack:
                                            stack.pop()
                                break
                    i += 2
                    continue
                i += 1
    return found


# ---------------------------------------------------------------- runtime reads

def runtime_files(tree):
    root = os.path.join(tree, SCRIPTS)
    out = []
    for dp, _, fns in os.walk(root):
        for fn in fns:
            if fn.endswith(".cs"):
                p = os.path.join(dp, fn)
                rel = os.path.relpath(p, root).replace("\\", "/")
                if rel.startswith(RUNTIME_EXCLUDE):
                    continue
                out.append((rel, read(p).split("\n")))
    return sorted(out)


def _scan(rx, files, file_filter=None):
    sites, hints = [], []
    for rel, lines in files:
        if file_filter is not None and not any(file_filter.search(ln) for ln in lines):
            continue
        for i, ln in enumerate(lines, 1):
            if rx.search(ln) and not ln.strip().startswith("//"):
                sites.append("%s:%d" % (rel, i))
                if HINT_RE.search(ln):
                    hints.append({"at": "%s:%d" % (rel, i), "code": ln.strip()[:160]})
    return sites, hints


def find_reads(recs, files, max_sites=12):
    """Qualified match `.<Parent>.<Field>` first. If that finds nothing (code often keeps a
    sub-definition in a local), fall back to `.<Field>` in files that also name the parent,
    and mark the result loose."""
    by_pattern = defaultdict(list)
    for r in recs:
        segs = [s.rstrip("[]") for s in r["full_path"].split(".")]
        parent = segs[-2] if len(segs) >= 3 else None
        if parent in PARENT_ALIASES:
            pat = r"\b" + PARENT_ALIASES[parent] + r"\s*\.\s*" + r["field"] + r"\b"
        elif parent:
            pat = r"\." + parent + r"\s*\.\s*" + r["field"] + r"\b"
        else:
            pat = r"\." + r["field"] + r"\b"
        by_pattern[(pat, parent, r["field"])].append(r)
    for (pat, parent, field), rs in by_pattern.items():
        sites, hints = _scan(re.compile(pat), files)
        loose = False
        if not sites and parent:
            sites, hints = _scan(re.compile(r"\.\s*" + field + r"\b"), files, re.compile(r"\b" + parent + r"\b"))
            loose = bool(sites)
        for r in rs:
            r["reads"] = len(sites)
            r["read_sites"] = sites[:max_sites]
            r["rule_hints"] = hints[:max_sites]
            r["read_pattern"] = pat
            r["reads_loose"] = loose


# ---------------------------------------------------------------- API

PUB_METHOD = re.compile(r"^\s*public\s+(?:static\s+|virtual\s+|override\s+)*([\w<>\[\],\.\s\?]+?)\s+(\w+)\s*\((.*)$")


def parse_api_client(tree, rel):
    path = os.path.join(tree, SCRIPTS, rel)
    if not os.path.exists(path):
        return {"file": rel, "methods": [], "bindings": {}}
    text = read(path)
    lines = text.split("\n")
    code_lines = blank_comments_strings(text).split("\n")
    bindings = {}
    for i, ln in enumerate(lines, 1):
        m = re.search(r'AssignMethod\(\s*\w+\s*,\s*"([^"]+)"\s*,\s*ref\s+(\w+)\s*\)', ln)
        if m:
            bindings[m.group(2)] = {"key": m.group(1), "line": i}
    methods = []
    i = 0
    while i < len(lines):
        m = PUB_METHOD.match(code_lines[i])
        if m and m.group(2) not in ("if", "while") and "class " not in code_lines[i]:
            sig = lines[i].strip()
            j = i
            while ")" not in blank_comments_strings(sig) and j + 1 < len(lines) and j - i < 6:
                j += 1
                sig += " " + lines[j].strip()
            body = " ".join(lines[i:min(len(lines), j + 12)])
            # stop the body at the next public member
            nxt = [k for k in range(i + 1, min(len(lines), j + 12)) if PUB_METHOD.match(code_lines[k])]
            if nxt:
                body = " ".join(lines[i:nxt[0]])
            fields = re.findall(r"\b(_\w+)\s*(?:\?\.\s*Invoke|\.Invoke|\()", body)
            fields = [f for f in fields if f in bindings] or fields
            sig_clean = re.sub(r"\s*(=>|\{).*$", "", sig).strip()
            no_null_guard = bool(fields) and not re.search(re.escape(fields[0]) + r"\s*\?\.", body) \
                and not re.search(re.escape(fields[0]) + r"\s*==\s*null|" + re.escape(fields[0]) + r"\s*!=\s*null", body)
            doc = []
            k = i - 1
            while k >= 0 and lines[k].strip().startswith("///"):
                doc.insert(0, re.sub(r"</?\w+[^>]*>", "", lines[k].strip()[3:]).strip())
                k -= 1
            methods.append({"name": m.group(2), "signature": sig_clean, "line": i + 1,
                            "delegate": fields[0] if fields else None,
                            "key": bindings.get(fields[0], {}).get("key") if fields else None,
                            "key_line": bindings.get(fields[0], {}).get("line") if fields else None,
                            "no_null_guard": no_null_guard,
                            "doc": " ".join(d for d in doc if d)})
            i = j + 1
            continue
        i += 1
    return {"file": rel, "methods": methods, "bindings": bindings}


def parse_backend(tree):
    path = os.path.join(tree, SCRIPTS, API_BACKEND)
    if not os.path.exists(path):
        return {}
    text = read(path)
    lines = text.split("\n")
    dicts = defaultdict(dict)
    current = None
    for i, ln in enumerate(lines, 1):
        d = re.search(r"(\w+)\s*=\s*new\s+Dictionary<string,\s*Delegate>", ln)
        if d:
            current = d.group(1)
        m = re.search(r'\["([^"]+)"\]\s*=\s*new\s+([^\(]+(?:\([^\)]*\))?[^\(]*)\((\w+)\)', ln)
        if not m:
            m = re.search(r'\["([^"]+)"\]\s*=\s*new\s+(.+)\((\w+)\)\s*,?\s*$', ln)
        if m and current:
            dicts[current][m.group(1)] = {"type": m.group(2).strip(), "method": m.group(3), "line": i}
    defs = {}
    for i, ln in enumerate(lines, 1):
        m = re.match(r"^\s*(?:private|internal|public|protected)\s+(?:static\s+)?[\w<>\[\],\.\s\?]+?\s+(\w+)\s*\(", ln)
        if m and m.group(1) not in defs:
            defs[m.group(1)] = i
    for dname, entries in dicts.items():
        for k, e in entries.items():
            e["method_line"] = defs.get(e["method"])
    return dicts


# ---------------------------------------------------------------- markdown

def md(s):
    if s is None:
        return ""
    s = str(s).replace("|", "\\|").replace("\n", " ")
    return s


def short(s, n=140):
    s = re.sub(r"\s+", " ", s or "").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


SECTIONS = [
    ("WeaponDefinition-Assignments", "WeaponDefinition.Assignments", "Model assignments: mount points, subparts, muzzles"),
    ("WeaponDefinition-Targeting", "WeaponDefinition.Targeting", "Targeting: threats, subsystems, ranges"),
    ("WeaponDefinition-HardPoint", "WeaponDefinition.HardPoint", "Hardpoint: aiming, AI flags, hardware, loading, audio, graphics"),
    ("WeaponDefinition-Animations", "WeaponDefinition.Animations", "Animations and heat-up/emissive events"),
    ("WeaponDefinition-Other", "WeaponDefinition", "Top-level WeaponDefinition fields"),
    ("AmmoDef", "AmmoDef", "Ammo: damage, trajectory, guidance, area damage, fragments, patterns, EWAR, graphics"),
    ("ArmorDefinition", "ArmorDefinition", "Armor definitions"),
    ("UpgradeDefinition", "UpgradeDefinition", "Upgrade definitions"),
    ("SupportDefinition", "SupportDefinition", "Support definitions"),
    ("ProjectileTags", "ProjectileTag", "Projectile tag definitions and assignments"),
]


def section_of(path):
    for fname, prefix, _ in SECTIONS:
        if prefix == "WeaponDefinition":
            if path.count(".") == 1 and path.startswith("WeaponDefinition."):
                return fname
            continue
        if path == prefix or path.startswith(prefix + ".") or path.startswith(prefix + "[]") or (prefix == "ProjectileTag" and path.startswith(prefix)):
            return fname
    return "WeaponDefinition-Other"


def write_tables(out_tables, recs, enums, settings, api, diffs, stamp):
    os.makedirs(out_tables, exist_ok=True)
    for fn in os.listdir(out_tables):
        if fn.endswith(".md"):
            os.remove(os.path.join(out_tables, fn))
    groups = defaultdict(list)
    for r in recs:
        groups[section_of(r["path"])].append(r)
    idx = [("# WeaponCore definition and API tables\n\n%s\n\n"
            "Paths are what a weapon mod writes in its CoreParts (`Data/Scripts/CoreParts/*.cs`). "
            "Ammo is written as standalone `AmmoDef` objects and listed in `WeaponDefinition.Ammos`, "
            "so ammo paths start at `AmmoDef`.\n\n"
            "**Definition fields have no defaults of their own.** They are protobuf fields: anything "
            "a mod leaves out arrives as 0, false, null or the first enum value. What 0 or empty then "
            "means is decided by the code that reads it; the `rule hints` column points at the lines "
            "that compare the field against 0/-1, clamp it, or fall back to another value. "
            "`references/definitions.md` lists those rules.\n\n"
            "Columns: `proto` = ProtoMember number; `example` = a value from WeaponCore's own CoreParts "
            "(`Coreparts/Definitions/`), with its comment; `reads` = lines in the runtime code matching "
            "`.<Parent>.<Field>` (a lead, not complete: code that stores a sub-definition in a local "
            "first is missed; use `wc_graph.py uses <Field>` for every mention).\n\n"
            "| Table | Fields | What |\n|---|---|---|\n") % stamp]
    for fname, prefix, what in SECTIONS:
        rs = groups.get(fname, [])
        if not rs:
            continue
        idx.append("| [%s](%s.md) | %d | %s |\n" % (fname, fname, len(rs), what))
        lines = ["# %s\n\n%s\n\n%s.\n\n" % (fname, stamp, what),
                 "| Path | Type | proto | Example (CoreParts) | Comment | Reads | Rule hints | Declared |\n",
                 "|---|---|---|---|---|---|---|---|\n"]
        for r in rs:
            ex = r.get("examples") or []
            exs = "; ".join("`%s`" % short(v, 50) for v, _, _ in ex[:2])
            if ex:
                exs += " (%s:%d)" % (ex[0][1], ex[0][2])
            if len(ex) > 2:
                exs += " +%d more" % (len(ex) - 2)
            com = r.get("parts_comment") or r.get("comment") or ""
            typ = r["type"] + (" (enum)" if r.get("enum") else "")
            hints = "<br>".join("%s `%s`" % (h["at"], short(h["code"], 90)) for h in r.get("rule_hints", [])[:3])
            if len(r.get("rule_hints", [])) > 3:
                hints += "<br>+%d more" % (len(r["rule_hints"]) - 3)
            reads = str(r.get("reads", 0)) + (" (loose)" if r.get("reads_loose") else "")
            if r.get("read_sites"):
                reads += ": " + ", ".join(r["read_sites"][:2])
            lines.append("| `%s` | `%s` | %s | %s | %s | %s | %s | %s:%d |\n" % (
                r["path"], md(typ), r["proto"] if r["proto"] is not None else "", md(exs), md(short(com, 160)),
                md(reads), md(hints), r["file"], r["line"]))
        with open(os.path.join(out_tables, fname + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.writelines(lines)

    # enums
    el = ["# Enums used by definitions and settings\n\n%s\n\nAn enum field a mod leaves out is the value "
          "numbered 0. Names are written as C# identifiers in CoreParts.\n\n" % stamp]
    for full in sorted(enums):
        e = enums[full]
        el.append("## %s\n\n`%s:%d`\n\n" % (full, e["file"], e["line"]))
        el.append(", ".join("`%s`=%s" % (v["name"], v["value"]) for v in e["values"]) + "\n\n")
    with open(os.path.join(out_tables, "ENUMS.md"), "w", encoding="utf-8", newline="\n") as f:
        f.writelines(el)
    idx.append("| [ENUMS](ENUMS.md) | %d enums | Allowed values of every enum field |\n" % len(enums))

    # settings
    sl = ["# Server and client settings classes\n\n%s\n\nFrom `%s`. Initializers shown where the class "
          "sets one; otherwise the starting values are set elsewhere (see references/config-controls.md).\n\n" % (stamp, SETTINGS),
          "| Class | Field | Type | proto | Initializer | Line |\n|---|---|---|---|---|---|\n"]
    n = 0
    for t in settings:
        for f in t["fields"]:
            sl.append("| `%s` | `%s` | `%s` | %s | %s | %s:%d |\n" % (
                t["type"], f["name"], md(f["type"]), f["proto"] if f["proto"] is not None else "",
                md(short(f["init"] or "", 60)), SETTINGS, f["line"]))
            n += 1
    with open(os.path.join(out_tables, "SETTINGS.md"), "w", encoding="utf-8", newline="\n") as f:
        f.writelines(sl)
    idx.append("| [SETTINGS](SETTINGS.md) | %d fields | Server/client config classes (`CoreSettings.cs`) |\n" % n)

    # api
    for key, title, fname in (("client", "WcApi (mod scripts)", "API"), ("pb", "WcPbApi (programmable block scripts)", "PBAPI")):
        a = api[key]
        backend = api["backend"]
        al = ["# %s\n\n%s\n\nWrapper: `%s`. Backend: `%s`. `key` is the delegate dictionary key the wrapper binds; "
              "`backend` is the method that key maps to in the backend dictionary. "
              "`throws if absent` marks wrappers that call the delegate without `?.`, so they throw a "
              "NullReferenceException when the API never arrived.\n\n" % (title, stamp, a["file"], API_BACKEND),
              "| Method | Signature | key | backend | throws if absent | Wrapper line | Doc |\n|---|---|---|---|---|---|---|\n"]
        for m in a["methods"]:
            be = ""
            if m.get("key"):
                for dname, entries in backend.items():
                    if m["key"] in entries:
                        e = entries[m["key"]]
                        be = "%s → `%s` (%s:%s)" % (dname, e["method"], API_BACKEND, e.get("method_line") or e["line"])
                        break
                if not be:
                    be = "**key not in backend**"
            al.append("| `%s` | `%s` | %s | %s | %s | %s:%d | %s |\n" % (
                m["name"], md(short(m["signature"], 200)), ("`%s`" % m["key"]) if m.get("key") else "",
                md(be), "yes" if m.get("no_null_guard") else "", a["file"], m["line"], md(short(m.get("doc"), 120))))
        unbound = sorted(set(b["key"] for b in a["bindings"].values()) -
                         set(m["key"] for m in a["methods"] if m.get("key")))
        if unbound:
            al.append("\nKeys bound but used by no public method (internal helpers or events): %s\n" %
                      ", ".join("`%s`" % k for k in unbound))
        with open(os.path.join(out_tables, fname + ".md"), "w", encoding="utf-8", newline="\n") as f:
            f.writelines(al)
        idx.append("| [%s](%s.md) | %d methods | %s: signature, key, backend method |\n" % (fname, fname, len(a["methods"]), title))

    # backend keys not in any wrapper
    bl = ["# Backend delegate dictionaries\n\n%s\n\nEvery key WeaponCore publishes, by dictionary, from `%s`.\n\n" % (stamp, API_BACKEND)]
    used = set(m["key"] for k in ("client", "pb") for m in api[k]["methods"] if m.get("key"))
    used |= set(b["key"] for k in ("client", "pb") for b in api[k]["bindings"].values())
    for dname, entries in api["backend"].items():
        bl.append("## %s (%d keys)\n\n| Key | Delegate type | Method | In a wrapper |\n|---|---|---|---|\n" % (dname, len(entries)))
        for k, e in entries.items():
            bl.append("| `%s` | `%s` | `%s` (%s:%s) | %s |\n" % (k, md(short(e["type"], 120)), e["method"], API_BACKEND,
                                                         e.get("method_line") or e["line"], "yes" if k in used else "**no**"))
        bl.append("\n")
    with open(os.path.join(out_tables, "BACKEND.md"), "w", encoding="utf-8", newline="\n") as f:
        f.writelines(bl)
    idx.append("| [BACKEND](BACKEND.md) | %d keys | Every published API key and its backend method |\n" %
               sum(len(e) for e in api["backend"].values()))

    # differences
    dl = ["# Differences between the server and mod-side definition classes\n\n%s\n\n"
          "WeaponCore deserializes with `%s` (namespace CoreSystems.Support). Mods compile against "
          "their own copy, shipped as `%s` (class WcApiDef). A field present in only one copy, or with a "
          "different ProtoMember number or type, does not reach WeaponCore as written.\n\n" % (stamp, DEFS, API_DEFS)]
    if not diffs:
        dl.append("No differences in field names, types or ProtoMember numbers.\n")
    else:
        dl.append("| Type | Field | Server (%s) | Mod copy (%s) |\n|---|---|---|---|\n" % (DEFS, API_DEFS))
        for d in diffs:
            dl.append("| `%s` | `%s` | %s | %s |\n" % (d["type"], d["field"], md(d["server"]), md(d["api"])))
    with open(os.path.join(out_tables, "DIFFERENCES.md"), "w", encoding="utf-8", newline="\n") as f:
        f.writelines(dl)
    idx.append("| [DIFFERENCES](DIFFERENCES.md) | %d | Server vs mod-side definition copy |\n" % len(diffs))

    with open(os.path.join(out_tables, "INDEX.md"), "w", encoding="utf-8", newline="\n") as f:
        f.writelines(idx)


# ---------------------------------------------------------------- main

def compare_defs(server, api):
    diffs = []
    for full, t in server.items():
        if t.kind == "enum":
            a = api.get(full)
            if a is None:
                diffs.append({"type": full, "field": "(enum)", "server": "present", "api": "missing"})
                continue
            sv = [(v["name"], v["value"]) for v in t.values]
            av = [(v["name"], v["value"]) for v in a.values]
            if sv != av:
                only_s = [n for n in sv if n not in av]
                only_a = [n for n in av if n not in sv]
                diffs.append({"type": full, "field": "(enum values)",
                              "server": "only here: " + ", ".join("%s=%s" % x for x in only_s) if only_s else "",
                              "api": "only here: " + ", ".join("%s=%s" % x for x in only_a) if only_a else ""})
            continue
        a = api.get(full)
        if a is None:
            if t.fields:
                diffs.append({"type": full, "field": "(type)", "server": "present (%s:%d)" % (t.file, t.line), "api": "missing"})
            continue
        af = {f["name"]: f for f in a.fields if f["proto"] is not None}
        sf = {f["name"]: f for f in t.fields if f["proto"] is not None}
        for n, f in sf.items():
            g = af.get(n)
            if g is None:
                diffs.append({"type": full, "field": n, "server": "%s proto %s (line %d)" % (f["type"], f["proto"], f["line"]), "api": "missing"})
            elif g["proto"] != f["proto"] or g["type"] != f["type"]:
                diffs.append({"type": full, "field": n, "server": "%s proto %s (line %d)" % (f["type"], f["proto"], f["line"]),
                              "api": "%s proto %s (line %d)" % (g["type"], g["proto"], g["line"])})
        for n, g in af.items():
            if n not in sf:
                diffs.append({"type": full, "field": n, "server": "missing", "api": "%s proto %s (line %d)" % (g["type"], g["proto"], g["line"])})
    for full, a in api.items():
        if full not in server and (a.fields or a.values):
            diffs.append({"type": full, "field": "(type)", "server": "missing", "api": "present (%s:%d)" % (a.file, a.line)})
    return diffs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tree")
    ap.add_argument("--commit", default="")
    ap.add_argument("--date", default="")
    ap.add_argument("--ref", default="")
    ap.add_argument("--parts", action="append", default=[], metavar="DIR",
                    help="extra CoreParts folder(s) from a weapon mod, for more example values and comments")
    ap.add_argument("--out", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    a = ap.parse_args()
    src = os.path.join(a.tree, SCRIPTS)
    for p in (DEFS, API_CLIENT):
        if not os.path.exists(os.path.join(src, p)):
            sys.exit("%s not found under %s. Is this the WeaponCore repository?" % (p, a.tree))

    server = parse_types(DEFS, read(os.path.join(src, DEFS)))
    api_types = parse_types(API_DEFS, read(os.path.join(src, API_DEFS)), strip_prefix="WcApiDef") \
        if os.path.exists(os.path.join(src, API_DEFS)) else {}
    recs = walk_paths(server)
    api_lines = {}
    for full, t in api_types.items():
        for f in t.fields:
            api_lines[(full, f["name"])] = f["line"]
    parts = parse_parts(a.tree, server, a.parts)
    for r in recs:
        r["api_line"] = api_lines.get((r["owner"], r["field"]))
        p = parts.get((r["owner"], r["field"]))
        if p:
            seen, ex = set(), []
            for v, f, l in p["examples"]:
                if v not in seen:
                    seen.add(v)
                    ex.append((v, f, l))
            r["examples"] = ex
            r["example_count"] = len(p["examples"])
            cs = [c for c in p["comments"] if c]
            r["parts_comment"] = max(cs, key=len) if cs else ""
    files = runtime_files(a.tree)
    find_reads(recs, files)

    enums = {}
    for full, t in server.items():
        if t.kind == "enum":
            enums[full] = {"file": t.file, "line": t.line, "values": t.values}
    settings_types = []
    if os.path.exists(os.path.join(src, SETTINGS)):
        st = parse_types(SETTINGS, read(os.path.join(src, SETTINGS)))
        for full, t in sorted(st.items(), key=lambda kv: kv[1].line):
            if t.kind == "enum":
                enums["Settings." + full] = {"file": t.file, "line": t.line, "values": t.values}
            elif t.fields:
                settings_types.append({"type": full, "line": t.line, "fields": t.fields})

    api = {"client": parse_api_client(a.tree, API_CLIENT), "pb": parse_api_client(a.tree, API_PB),
           "backend": parse_backend(a.tree)}
    diffs = compare_defs(server, api_types) if api_types else []

    version = ""
    sf = os.path.join(src, "Session/SessionFields.cs")
    if os.path.exists(sf):
        m = re.search(r"const\s+int\s+ModVersion\s*=\s*(\d+)", read(sf))
        version = m.group(1) if m else ""

    stamp = ("Generated by scripts/build_reference.py from WeaponCore (ModVersion %s), `%s` commit `%s` (%s). "
             "Do not edit by hand." % (version or "?", a.ref or "?", a.commit or "?", a.date or "?"))
    write_tables(os.path.join(a.out, "tables"), recs, enums, settings_types, api, diffs, stamp)

    data = os.path.join(a.out, "data")
    os.makedirs(data, exist_ok=True)
    with open(os.path.join(data, "fields.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(recs, f, indent=0)
    with open(os.path.join(data, "enums.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(enums, f, indent=0)
    with open(os.path.join(data, "api.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(api, f, indent=0)
    with open(os.path.join(data, "settings.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(settings_types, f, indent=0)
    build = {"mod_version": version, "ref": a.ref, "commit": a.commit, "date": a.date,
             "fields": len(recs), "enums": len(enums),
             "api_methods": len(api["client"]["methods"]), "pb_api_methods": len(api["pb"]["methods"]),
             "backend_keys": sum(len(e) for e in api["backend"].values()),
             "def_differences": len(diffs),
             "fields_with_examples": sum(1 for r in recs if r.get("examples")),
             "extra_parts": [os.path.abspath(d) for d in a.parts]}
    old = {}
    bp = os.path.join(data, "build.json")
    if os.path.exists(bp):
        try:
            old = json.load(open(bp, encoding="utf-8"))
        except ValueError:
            old = {}
    for k in ("repo", "graph_nodes", "graphify_cmd"):
        if k in old:
            build[k] = old[k]
    with open(bp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(build, f, indent=1)
    print("%d fields (%d with CoreParts examples), %d enums, %d WcApi + %d WcPbApi methods, %d backend keys, %d def differences."
          % (len(recs), build["fields_with_examples"], len(enums), build["api_methods"], build["pb_api_methods"],
             build["backend_keys"], len(diffs)))


if __name__ == "__main__":
    main()
