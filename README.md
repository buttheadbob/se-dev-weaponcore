# se-dev-weaponcore

A [Claude Code](https://claude.com/claude-code) skill for
[WeaponCore](https://github.com/Ash-LikeSnow/WeaponCore) (CoreSystems), the Space Engineers 1
weapons framework mod.

WeaponCore weapons are defined in C# (`Data/Scripts/CoreParts` in each weapon mod) as hundreds
of protobuf fields with no defaults of their own. A field a mod leaves out arrives as 0, false or
null. What that means then depends on the code that reads it: sometimes "off", sometimes
"unlimited", sometimes zero damage. This skill lets Claude answer WeaponCore questions from the
WeaponCore source code instead of from memory:
- exact field names, types and ProtoMember numbers;
- where each field is read, and what 0 or unset does;
- how definitions load and override each other;
- how targeting, firing, projectiles and damage work;
- how to call the WcApi and WcPbApi scripting APIs.

This repository holds only the skill's own files: instructions, hand-written reference notes and
scripts. The field tables, the source mirror and the code graph are **generated on your machine
from your own clone of WeaponCore**. See [Credits and licences](#credits-and-licences).

## What it covers

- **Every definition field** (about 1,100 at WeaponCore ModVersion 29) in WeaponDefinition
  (Assignments, Targeting, HardPoint, Animations), AmmoDef (damage scales, trajectory, guidance,
  area damage, fragments, patterns, EWAR, graphics), ArmorDefinition, UpgradeDefinition,
  SupportDefinition and projectile tags. Each row gives:
  - the path a mod writes, its C# type and ProtoMember number;
  - an example value and comment from WeaponCore's own CoreParts;
  - the runtime lines that read it;
  - the lines that compare it with 0/-1, clamp it or fall back to another value.
- **Every enum** and its numbered values.
- **The server/client settings** classes.
- **Server vs mod-side differences:** fields and enum values where the definition copy shipped
  for mods differs from the one WeaponCore deserializes.
- **The scripting APIs:** every WcApi and WcPbApi method, the delegate key it binds, and the
  backend method that key runs.
- **How it works** (`references/`, written against ModVersion 29, commit `25985a9`):
  - definitions: loading, priority, multi-weapon blocks, ammo linking, per-field zero/clamp/derived
    rules, setup mistakes;
  - api: handshake, every method's real behaviour, callbacks, how MES uses it;
  - combat: targeting, aiming, firing, heat, reload, projectiles and guidance, damage and armor,
    EWAR;
  - config-controls: server and client config, overrides, chat commands, terminal controls and
    actions, vanilla weapon replacement, integrations, logs.

  Every claim cites `file:line` in the WeaponCore source.
- **A code graph** (optional, via Graphify) for "what calls this", "what does this call" and "how
  does A reach B".

## Requirements

- Claude Code.
- Python 3.8 or newer (standard library only), or [uv](https://docs.astral.sh/uv/).
- git.
- A local git clone of WeaponCore:
  ```bash
  git clone https://github.com/Ash-LikeSnow/WeaponCore.git
  ```
  The scripts only read it (with `git archive`). They never check out, reset or change anything
  in it.

## Install

Claude Code loads skills from a `skills` folder. Put this repository there under the name
`se-dev-weaponcore`.

For you, in every project:

```bash
git clone https://github.com/buttheadbob/se-dev-weaponcore.git ~/.claude/skills/se-dev-weaponcore
```

On Windows, `~` is `%USERPROFILE%` (for example `C:\Users\you\.claude\skills\se-dev-weaponcore`).

For one project only (shared with everyone who works on it), run this from the project root:

```bash
git clone https://github.com/buttheadbob/se-dev-weaponcore.git .claude/skills/se-dev-weaponcore
```

Start a new Claude Code session afterwards so it picks up the skill.

## Generate the tables (once)

From the skill folder, point the generator at your WeaponCore clone:

```bash
python scripts/refresh.py --repo /path/to/WeaponCore
```

With uv instead of a system Python:

```bash
uv run scripts/refresh.py --repo /path/to/WeaponCore
```

This takes a few seconds, plus about a minute for the code graph. It writes these folders, all
in `.gitignore`:

- `tables/`: Markdown tables per definition section, plus enums, settings, API and differences.
- `data/`: the JSON the search helper reads, and `build.json` with the WeaponCore commit.
- `source/`: the WeaponCore scripts at that commit, with WeaponCore's licence beside them.
- `graph/`: the code graph, if Graphify is installed (see below).

The clone path and ref are saved in `data/build.json`, so later runs need no arguments.

By default it builds from `origin/master`. Use `--ref` for anything else, for example
`--ref upstream/master` if your clone is a fork that tracks Ash-LikeSnow as `upstream`.

`--parts /path/to/SomeWeaponMod/Data/Scripts/CoreParts` (repeatable) adds a weapon mod's
CoreParts as a further source of example values and comments. This helps because WeaponCore's
own parts don't use every field.

### Optional: the code graph

With [Graphify](https://pypi.org/project/graphifyy/) installed, the same step builds a graph of
WeaponCore's classes, methods and calls. Install it once:

```bash
uv tool install --python 3.12 "graphifyy[leiden]"
```

Then run `refresh.py` again. It builds the graph automatically when `graphify` is on your PATH,
in about a minute for WeaponCore's ~170 files (about 5,000 nodes). The build is code-only: local
parsing, no LLM calls and no API key.
- `--graph yes` builds through `uvx` without a permanent install.
- `--graph no` skips it.
- `SE_DEV_GRAPHIFY=1` / `0` does the same, as in the other se-dev skills.

Without Graphify everything else works. `scripts/wc_graph.py uses <name>`, which finds where a
field or property is read or written, needs only `source/`.

## Refresh after WeaponCore updates

```bash
python scripts/refresh.py --fetch origin
```

This fetches, rebuilds the tables at the new commit, and prints which WeaponCore code files
changed since the last build. The notes in `references/` cite `file:line` from ModVersion 29
(`25985a9`). If the printed diff touches a file they cite, read those sections with that in
mind. Claude is told to check the code in that case too.

## Check that it works

1. The search helper answers from your generated tables:
   ```bash
   python scripts/wc_search.py --version
   python scripts/wc_search.py MaxTrajectory
   python scripts/wc_search.py --enum GuidanceType
   python scripts/wc_search.py --api Heat
   ```
   - The first prints the WeaponCore version and commit.
   - The second shows `AmmoDef.Trajectory.MaxTrajectory` (float, ProtoMember 1) with example
     values, its read sites and rule lines.
   - The third lists the guidance types.
   - The fourth lists the heat methods of both APIs.

   `python scripts/wc_search.py --src DesiredSpeed` searches the WeaponCore code itself.
2. In a new Claude Code session, ask a WeaponCore question, for example *"My WeaponCore ammo
   does no damage to grids but kills players. I left DamageScales.Grids out. Why?"* Claude
   should load the `se-dev-weaponcore` skill and answer from the code, citing WeaponCore source
   lines.
3. Optional: `evals/` holds test cases (questions plus graded expectations) in the layout
   `claude plugin eval` reads. From the skill folder, `claude plugin eval .` runs each with and
   without the skill. These are real, billed model runs.

## Layout

```
SKILL.md                     instructions Claude reads when the skill loads
references/                  hand-written notes: definitions.md, api.md, combat.md, config-controls.md
scripts/refresh.py           generate or refresh tables/, data/, source/ and graph/ from your clone
scripts/build_reference.py   the generator refresh.py runs
scripts/wc_search.py         field, enum, API and settings search, and source grep
scripts/wc_graph.py          callers, callees, call paths (code graph) and field uses
evals/                       test cases
tables/ data/                generated, not in git
source/ graph/               generated, not in git
```

## Credits and licences

[WeaponCore](https://github.com/Ash-LikeSnow/WeaponCore) is © 2024 Shane R. Stixrud, with
thanks to its contributors, and is licensed under
[CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)
([Steam Workshop](https://steamcommunity.com/sharedfiles/filedetails/?id=3154371364)). This
project is not affiliated with WeaponCore.

None of WeaponCore's code or data is distributed here. The tables, the source mirror and the code
graph are built on your machine from your own WeaponCore checkout by `scripts/refresh.py`, and
`.gitignore` keeps them out of this repository. **What you generate is derived from WeaponCore,
so it carries WeaponCore's licence, CC BY-NC-SA 4.0** (attribution, non-commercial,
share-alike). Keep that in mind before you share it. The notes in `references/` are original
descriptions of how WeaponCore behaves, with `file:line` citations into its source.

The files in this repository are licensed under the GNU Affero General Public License v3.0; see
[LICENSE](LICENSE). That licence covers only this repository's own files, not WeaponCore or
anything generated from it.
