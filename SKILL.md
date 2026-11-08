---
name: se-dev-weaponcore
description: Reference for WeaponCore (CoreSystems), the Space Engineers 1 weapons framework mod (Ash-LikeSnow/WeaponCore, Workshop 3154371364), built from WeaponCore's own C# code. Gives every definition field a weapon mod writes in its CoreParts (WeaponDefinition, HardPoint, Targeting, Loading, AmmoDef, Trajectory, Smarts/guidance, AreaOfDamage, DamageScales, Fragment, Pattern, Ewar, Beams, AnimationDef, ArmorDefinition, Upgrade and Support definitions) with type, ProtoMember number, example value and what 0 or an unset field really does. Also covers how definitions load (priority, multi-weapon blocks, ammo linking), targeting, firing, heat, reload, projectile guidance, damage and armor, EWAR, the server config and overrides, terminal controls, and the WcApi / WcPbApi scripting APIs that MES NPCs and mods use. Use it whenever working on a WeaponCore weapon mod or its ammo, debugging why a WC weapon doesn't fire, track, hit or do damage, balancing damage, writing a mod or PB script that calls the WeaponCore API, or setting up NPC encounters with WC weapons, even if the user only says WC, CoreParts, CoreSystems, turret AI, smart missiles or weapon definitions.
allowed-tools: Read, Grep, Glob, Bash
---

# WeaponCore reference

**The hand-written `references/` were written against WeaponCore ModVersion 29, commit
`25985a9` (2026-11-05)** of Ash-LikeSnow/WeaponCore. The generated parts (`tables/`, `data/`,
`source/`, `graph/`) are built on this machine from a local WeaponCore clone by
`scripts/refresh.py`. `data/build.json` and the top of `tables/INDEX.md` name the commit they
came from. The C# code wins over this skill, the WeaponCore wiki and the comments in example
CoreParts. If the code may have moved on, refresh (see the bottom of this page) or check the line
before you state it as fact.

`<skill>` below means the folder this SKILL.md is in. Paths in this skill are relative to
`Data/Scripts/CoreSystems/` in the WeaponCore repository. `source/` mirrors that folder.

## First use: generate the tables

If `<skill>/data/fields.json` does not exist, the tables have not been generated yet, and the
search helper says so. Generate them from a git clone of https://github.com/Ash-LikeSnow/WeaponCore.
Ask the user where theirs is, or whether to clone it.

```bash
python <skill>/scripts/refresh.py --repo PATH/TO/WeaponCore
```

It only reads the clone (`git archive`), needs nothing but Python 3.8+ and git, and takes a few
seconds, plus about a minute for the optional code graph when Graphify is installed. Until then,
`references/` still answers how-it-works questions. Exact field names, types and read sites need
the tables or the code.

Applies only to Space Engineers 1. WeaponCore is a **mod**, not a plugin. Weapon definitions
are C# in each weapon mod's `Data/Scripts/CoreParts/` (C# 7.3 under the Mod API whitelist; see
`se-dev-mod`). They are serialized with protobuf and sent to WeaponCore.

## The one thing to know about definition values

Definition fields are protobuf members with **no defaults of their own**. A field the mod
doesn't write arrives as `0`, `false`, `null` or the enum value numbered 0. What that means
is decided by the code that reads it, and it differs per field. Some fields treat 0 as "unlimited"
or "off", some substitute another value, some clamp, and some are used as 0. The comments
in example CoreParts are often right but not always. So for any "what does X = 0 / unset do",
or "why is my value ignored", look at the field's read sites and rule lines (search helper), then
`references/definitions.md`, then the code. Don't answer from the example comment alone.

## How to answer a WeaponCore question

1. **A definition field** (name, type, what it does, what 0 means, where it goes): run the
   search helper. Then open the read sites it lists.
   ```bash
   python <skill>/scripts/wc_search.py MaxTrajectory
   python <skill>/scripts/wc_search.py "Smarts\." --brief
   python <skill>/scripts/wc_search.py Aggressiveness --exact
   python <skill>/scripts/wc_search.py "shield" --desc --brief
   python <skill>/scripts/wc_search.py --enum GuidanceType
   ```
   Each hit gives the modder-facing path (ammo paths start at `AmmoDef`), C# type, ProtoMember
   number, whether the field exists in the mod-side copy, an example value and comment from
   WeaponCore's own CoreParts, where the runtime reads it, and the `rule?` lines. Those are the
   lines that compare it with 0/-1, clamp it or fall back to something else.
   Many ammo fields are copied into `AmmoConstants` (`ammo.AmmoDef.Const.X`, `aConst.X`) at load,
   and the runtime reads the copy. When a read site is in `AmmoConstants.cs`, follow the constant
   (`wc_graph.py uses <ConstName>`).
2. **A whole definition section**: `tables/INDEX.md` lists the tables. `tables/<Section>.md`
   shows every field with example, comment, reads and rule lines. `tables/ENUMS.md` lists every
   enum's values and numbers.
