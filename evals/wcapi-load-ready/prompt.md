---
tags: [se-dev-weaponcore]
max_turns: 25
timeout_seconds: 600
allowed_tools: [Read, Glob, Grep, Skill, Bash]
---

In my Space Engineers mod's session component I make a WcApi object and call Load() in Init(), and then again in BeforeStart() just to be safe, then I immediately call GetMaxWeaponRange on a turret. It throws. How is the WeaponCore API supposed to be loaded and when can I use it?
