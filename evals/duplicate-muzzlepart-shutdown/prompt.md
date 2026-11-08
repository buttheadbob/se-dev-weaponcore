---
tags: [se-dev-weaponcore]
max_turns: 25
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash]
---

I added a second WeaponDefinition to my existing WeaponCore turret block so it has a gun and a missile launcher. Both defs have the same SubtypeId and I set MuzzlePartId = "MissileTurretBarrels" on both, with different PartNames. Now when the grid loads I get a notification that CoreSystems hard crashed and every WeaponCore weapon in the world stops working. Why, and how do I fix it?