3. **The scripting API**: `wc_search.py --api <regex>` or `tables/API.md` (WcApi),
   `tables/PBAPI.md` (WcPbApi) and `tables/BACKEND.md` (every published key). Then read
   `references/api.md` for the handshake, behaviour and gotchas.
4. **How something works** (why it doesn't fire, how targets are picked, how damage is
   computed): read the matching file under `references/`, then confirm in the code.
5. **The code itself**:
   - `wc_search.py --src "<regex>"` runs `git grep` over the clone at the built commit.
   - `wc_graph.py uses <Name>` finds every read and write of a field or property, with the
     enclosing method.
   - `wc_graph.py callers|callees|path|explain` walk the call graph (needs Graphify).
   - Read files under `<skill>/source/`, or with `git -C <clone> show <commit>:Data/Scripts/CoreSystems/<path>`
     (`repo` and `commit` are in `data/build.json`). Never check out, merge, stash or reset in that
     clone: it may hold the user's own work.
6. **Cite** `file:line` for anything you state about behaviour, and say which WeaponCore commit
   it is from when it matters.

## Routing

| Question is about | Read |
|---|---|
| A field's exact name, type, example, what 0 means | `scripts/wc_search.py`, `tables/<Section>.md` |
| Which sections exist | `tables/INDEX.md` |
| Enum values (Threats, BlockTypes, GuidanceType, HardwareType, EwarType, ...) | `tables/ENUMS.md`, `wc_search.py --enum` |
| Fields that differ between WeaponCore and the mod-side definition copy | `tables/DIFFERENCES.md` |
| How definitions reach WC, priority and duplicates, multi-weapon blocks, ammo linking, zero/clamp/derived rules, common setup mistakes | `references/definitions.md` |
| WcApi and WcPbApi: getting them, every method, callbacks, how MES uses them | `references/api.md`, `tables/API.md`, `tables/PBAPI.md` |
| Targeting, aiming, firing, heat, reload, projectiles and guidance, damage and armor, EWAR | `references/combat.md` |
| Server/client config and overrides, chat commands, terminal controls and actions, vanilla weapon replacement, shield/water integrations, logs | `references/config-controls.md`, `tables/SETTINGS.md` |
| Who calls what, how A reaches B | `scripts/wc_graph.py` |

## Gotchas worth checking first

- **Units.** Times are mostly game ticks (60 = 1 s): ReloadTime, DelayCeaseFire, heat
  ticks, MaxLifeTime and many more. Turret RotateRate/ElevateRate are radians per tick,
  AimingTolerance and DeviateShotAngle are degrees, and azimuth/elevation limits are degrees.
  Check the field's comment and read site before converting.
- **A weapon that does nothing.** It is usually one of these:
  - a subpart or muzzle dummy name that doesn't match the model;
  - turret `Ai` flags that don't match the block type;
  - an `AmmoMagazine` that names no magazine definition;
  - an ammo the weapon lists that is not in the part's `Ammos`;
  - a definition that lost on `DefinitionPriority`.
  `references/definitions.md` lists what the loader checks and what it drops silently.
- **The mod-side definition copy can differ from what WeaponCore deserializes.** A field or enum
  value that exists only in one copy, or is numbered differently, doesn't arrive as written.
  Check `tables/DIFFERENCES.md`: it is generated, so it is current for the built commit.
- **Example comments vs code.** WeaponCore's own CoreParts comments describe intent. Where the
  read site disagrees (for example a "0 = unlimited" that the code treats differently), the code
  is right. Say so when you answer.
- **Server config can override definitions** (damage, ranges, speeds, armor values) per world.
  If a weapon behaves differently on one server, check the overrides in
  `references/config-controls.md`.

## Refreshing after upstream changes

```bash
python <skill>/scripts/refresh.py --fetch upstream
```

It runs `git fetch` on that remote and exports the saved ref (here `upstream/master`) with
`git archive` to a temp folder. The clone's working tree is untouched. It then regenerates
`tables/`, `data/`, `source/` and the graph, and prints which code files changed since the last
build. `--ref` picks another ref and `--repo` another clone. Both are remembered.
`--parts PATH/TO/SomeWeaponMod/Data/Scripts/CoreParts` (repeatable, remembered) adds a weapon
mod's CoreParts as a further source of example values and comments.

The tables then match the new commit. `references/*.md` still cite `file:line` from the commit
named at the top of this file. When the printed diff touches a file a reference cites, check that
section against the new code before relying on it.

## Related skills

- `se-dev-mod`: mod authoring in general, the Mod API whitelist, example mod code.
- `se-dev-mes`: Modular Encounters Systems. MES NPCs use WeaponCore weapons through WcApi.
- `se-dev-game-code` / `se-dev-server-code`: the game's own weapon and damage code.
