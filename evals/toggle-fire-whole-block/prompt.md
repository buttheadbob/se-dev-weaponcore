---
tags: [se-dev-weaponcore]
max_turns: 25
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash]
---

My turret block has two WeaponCore weapons (weaponId 0 is a gatling, weaponId 1 is a missile launcher). From my mod script I call wcApi.ToggleWeaponFire(turret, true, false, 1) to fire only the missiles, but the gatling fires too. FireWeaponOnce(turret, false, 1) does the same. Am I using the parameters wrong?
