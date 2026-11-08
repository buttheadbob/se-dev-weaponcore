---
tags: [se-dev-weaponcore]
max_turns: 25
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash]
---

I want a small server-side balance mod that makes WeaponCore's vanilla Gatling turret (LargeGatlingTurret) fire faster. I copied WeaponCore's LargeGatlingTurret WeaponDefinition into my own CoreParts, changed RateOfFire, and left DefinitionPriority as it was in WC's file. My values never apply. What decides which definition wins?
