# WeaponCore combat reference: targeting, firing, projectiles, damage, EWAR

Source: WeaponCore commit 25985a9 (2026-11-05). Paths are relative to Data/Scripts/CoreSystems/.

Conventions in this file:
- `Def.` = `WeaponDefinition` (`Definitions/CoreDefinitions.cs:232`). `Ammo.` = `WeaponDefinition.AmmoDef` (`Definitions/CoreDefinitions.cs:721`).
- `aConst` = `AmmoConstants` (derived per ammo at load, `Definitions/SerializedConfigs/AmmoConstants.cs:363`). `WConst` = `WeaponConstants` (`Definitions/CoreSystems.cs:765`). `System` = `WeaponSystem` (`Definitions/CoreSystems.cs:98`).
- A tick is 1/60 s. "quirk" marks code that behaves differently from what the field name suggests; the text says what the code does.

---

## 1. Targeting

### 1.1 Definition fields (`Def.Targeting`, `Definitions/CoreDefinitions.cs:267-337`)

| Field | Used as | Cite |
|---|---|---|
| `Threats[]` (`Threat` enum: Projectiles, Characters, Grids, Neutrals, Meteors, Other, Scan*) | Sets `TrackProjectile/TrackGrids/TrackCharacters/TrackMeteors/ScanThreats/ScanNonThreats` | `Definitions/CoreSystems.cs:591-646` |
| `Threats[0] == Projectiles` | `ProjectilesFirst`; if it is the only entry, `ProjectilesOnly` | `Definitions/CoreSystems.cs:509-510` |
| `SubSystems[]` (`BlockTypes`: Any, Offense, Utility, Power, Production, Thrust, Jumping, Steering) | `TargetSubSystems` = any non-Any entry; `OnlySubSystems` = false only if the list has `Any` plus a specific type | `Definitions/CoreSystems.cs:649-663` |
| `TopTargets`, `TopBlocks` | Size of the randomised window in the candidate "deck" | `Ai/AiTargeting.cs:180`, `Ai/AiTargeting.cs:1278` |
| `CycleTargets`, `CycleBlocks` | How many candidates are checked per acquire attempt (0 = all) | `Ai/AiTargeting.cs:167-178`, `Ai/AiTargeting.cs:1267-1276` |
| `StopTrackingSpeed` | `System.MaxTargetSpeed` (0 = unlimited) | `Definitions/CoreSystems.cs:304` |
| `MinimumDiameter`, `MaximumDiameter` | Halved to radii; max 0 = 8192 | `Definitions/CoreSystems.cs:665-672` |
| `ClosestFirst` (+`AllowSwitchTargetPriority`) | Closest projectile / closest subsystem block | `Ai/AiTargeting.cs:579-601`, `Ai/AiTargeting.cs:1201-1212` |
| `MaxTargetDistance`, `MinTargetDistance` | `WConst.MaxTargetDistance` (0 = `double.MaxValue`), `MinTargetDistance` (clamped >= 0) | `Definitions/CoreSystems.cs:849-850` |
| `IgnoreDumbProjectiles`, `LockedSmartOnly` | Projectile-target filters | `Ai/AiTargeting.cs:560`, `Ai/AiTargeting.cs:684` |
| `UniqueTargetPerWeapon`, `EvictUniqueTargets` | Skip targets another weapon on the comp owns, unless evicting | `Ai/AiTargeting.cs:218-223` |
| `MaxTrackingTime` | Ticks before the target is dropped (0 = off) | `Definitions/CoreSystems.cs:598-599`, `Session/SessionUpdate.cs:743-748` |
| `ShootBlanks` | Fires but creates no projectiles | `EntityComp/Parts/Weapon/WeaponShoot.cs:263` |
| `FocusOnly` | Only the construct's focus target | `Ai/AiTargeting.cs:116`, `Session/SessionUpdate.cs:681-684` |
| `ProjectileTagsList`, `ProjectileTagsMeaning` | Tag white/blacklist for projectile targets | `Ai/AiTargeting.cs:552-558`, `Ai/AiTargeting.cs:693-751` |
| `AllowFireDistribution`, `AdvancedFireDistribution` | Enables the terminal toggle and picks the distribution system | `EntityComp/Controls/TerminalHelpers.cs:592`, see 1.9 |
| `ValidControlModes` | Empty/Invalid = Automatic+Manual+Painter | `Definitions/CoreSystems.cs:864-874` |
| `Communications` | Target sharing (radio types) | `Definitions/CoreSystems.cs:329-374` |

Related `Def.HardPoint` fields: `Ai.TrackTargets`, `Ai.TurretAttached`, `Ai.TurretController`, `Ai.PrimaryTracking`, `Ai.LockOnFocus`, `Ai.SuppressFire`, `Ai.TargetGridCenter`, `ScanTrackOnly`, `Other.DisableLosCheck`, `Other.NoVoxelLosCheck`, `Other.ProhibitLGTargeting/ProhibitSGTargeting` (`Definitions/CoreDefinitions.cs:625-638`, `Definitions/CoreDefinitions.cs:544`, `Definitions/CoreDefinitions.cs:692-710`).

### 1.2 Effective range ("terminal range")

- `Weapon.MaxTargetDistance = min(terminal Range (if >= 0, else hardpoint max), WConst.MaxTargetDistance, aConst.MaxTrajectory)` (`EntityComp/Parts/Weapon/WeaponState.cs:173-180`). So ammo `Trajectory.MaxTrajectory` caps targeting range.
- `MinTargetDistanceBufferSqr = (1.5 * MinTargetDistance)^2`, used only for projectile targets (`EntityComp/Parts/Weapon/WeaponState.cs:187-189`, `Ai/AiTargeting.cs:668`).
- Grid/character range test adds the target's radius: `dist > (MaxTargetDistance + TargetRadius)` is rejected (`Ai/AiTargeting.cs:239`).
- Server-side `WConst` overrides (`WeaponValuesMap`) can replace range, ROF, reload, deviation, tolerance, heat and idle power (`Definitions/CoreSystems.cs:878-892`).

### 1.3 When a weapon re-scans

- Each weapon gets a slot in 60 "awake" buckets or 180 "asleep" buckets (`Session/SessionFields.cs:52-53`). Counters wrap each tick (`Session/SessionSupport.cs:84-85`). A weapon is checked when the counter equals its slot (`Session/SessionUpdate.cs:782`, `Session/SessionUpdate.cs:1049`): about once per second awake, once per 3 s asleep.
- A monitored weapon goes to sleep after 600 ticks with no target (`Session/SessionTypes.cs:745-754`).
- Extra checks happen on target change, nearby enemy projectiles, `FastTargetResetTick` and API requests (`Session/SessionUpdate.cs:1051-1052`).
- Queue gate: needs `EnemiesNear` plus a detected signal (or obstructions to scan), ammo (`DropTargetUntilLoaded`), not out of ammo, not needing to go home to reload, focus if `FocusOnly` (`Session/SessionUpdate.cs:780-808`).

### 1.4 Acquisition order (`Ai.AcquireTarget`, `Ai/AiTargeting.cs:30-98`)

1. Auto (or Painter without paint): projectiles first if `ProjectilesFirst`, else top-most entities; then the other; then obstructions (scan threats) (`Ai/AiTargeting.cs:41-64`).
2. Manual/Painter: uses the fake (painted/manual) target if `CanShootTarget` passes (`Ai/AiTargeting.cs:66-74`).

Grid/character candidates come from `ai.SortedTargets`, sorted by `TargetCompare` (`Session/SessionJobs.cs:168`, `Ai/AiTypes.cs:420-447`): drone threats, then grids before non-grids, then imminent threats (approaching, < 800 m, OffenseRating > 0), then higher `OffenseRating`.
- quirk: the "collision risk" key returns `collisionRisk` without negation, so approaching objects < 300 m at > 10 m/s sort after others (`Ai/AiTypes.cs:432-435`); every other key is negated.
- `OffenseRating` = target construct DPS / own DPS when the target has an AI; else 0.0001 if armed or approaching at >= 35 m/s; else 0. Suspected drones get >= 10 (`Ai/AiTypes.cs:501-520`).

Per candidate in `AcquireTopMostEntity` (`Ai/AiTargeting.cs:100-386`), a target is skipped when:
- Friend and not `Friendly` override (focus targets only) (`Ai/AiTargeting.cs:209`); Neutral without `Neutrals` override; NoOwnership without `Unowned` override (`Ai/AiTargeting.cs:214`). `ScanTrackOnly` forces all three on (`Ai/AiTargeting.cs:119-121`).
- Move-mode filter (Moving / Moored / ShipAny) (`Ai/AiTargeting.cs:228`).
- Size: characters use radius x5; `radius <= minRadius` or `radius >= maxRadius` (when max < 8192) (`Ai/AiTargeting.cs:233-234`).
- Not a focus target and `OffenseRating <= 0` (`Ai/AiTargeting.cs:234`).
- Out of range (`Ai/AiTargeting.cs:239`); fully under water (`Ai/AiTargeting.cs:241-244`); API `ValidateWeaponTargetFunc` rejects (`Ai/AiTargeting.cs:252-254`).
- Grid: not `TrackGrids`/`Grids` override, prohibited LG/SG, or fewer than 2 fat blocks unless focus (`Ai/AiTargeting.cs:258`).
- Character: not tracked, dead, or an admin (`Ai/AiTargeting.cs:324`).

Grid path: `TargetGridCenter` aims at the grid AABB centre and skips unpowered grids unless focused (`Ai/AiTargeting.cs:260-281`). Otherwise a fixed weapon must have the (lead-predicted) target sphere inside its aim cone; a turret uses `CanShootTargetObb` (azimuth/elevation limits) (`Ai/AiTargeting.cs:284-296`). Friendly shield in the way rejects (`Ai/AiTargeting.cs:298-303`). Then a block is picked (1.5).

### 1.5 Block selection (SubSystems, TopBlocks)

- `AcquireBlock` (`Ai/AiTargeting.cs:1181-1222`): with `TargetSubSystems`, each `SubSystems` type (or the terminal focus subsystem) is tried in order. `ClosestFirst` -> `GetClosestHitableBlockOfType` (keeps a top-5 list, `Ai/AiTargeting.cs:1544-1800`); else `FindRandomBlock`. If nothing found and `OnlySubSystems`, no target; else any block on the grid (`Ai/AiTargeting.cs:1218-1221`).
- Blocks must be `IsWorking` (warheads/cockpits exempt) unless objective mode allows (`Ai/AiTargeting.cs:1186`, `Ai/AiTargeting.cs:1300`).
- `FindRandomBlock` stops after `lastBlocks` checks: `TopBlocks` if `TopBlocks > 10` and the grid is < 1000 m away, else 10; up to 250 for the construct's focus target (`Ai/AiTargeting.cs:1250-1265`, `Ai/AiTargeting.cs:1294`).
- Deck shuffle (`Ai/AiSupport.cs:225-252`): quirk: with `TopTargets`/`TopBlocks` = N > 0 and N <= candidates, a random chunk index k in `[1, candidates/N]` is chosen and positions `[(k-1)N, kN)` are shuffled; the window is not always the top N. N = 0 keeps sorted order; N > candidates shuffles all.
- quirk: `CycleTargets > count` makes `checkSize = CycleTargets - count` (`Ai/AiTargeting.cs:170-171`).
- `ClosestFirst` does not affect which grid is picked, only projectiles and subsystem blocks (only referenced at `Ai/AiTargeting.cs:579-581`, `Ai/AiTargeting.cs:1001-1003`, `Ai/AiTargeting.cs:1201-1203`).

### 1.6 Line of sight

- Block LOS ray from muzzle toward the block (`Ai/AiTargeting.cs:1345-1349`): own construct blocks it (`Ai/AiTargeting.cs:1364-1369`); voxels and non-enemy characters block it; the closest grid hit is valid only if unowned or a known enemy/neutral/unowned target (`Ai/AiTargeting.cs:1377-1411`).
- Rays over 1.5 km near voxels use the low-detail layer (`Ai/AiTargeting.cs:1358-1360`).
- `Other.NoVoxelLosCheck`: uses an entity-overlap test that ignores voxels (`Ai/AiTargeting.cs:1350`, `Ai/AiTargeting.cs:1415-1513`).
- Smart/drone ammo on a fixed weapon: `SkipAimChecks` (not target-slaving) or `SkipRayChecks` (target-slaving) (`Definitions/SerializedConfigs/AmmoConstants.cs:594-595`). Ray-skip picks the block without a ray (`Ai/AiTargeting.cs:1515-1521`).
- Characters/meteors: `CanShootTarget(checkSelfHit)` casts target->muzzle and rejects hits on the own grid (`EntityComp/Parts/Weapon/WeaponTracking.cs:56-89`).
- While tracking: re-check every 30 ticks unless `DisableLosCheck` or ammo guidance is Smart/DroneAdvanced (`EntityComp/Parts/Weapon/WeaponTracking.cs:458-466`).
- Fixed smart launchers run `SmartLos` (rays from 5 offsets around the muzzle against the own grid) every 240/1200 ticks; blocked -> `PauseShoot` (`Session/SessionUpdate.cs:1105-1106`, `EntityComp/Parts/Weapon/WeaponTracking.cs:512-565`).

### 1.7 Projectiles as targets

- Only projectiles with `Ammo.Health > 0` and no beam are offered as targets (`Projectiles/ProjectileGen.cs:32`, `Projectiles/ProjectileGen.cs:211-213`).
- Only AIs with `PointDefense` (a weapon with `Threats` Projectiles) receive them (`EntityComp/Parts/Weapon/WeaponComp.cs:348-349`, `Projectiles/ProjectileGen.cs:277`).
- Dumb projectiles are added only if their ray hits the target AI sphere of radius `MaxTargetingRange` (motion-predicted). Guided ones are added if aimed at that grid or nearby (`Projectiles/ProjectileGen.cs:286-344`).
- `AcquireProjectile` (`Ai/AiTargeting.cs:526-802`) rejects: neutral-faction shooter without `Neutrals` (`Ai/AiTargeting.cs:654`); `lp.MaxSpeed > StopTrackingSpeed`; out of `[1.5*Min, Max]` range; unique-target conflict (`Ai/AiTargeting.cs:667-671`); dumb when `IgnoreDumbProjectiles`; `LockedSmartOnly` and not smart or targeting own construct (`Ai/AiTargeting.cs:684`); tag filter; `CollisionSize` outside size limits (`Ai/AiTargeting.cs:754-755`); `CanShootTarget` fails or a ray hits anything (`Ai/AiTargeting.cs:768-790`).
- quirk: also rejected if beyond the incoming projectile's own `Smarts.ScanRange` (`Ai/AiTargeting.cs:670-671`).
- quirk: the acceleration passed to the solver is `Velocity - PrevVelocity1` (comment "Wrong btw") (`Ai/AiTargeting.cs:765`).
- A PD projectile only collides with its own target projectile (`Projectiles/ProjectileHits.cs:603-681`), except an end-of-life detonation from a `TrackProjectile` weapon, which hits all live projectiles in the EOL sphere (`Projectiles/Projectiles.cs:472-480`).

### 1.8 Focus and lock-on

- Focus targets are processed first (`offset`). With `FocusTargets` override or `FocusOnly`, only focus targets are tried (`Ai/AiTargeting.cs:146-188`).
- `Ai.LockOnFocus` only raises `MaxLockRange` to `MaxTargetDistance` (`Definitions/CoreSystems.cs:408-409`). Default construct lock range 10000 (`Definitions/CoreStructure.cs:51`). Only reader found: `Api/ApiBackend.cs:504`.
- HUD targeting range = min(longest weapon detect range + own radius, `Enforcement.MaxHudFocusDistance`) (`Ai/AiSupport.cs:208-222`).

### 1.9 Fire distribution (projectile targets only)

- Used only when the terminal `EnableFireDistribution` is on (`Ai/AiTargeting.cs:570-577`); the toggle exists only if `AllowFireDistribution` (`EntityComp/Controls/TerminalHelpers.cs:587-592`).
- System choice (`Support/FireDistribution/FireDistribution.cs:28-35`): `AdvancedFireDistribution` + closest -> AdvancedClosest (closest threat first); `AdvancedFireDistribution` + not closest -> AdvancedScreening (spread fire evenly); else Basic (one PDC per torpedo by distance) (`Support/FireDistribution/Implementation/AdvancedClosestFireDistributionSystem.cs:21-24`, `Support/FireDistribution/Implementation/AdvancedScreeningFireDistributionSystem.cs:15-18`, `Support/FireDistribution/Implementation/BasicFireDistributionSystem.cs:45-48`, `Support/FireDistribution/Implementation/BasicFireDistributionSystem.cs:99-103`).

### 1.10 Losing a target (server, `Session/SessionUpdate.cs:663-751`)

Target reset when: out of ammo for > 600 ticks with no mags (`Session/SessionUpdate.cs:657`, `Session/SessionUpdate.cs:669-672`); entity closed/dead or user-controlled (`Session/SessionUpdate.cs:677-680`); focus no longer valid (`Session/SessionUpdate.cs:681-684`); out of range, checked every 60 ticks (`Session/SessionUpdate.cs:685-688`); target projectile dead (`Session/SessionUpdate.cs:689-693`); `MaxTrackingTime` exceeded; non-turret `TrackTargets` weapon no longer within `AimingTolerance` (`Session/SessionUpdate.cs:731-742`); turret `TrackingTarget` fails (`Session/SessionUpdate.cs:1012-1013`). Idle turrets go home 240 ticks after losing the target (`Session/SessionUpdate.cs:963-964`).

---

## 2. Aiming and firing

### 2.1 Aim tolerance and turret limits

- `HardPoint.AimingTolerance` is in degrees; `<= 0` means 180 (`Definitions/CoreSystems.cs:855`). Stored as a cos for dot tests and as the aim-cone angle (`EntityComp/Parts/Weapon/WeaponFields.cs:331-334`).
- `HardWare.MinAzimuth/MaxAzimuth/MinElevation/MaxElevation` are degrees, normalised then converted to radians (`EntityComp/Parts/Weapon/WeaponTracking.cs:1682-1686`). `HomeAzimuth/HomeElevation` are degrees (`Definitions/CoreSystems.cs:576-577`).
- Turret type: min az == max az -> ElevationOnly; both equal -> Fixed; el equal -> AzimuthOnly; no subparts -> Fixed (`Definitions/CoreSystems.cs:579-588`).
- `RotateRate`/`ElevateRate` are radians per tick (step clamp in `Support/MathFuncs.cs:218-222`).
- `AddToleranceToTracking` widens the limits by the tolerance (`EntityComp/Parts/Weapon/WeaponTracking.cs:1688-1697`). quirk: when set, only elevation is widened; the azimuth branch is an `else if` the flag never reaches.
- Turret rotation: `WeaponLookAt` steps az/el toward the target within limits (`Support/MathFuncs.cs:128-240`). Aligned = barrel forward within tolerance of the predicted point (`EntityComp/Parts/Weapon/WeaponTracking.cs:432-433`). `TargetLock = isTracking && IsAligned` (`EntityComp/Parts/Weapon/WeaponTracking.cs:452`).

### 2.2 Lead prediction (`HardPoint.AimLeadingPrediction`: Off, Basic, Accurate, Advanced; `Definitions/CoreDefinitions.cs:521-527`)

- No lead if Off, beam ammo, or `DesiredSpeed <= 0` (`EntityComp/Parts/Weapon/WeaponTracking.cs:34`).
- Basic: during acquisition target acceleration is zeroed (`accelPrediction = level > 1`, `Ai/AiTargeting.cs:127`, `Ai/AiTargeting.cs:248`).
- `TrajectoryEstimation` (`EntityComp/Parts/Weapon/WeaponTracking.cs:874-1099`):
  - First a crude time-to-intercept (`EntityComp/Parts/Weapon/WeaponTracking.cs:696-720`).
  - Level > 1 allows the advanced grid solver when the grid rotates or accelerates (`EntityComp/Parts/Weapon/WeaponTracking.cs:852-866`, `EntityComp/Parts/Weapon/WeaponTracking.cs:943`).
  - The advanced projectile solver also needs `Ai.UseLimitlessPDSolver` (`EntityComp/Parts/Weapon/WeaponTracking.cs:944`).
  - Fallback: linear lead, or a quartic solve if target accel^2 >= 2.5 (`EntityComp/Parts/Weapon/WeaponTracking.cs:902`, `EntityComp/Parts/Weapon/WeaponTracking.cs:991-1028`).
  - Accelerating ammo adds a time penalty `(DesiredSpeed/AccelPerSec)/tti` (`EntityComp/Parts/Weapon/WeaponTracking.cs:1014-1022`).
  - Gravity drop is solved with the ballistic angle formula, low arc first, high arc if the low one is blocked (`EntityComp/Parts/Weapon/WeaponTracking.cs:1033-1098`).
- Accurate and Advanced behave the same: no code tests above `> 1` (all uses listed in `Ai/AiTargeting.cs:127`, `EntityComp/Parts/Weapon/WeaponTracking.cs:943-944`).

### 2.3 Fire gate (per tick, `Session/SessionUpdate.cs:818-841`)

`AiShooting = !UserControlled && !SuppressFire && (TargetLock || projectile target with smart/drone ammo aligned || CTC aimed)`.

`canShoot` is false when:
- overheated (after a 15-tick countdown, `Session/SessionUpdate.cs:828`);
- reloading or empty (reloadable ammo);
- the weapon is a designator;
- the sequence is not ready;
- `Heat < Ammo.HeatNeededToFire`.

`shoot` also needs `ai.CanShoot` and a target when `aConst.RequiresTarget`. A finish/burst/override, `Other.AllowNoTargetFiring` or a manual signal bypasses the target need (`Session/SessionUpdate.cs:840-841`).

`RequiresTarget = guidance != None && !Smarts.OverideTarget || Ai.TrackTargets` (`Definitions/SerializedConfigs/AmmoConstants.cs:454`).

`ShootWeapons` then skips when: entity invalid, smart-LOS blocked, `PauseShoot`, `LiveSmarts >= Loading.MaxActiveProjectiles` (0 = unlimited), or no loaded ammo (`Session/SessionUpdate.cs:1104-1106`, `Definitions/CoreSystems.cs:327`).

`HardPoint.DelayCeaseFire` (ticks): keeps firing for that many ticks after alignment is lost (`Session/SessionUpdate.cs:835-837`, `Definitions/CoreSystems.cs:300-301`).

### 2.4 Shot timing and per-shot structure (`EntityComp/Parts/Weapon/WeaponShoot.cs:17-389`)

- `Loading.DelayUntilFire`: ticks of pre-fire before the first shot (`EntityComp/Parts/Weapon/WeaponShoot.cs:25-36`). Reset when shooting stops (`EntityComp/Parts/Weapon/WeaponState.cs:153-164`).
- `Loading.RateOfFire` = shots per minute; `TicksPerShot = 3600 / ROF` (`EntityComp/Parts/Weapon/WeaponController.cs:410`).
- `DegradeRof` lerps ROF between `RofAt0Heat` and `RofAt100Heat` by heat%. It starts at `HeatThresholdStart` (default 0.8) and stops below `HeatThresholdEnd` (default 0.4) (`EntityComp/Parts/Weapon/WeaponController.cs:304-317`, `EntityComp/Parts/Weapon/WeaponController.cs:359-374`, `Definitions/CoreSystems.cs:524-542`).
- Barrel spin: a spinning barrel must spin up before firing (`EntityComp/Parts/Weapon/WeaponShoot.cs:44-52`).
- `Loading.BarrelsPerShot`: barrels fired per shot. Each barrel uses 1 ammo (`EntityComp/Parts/Weapon/WeaponShoot.cs:88-108`) and adds heat (`EntityComp/Parts/Weapon/WeaponShoot.cs:318-341`).
- `Loading.TrajectilesPerBarrel`: projectiles per barrel; no extra ammo (`EntityComp/Parts/Weapon/WeaponShoot.cs:208`).
- `Loading.SkipBarrels`: muzzle step (`EntityComp/Parts/Weapon/WeaponShoot.cs:345`).
- `HardPoint.DeviateShotAngle` (degrees): random cone, angle uniform in `[-d, +d]` with random roll (`EntityComp/Parts/Weapon/WeaponShoot.cs:211-232`). quirk: with `DeviateShotAngleSGModifier` against a small grid the range becomes `[-s, 2d+s]` (`EntityComp/Parts/Weapon/WeaponShoot.cs:222-227`).
- `Ammo.Pattern` (weapon mode): every trajectile spawns all pattern entries unless `Random` (count `RandomMin..RandomMax`, with `TriggerChance`) or `PatternSteps` is set (`EntityComp/Parts/Weapon/WeaponShoot.cs:236-268`). Enabled by `Enable` or Mode Weapon/Both (`Definitions/SerializedConfigs/AmmoConstants.cs:1124`).
- `Ammo.DecayPerShot`: damages the weapon block per projectile (`EntityComp/Parts/Weapon/WeaponShoot.cs:270-271`, `EntityComp/Parts/Weapon/WeaponShoot.cs:356-371`).
- `Ammo.BackKickForce`: impulse on the shooter (`EntityComp/Parts/Weapon/WeaponShoot.cs:181-182`).

### 2.5 Bursts

- `BurstMode = ShotsInBurst > 0 && (energy ammo || magazine capacity >= ShotsInBurst)` (`Definitions/SerializedConfigs/AmmoConstants.cs:1374`).
- `HasShotReloadDelay = !BurstMode && ShotsInBurst > 0 && DelayAfterBurst > 0` (`Definitions/SerializedConfigs/AmmoConstants.cs:1378`).
- After `ShotsInBurst` shots the next shot waits `max(DelayAfterBurst, TicksPerShot)` ticks; `GiveUpAfter` drops the target (`EntityComp/Parts/Weapon/WeaponShoot.cs:373-381`, `EntityComp/Parts/Weapon/WeaponShoot.cs:391-425`).
- `Loading.FireFull`: once started, keeps firing until the magazine is empty (`EntityComp/Parts/Weapon/WeaponShoot.cs:30-31`, `EntityComp/Parts/Weapon/WeaponShoot.cs:411-412`).

### 2.6 Heat

- Heat per barrel = `Loading.HeatPerShot * Ammo.HeatModifier`. `HeatModifier <= 0` means 1 unless `AllowNegativeHeatModifier` (`EntityComp/Parts/Weapon/WeaponController.cs:406`, `Definitions/SerializedConfigs/AmmoConstants.cs:534`).
- Overheat when `Heat >= MaxHeat`. Firing stops, and with terminal Overload > 1 the block takes 2% of max integrity (`EntityComp/Parts/Weapon/WeaponShoot.cs:328-332`, `EntityComp/Parts/Weapon/WeaponShoot.cs:427-450`).
- `AllowOverheatShooting` clamps heat at max instead of overheating (`EntityComp/Parts/Weapon/WeaponShoot.cs:333-340`).
- Cooling: every 20 ticks heat drops by `HeatSinkRate/3` (`HeatSinkRate` is per second). Multiplied by `HeatSinkRateOverheatMult` while overheated (`EntityComp/Parts/Weapon/WeaponFields.cs:330`, `EntityComp/Parts/Weapon/WeaponController.cs:260-267`, `EntityComp/Parts/Weapon/WeaponController.cs:337-340`).
- `ProhibitCoolingWhenOff`: no cooling while the block is not working (`EntityComp/Parts/Weapon/WeaponController.cs:262`).
- Overheat clears when `Heat <= MaxHeat * Cooldown`. `Cooldown` is a fraction clamped to 0..0.95 (`EntityComp/Parts/Weapon/WeaponController.cs:320-335`, `Definitions/CoreSystems.cs:521-522`).

### 2.7 Reload and energy

- Magazine: `MagazineSize` = sbc magazine capacity, or `EnergyMagazineSize` for energy ammo (`Definitions/SerializedConfigs/AmmoConstants.cs:568`). `MagsToLoad` (0 = 1) magazines per reload (`Definitions/SerializedConfigs/AmmoConstants.cs:573-574`, `EntityComp/Parts/Weapon/WeaponReload.cs:330`). Loaded ammo = `MagsLoaded * MagazineSize` (`EntityComp/Parts/Weapon/WeaponReload.cs:426`).
- Energy ammo = magazine subtype "Energy" or empty (`Definitions/SerializedConfigs/AmmoConstants.cs:1371`). `MustCharge = energy || HybridRound` (`Definitions/SerializedConfigs/AmmoConstants.cs:1372`).
- `Reloadable = !energy || (MustCharge && ReloadTime > 0)` (`Definitions/SerializedConfigs/AmmoConstants.cs:1376`). Energy ammo with `ReloadTime` 0 never reloads (unlimited).
- `Loading.ReloadTime` (ticks): `ReloadEndTick = now + max(ReloadTime, remaining DelayAfterBurst)` (`EntityComp/Parts/Weapon/WeaponReload.cs:371-381`).
- Charging (energy/hybrid): `MaxCharge = ChargSize = PowerPerTick * max(ReloadTime, 1)` (`Definitions/SerializedConfigs/AmmoConstants.cs:1389-1390`).
  - `PowerPerTick = EnergyCost * BaseDamage (or * Ewar.Strength) * ROF/3600 * BarrelsPerShot * TrajectilesPerBarrel` (`Definitions/SerializedConfigs/AmmoConstants.cs:1380-1387`).
  - Charge grows by the assigned power each tick until full; then reloaded (`Session/SessionCharging.cs:111-133`).
  - Grid power is shared in three priority groups at about 90-94% of available power (`Session/SessionCharging.cs:14-37`).
  - No power, or the comp not working, aborts the charge (`Session/SessionCharging.cs:119-123`).
- `StayCharged = Loading.StayCharged || ReloadTime == 0` (`Definitions/CoreSystems.cs:303`).
- `MaxReloads`: lifetime reload cap (`EntityComp/Parts/Weapon/WeaponReload.cs:306`). `GoHomeToReload` and `DropTargetUntilLoaded` act when empty (`EntityComp/Parts/Weapon/WeaponReload.cs:295-304`).
- Inventory pull keeps ammo between `InventoryLowAmount` (default 0.25) and `InventoryFillAmount` (default 0.75) of `InventorySize` (`Definitions/CoreSystems.cs:297-299`, `EntityComp/Parts/Weapon/WeaponReload.cs:271-289`).
- Creative mode, non-reloadable ammo or `InfiniteResource` always has ammo (`EntityComp/Parts/Weapon/WeaponReload.cs:171-174`).

---

## 3. Projectiles

### 3.1 Guidance types (`Ammo.Trajectory.Guidance`, `Definitions/CoreDefinitions.cs:1466-1476`)

| Value | Runtime behaviour | Cite |
|---|---|---|
| None | Straight (gravity optional). Beams only allowed with None (`IsBeamWeapon = Beams.Enable && Guidance == None`) | `Definitions/SerializedConfigs/AmmoConstants.cs:1261` |
| Remote | quirk: no runtime handler anywhere; flies like None but counts as guided (`RequiresTarget`, `DynamicGuidance`) | `Definitions/SerializedConfigs/AmmoConstants.cs:454`, `Definitions/SerializedConfigs/AmmoConstants.cs:614` |
| TravelTo | Range set to the lead-predicted target point at launch; forced end-of-life (detonation) there | `Projectiles/Projectile.cs:237-251`, `Projectiles/Projectiles.cs:468` |
| Smart | Homing via `RunSmart` | `Projectiles/Projectiles.cs:198-200`, `Projectiles/Projectile.cs:534-892` |
| DetectFixed / DetectTravelTo / DetectSmart | Mines (`IsMine`). Wait until an enemy grid/character is within `Mines.DetectRadius`, then `ActivateMine`. DetectFixed only sets the target position (does not move); the others fly to the predicted position | `Definitions/SerializedConfigs/AmmoConstants.cs:440`, `Projectiles/Projectile.cs:3017-3144` |
| DroneAdvanced | `RunDrone`: launch, then orbit/attack missions | `Projectiles/Projectile.cs:1958-2001`, `Projectiles/Projectile.cs:2085` |

- quirk: DetectSmart counts as smart (`Definitions/SerializedConfigs/AmmoConstants.cs:852`), but `RunSmart` for mines needs `RequestedStage == 1` (`Projectiles/Projectiles.cs:198`). Mine code only sets -1/-2/-3 (`Projectiles/Projectile.cs:3019`, `Projectiles/Projectile.cs:3154`, `Projectiles/Projectile.cs:3171`); stage 1 comes only from Approaches (`Projectiles/Projectile.cs:942`, `Projectiles/Projectile.cs:1779`).
- Mines: owner and faction-share entities are ignored (`Projectiles/Projectile.cs:3089-3095`). `Cloak` hides the model beyond `DeCloakRadius` (`Projectiles/Projectile.cs:3120-3124`). `FieldTime` (ticks) is set as the linger time on trigger (`Projectiles/Projectile.cs:3153`). An idle mine sleeps after 600 ticks (`Projectiles/Projectiles.cs:555-558`).

### 3.2 Speed, acceleration, range, lifetime

- `DesiredSpeed` m/s; launch speed = shooter velocity + direction * DesiredSpeed (+ random `SpeedVariance`) (`Projectiles/Projectile.cs:266-275`, `Projectiles/Projectile.cs:306-314`).
- Beams: speed = `MaxTrajectory * 60`; the beam reaches full length in one tick (`Definitions/SerializedConfigs/AmmoConstants.cs:533`, `Projectiles/Projectiles.cs:167-176`).
- `AccelPerSec` (m/s^2). `<= 0` means no acceleration phase: the projectile starts at full speed (`AmmoSkipAccel`, `Definitions/SerializedConfigs/AmmoConstants.cs:495-496`, `Definitions/SerializedConfigs/AmmoConstants.cs:510`). Otherwise speed rises by `AccelPerSec/60` per tick up to `MaxSpeed` (`Projectiles/Projectiles.cs:203-256`).
- `TotalAcceleration` (0 = unlimited) caps cumulative velocity change (`Definitions/SerializedConfigs/AmmoConstants.cs:497-498`). quirk: the accumulator sums squared per-tick velocity changes and compares them with `TotalAcceleration^2` (`Projectiles/Projectiles.cs:249-252`, `Projectiles/Projectile.cs:872-877`).
- `DragPerSecond` / `DragMinSpeed`: max speed drops `Age * DragPerSecond/60` with a floor (`Definitions/SerializedConfigs/AmmoConstants.cs:511-513`, `Projectiles/Projectiles.cs:212-220`, `Projectiles/Projectiles.cs:261-269`).
- `MaxTrajectory` (m, +/- `RangeVariance`): the projectile ends when distance travelled^2 >= `DistanceToTravelSqr` (`Projectiles/Projectile.cs:225-231`, `Projectiles/Projectiles.cs:321-334`).
- `MaxLifeTime` (ticks, 0 = unlimited): early end (`Definitions/SerializedConfigs/AmmoConstants.cs:493`, `Projectiles/Projectiles.cs:315-319`).
- `DeaccelTime` (ewar/mine only): slows to stop at max range and lingers that many ticks (`Projectiles/Projectile.cs:320`, `Projectiles/Projectiles.cs:221-238`, `Projectiles/Projectiles.cs:326-334`, `Projectiles/Projectiles.cs:463`).
- `MaxTrajectoryTime` (> 1): virtual-beam length grows per shot (`Definitions/SerializedConfigs/AmmoConstants.cs:599`, `EntityComp/Parts/Weapon/WeaponShoot.cs:297`).
- `GravityMultiplier > 0` enables gravity: `velocity += gravity * mult / 60` each tick (`Definitions/SerializedConfigs/AmmoConstants.cs:515`, `Projectiles/Projectiles.cs:187-196`). Weapon gravity is resampled every 120 ticks (`EntityComp/Parts/Weapon/WeaponTracking.cs:904-911`).
- `Shape`: Line or Sphere. `Diameter <= 0` gives a line of 1 m; a sphere uses radius = Diameter/2 (`Definitions/SerializedConfigs/AmmoConstants.cs:1270-1287`).
- Safe zones that forbid damage/shooting destroy the projectile (`Projectiles/ProjectileHits.cs:133-161`).

### 3.3 Smarts (`Ammo.Trajectory.Smarts`, `Definitions/CoreDefinitions.cs:1499-1527`)

| Field | Effect | Cite |
|---|---|---|
| `TrackingDelay` | Homing starts after flying `CollisionSize * TrackingDelay` m (and clear of own grid OBB unless `NoTargetApproach`) | `Definitions/SerializedConfigs/AmmoConstants.cs:558`, `Projectiles/Projectile.cs:559-563` |
| `Aggressiveness` | ProNav gain: `a_lat = Aggr * |v_rel| * (omega x LOS) + NavAccel * targetLatAccel` | `Projectiles/Projectile.cs:729-733` |
| `NavAcceleration` | <0 off, >0 value, 0 means Aggressiveness/2 | `Definitions/SerializedConfigs/AmmoConstants.cs:870-874` |
| `AltNavigation` | Zero-effort-miss nav instead of ProNav | `Definitions/SerializedConfigs/AmmoConstants.cs:884`, `Projectiles/Projectile.cs:734-741` |
| `MaxLateralThrust` | >= 1 = no limit. Below 1, if the turn per tick exceeds it, commanded accel is scaled by `abs(angle/pi - 1)` | `Definitions/SerializedConfigs/AmmoConstants.cs:520`, `Projectiles/Projectile.cs:823-838` |
| `SteeringLimit` > 0 | Uses `ProNavControl` steering instead | `Definitions/SerializedConfigs/AmmoConstants.cs:862`, `Projectiles/Projectile.cs:810-820` |
| `MinTurnSpeed` | No steering below this speed | `Projectiles/Projectile.cs:714-715` |
| `NoSteering` | Fly straight | `Projectiles/Projectile.cs:715`, `Projectiles/Projectile.cs:770-771` |
| `Inaccuracy` (m) | Random aim offset around the target, re-rolled near the target after 300 ticks | `Projectiles/Projectile.cs:633-643`, `Projectiles/Projectile.cs:2794-2801` |
| `OffsetTime`, `OffsetRatio`, `OffsetMinRange` | Periodic random lateral accel while farther than `OffsetMinRange` | `Projectiles/Projectile.cs:777-804` |
| `MaxChaseTime` (ticks, 0 = unlimited) | Gives up the current target and re-targets | `Definitions/SerializedConfigs/AmmoConstants.cs:880`, `Projectiles/Projectile.cs:571` |
| `MaxTargets` (0 = unlimited) | Stops re-targeting after N targets | `Projectiles/Projectile.cs:572`, `Projectiles/Projectile.cs:2826-2828` |
| `OverideTarget` | Picks its own target (not the weapon's); weapon need not have one | `Projectiles/Projectile.cs:286`, `Definitions/SerializedConfigs/AmmoConstants.cs:454` |
| `FocusOnly`, `FocusEviction` | Only the focus target | `Projectiles/Projectile.cs:578-580`, `Ai/AiTargeting.cs:861-862` |
| `Roam` | Keeps flying to the last point and wanders after target loss | `Projectiles/Projectile.cs:669-692` |
| `KeepAliveAfterTargetLoss`, `NoTargetExpire` | Control expiry after `TargetLossTime` | `Projectiles/Projectile.cs:672-677` |
| `CheckFutureIntersection`, `FutureIntersectionRange` | Obstacle avoidance look-ahead (default range = DesiredSpeed + size) | `Definitions/SerializedConfigs/AmmoConstants.cs:561-562`, `Projectiles/Projectile.cs:842-843` |
| `ScanRange` | Also limits how far enemy PD can engage this projectile (1.7 quirk) | `Ai/AiTargeting.cs:670-671` |
| `AccelClearance` | No accel until homing starts | `Projectiles/Projectile.cs:849-852` |
| `IgnoreAntiSmarts` | Immune to AntiSmart EWAR | `Projectiles/Projectile.cs:3260-3261` |

- Re-target timing: checks every 30 ticks (10 ticks if the last target was a projectile), staggered by a random slot. First target search for a non-fragment only after age 120 ticks (`Projectiles/Projectile.cs:585-602`).
- `NewTarget` uses `Ai.ReacquireTarget` (grids, sorted list) or `ReAcquireProjectile` (`Projectiles/Projectile.cs:2818-2922`, `Ai/AiTargeting.cs:822-1179`). A re-target must be within the remaining travel distance (`Ai/AiTargeting.cs:925-926`).
- `TargetLossDegree` (degrees): if the target leaves that cone while tracking, a new target is picked (`Definitions/SerializedConfigs/AmmoConstants.cs:503`, `Projectiles/Projectile.cs:655-663`).
- `TargetLossTime` (ticks): zombie time before expiry (`Definitions/SerializedConfigs/AmmoConstants.cs:491-492`, `Projectiles/Projectile.cs:672-677`).
- Gravity is compensated in the commanded accel (`Projectiles/Projectile.cs:752-768`).
- `Approaches[]` (multi-stage flight) only for Smart/DetectSmart ammo (`Definitions/SerializedConfigs/AmmoConstants.cs:1091-1116`, `Projectiles/Projectile.cs:705-709`). Full stage logic: `Projectiles/Projectile.cs:927-1900`.

### 3.4 Fragments (`Ammo.Fragment`, `Definitions/CoreDefinitions.cs:1122-1161`)

- `AmmoRound` must name another ammo in the same weapon (`Definitions/SerializedConfigs/AmmoConstants.cs:401-432`).
- `Radial`, `Degrees` are degrees clamped to 0..360 (`Definitions/SerializedConfigs/AmmoConstants.cs:1053-1054`). `Offset` < 0 means backwards (`Definitions/SerializedConfigs/AmmoConstants.cs:1050-1052`). `MaxChildren` (0 = unlimited) is the spawn depth (`Definitions/SerializedConfigs/AmmoConstants.cs:1057`).
- Spawn on end: if EOL is enabled with `ArmOnlyOnHit` and not `IgnoreArming`, fragments come only from an armed EOL. Otherwise on end, unless timed spawns are on without `ArmWhenHit` (`Definitions/SerializedConfigs/AmmoConstants.cs:1061-1062`).
- `TimedSpawns`: `StartTime`, `Interval`, `GroupSize`/`GroupDelay` are in ticks of age. `MaxSpawns`; `ParentDies` ends the parent at max spawns (`Projectiles/Projectile.cs:551-555`, `Projectiles/Projectile.cs:3493-3498`).
- `PointAtTarget` + `Proximity` aims fragments by lead (`Projectiles/Projectile.cs:3400`, `Projectiles/Projectile.cs:3452-3454`). `DirectAimCone` (degrees, min 1) only spawns when the target is inside the cone (`Definitions/SerializedConfigs/AmmoConstants.cs:1086-1087`, `Projectiles/Projectile.cs:3420-3433`).
- Pattern Mode Fragment/Both picks fragment ammo from `Pattern.Patterns` (`Definitions/SerializedConfigs/AmmoConstants.cs:1125`, `Projectiles/Projectile.cs:3375-3415`).

### 3.5 Beams (`Ammo.Beams`, `Definitions/CoreDefinitions.cs:1111-1119`)

- Beam = `Enable` and Guidance None. State `OneAndDone`: it lives one update at full `MaxTrajectory` (`Projectiles/Projectile.cs:321`, `Projectiles/Projectiles.cs:152-176`).
- `VirtualBeams`: one real beam carries all barrels; damage is multiplied by the hit count (`Definitions/SerializedConfigs/AmmoConstants.cs:1262`, `Session/SessionDamageMgr.cs:443-444`).
- `RotateRealBeam` and `ConvergeBeams` are visual options of virtual beams (`Definitions/SerializedConfigs/AmmoConstants.cs:1263-1264`).
- `FakeVoxelHitTicks`: voxel cut only on that tick value (`Session/SessionDamageMgr.cs:1336`).
- Beams cannot be shot down: never offered as projectile targets (`Projectiles/ProjectileGen.cs:32`).

---

## 4. Damage

### 4.1 Pools and penetration

- Each projectile starts with `BaseDamagePool = BaseDamage` (min 1e-6, `Definitions/SerializedConfigs/AmmoConstants.cs:1514`) and `BaseHealthPool = Health` (`Projectiles/Projectile.cs:159`).
- `ObjectsHit.MaxObjectsHit` (0 = unlimited) limits objects hit (`Definitions/SerializedConfigs/AmmoConstants.cs:500`, `Session/SessionDamageMgr.cs:59`).
- `CountBlocks`: each block counts; otherwise a whole grid counts as 1 object (`Session/SessionDamageMgr.cs:847-848`, `Session/SessionDamageMgr.cs:1063-1066`).
- The projectile is Depleted when the pool is <= 0 or max objects is reached (`Session/SessionDamageMgr.cs:69-80`, `Session/SessionDamageMgr.cs:116-124`).
- Grid loop: blocks along the path in order. Stops when pool <= 0.5 or max objects is reached (`Session/SessionDamageMgr.cs:470-476`).

### 4.2 Grid block formula (`DamageGrid`, `Session/SessionDamageMgr.cs:369-1073`)

```
blockHp     = (Integrity - AccumulatedDamage) / GeneralDamageMultiplier / GridGeneralDamageModifier
damageScale = hits(virtual) * GridScale * ArmorScale * Heavy/LightScale * CustomScale * fallOff
baseScale   = damageScale * DirectDamageModifer(world) * hitDamageMulti * smallVsLargeBuff * gridSizeBuff
scaled      = BaseDamagePool * baseScale        (capped at BaseDamageCutoff * cutoffScale * baseScale)
if scaled <  blockHp: pool -= scaled / baseScale ; projectile stops in this block
else:                 block dies; pool -= blockHp / baseScale ; continues (penetration)
```

Cites: `Session/SessionDamageMgr.cs:669-686`, `Session/SessionDamageMgr.cs:694-791`, `Session/SessionDamageMgr.cs:797-802`, `Session/SessionDamageMgr.cs:833-845`.

- Scale terms apply only when `aConst.DamageScaling` is true or a block/grid modifier differs from 1 (`Session/SessionDamageMgr.cs:681`).
- `GridScaling`, `ArmorScaling` are false if `NoGridOrArmorScaling` (`Definitions/SerializedConfigs/AmmoConstants.cs:1341-1351`).
- Armour detection = vanilla armour definitions plus `ArmorDefinition` subtypes (`Session/SessionDamageMgr.cs:714`, `Session/SessionDamageMgr.cs:723`).
- `DamageScales.Grids.Large/Small`, `Armor.Armor/Light/Heavy/NonArmor`: a value < 0 is ignored; a value >= 0 multiplies, so 0 means zero damage (`Session/SessionDamageMgr.cs:696-729`).
- `DamageScales.MaxIntegrity` > 0: a block whose scaled HP exceeds it takes nothing and ends the projectile (`Session/SessionDamageMgr.cs:688-692`).
- `Custom.Types[]` (`SubTypeId`, `Modifier`, `CutoffModifier`); `SkipOthers`: NoSkip, Inclusive (skip listed blocks), Exclusive (skip unlisted) (`Session/SessionDamageMgr.cs:750-766`). `Modifier < 0` = 1 (`Definitions/SerializedConfigs/AmmoConstants.cs:1316-1323`).
- `gridSizeBuff` = world `LargeGridDamageMultiplier`/`SmallGridDamageMultiplier` (`Session/SessionDamageMgr.cs:492`).
- `smallVsLargeBuff` = 0.25 when a large-grid shooter hits a small grid and both grid scales are < 0, unless `DisableSmallVsLargeBuff` (`Session/SessionDamageMgr.cs:494-495`).
- Hitting own construct: no damage unless `SelfDamage`, critical reaction, or a launched smart (`Session/SessionDamageMgr.cs:379-383`).
- Damage type: `Explosion` if AOE/EOL configured, else `Bullet` (`Session/SessionDamageMgr.cs:454`). `DamageType.Base` Kinetic/Energy is passed as extra info (`Session/SessionDamageMgr.cs:928`).
- Mass > 0: one impulse `speed * Mass` per grid hit (`Session/SessionDamageMgr.cs:920-924`).

### 4.3 FallOff

`fallOff = clamp(1 - (dist - FallOff.Distance) / (MaxTrajectory - FallOff.Distance), MinMultipler, 1)` for `dist > Distance` (`Session/SessionDamageMgr.cs:428-431`). Active only if `MinMultipler > 0` and != 1 (`Definitions/SerializedConfigs/AmmoConstants.cs:1348`). The same formula is used for shields, characters, projectiles and voxels (`Session/SessionDamageMgr.cs:216-220`, `Session/SessionDamageMgr.cs:1113-1118`, `Session/SessionDamageMgr.cs:1177-1182`, `Session/SessionDamageMgr.cs:1310-1311`).

### 4.4 Area of damage (`Ammo.AreaOfDamage`, `Definitions/CoreDefinitions.cs:1214-1267`)

- `ByBlockHit`: on each grid primary hit, if `Damage > 0.5` (`Session/SessionDamageMgr.cs:603-606`).
- `EndOfLife`: armed when age >= `MinArmingTime` (ticks) (`Session/SessionDamageMgr.cs:453`). Triggered when the pool runs out (`Session/SessionDamageMgr.cs:838`), at max objects (`Session/SessionDamageMgr.cs:849-850`), on sacrificial armour, or at end of flight. At end of flight `ArmOnlyOnHit` needs ObjectsHit > 0 (`Projectiles/Projectiles.cs:463-493`).
- Radius and Depth are metres, converted to blocks (`radius * GridSizeR`); ring = floor(radius) (`Session/SessionDamageMgr.cs:1365-1368`). `Depth <= 0` = Radius (`Definitions/SerializedConfigs/AmmoConstants.cs:1241-1244`).
- Depth < radius limits the box along the hit-face axis (`Session/SessionDamageMgr.cs:1373-1397`).
- `Shape`: Diamond = Manhattan rings; Round = Euclidean (`Session/SessionDamageMgr.cs:1408-1411`).
- The root block takes primary damage only; ring j >= 1 blocks take AOE (`Session/SessionDamageMgr.cs:794`, `Session/SessionDamageMgr.cs:853`).
- AOE per block: `aoeDamageFall(j) * AreaDamageModifer * damageScale * gridSizeBuff` (`Session/SessionDamageMgr.cs:805`). With `m = radius*GridSizeR + 1` (`Session/SessionDamageMgr.cs:626-651`):

| Falloff | aoeDamageFall(j) |
|---|---|
| NoFalloff, Pooled | `D` |
| Linear | `(m-j)/m * D` |
| Curve | `D - j/m/(m-j) * D` |
| InvCurve | `((m-j)/m)^2 * D` |
| Squeeze | `(j+1)/m/(m-j) * D` |
| Exponential | `D / (j+1)` |
| Legacy | not handled: 0 (quirk, see Gotchas) |

- Non-pooled: every block in range takes its share. The cycle ends once total AOE >= `MaxAbsorb` (when > 0) (`Session/SessionDamageMgr.cs:1000`).
- Pooled: `Damage` is a pool drained by damage dealt; with `MaxAbsorb` the per-block amount = MaxAbsorb (`Session/SessionDamageMgr.cs:855-887`).
- `ObjectsHit.SkipBlocksForAOE`: AOE blocks do not count as objects, and AOE ends after the root step (`Session/SessionDamageMgr.cs:477-478`, `Session/SessionDamageMgr.cs:847`, `Session/SessionDamageMgr.cs:1000`).
- Legacy `AreaEffect` (Explosive/Radiant, `Detonation`) is remapped at load to `ByBlockHit`/`EndOfLife` with Depth 1 and Exponential falloff (`Definitions/CoreSystems.cs:464-499`).

### 4.5 Shields (DefenseShields API, `DamageShield`, `Session/SessionDamageMgr.cs:178-367`)

- `primary = pool * DirectDamageModifer * Shields.Modifier * ShieldDamageModifer * ShieldResistMod * ShieldBypassMod`, then fallOff (`Session/SessionDamageMgr.cs:190-220`). `Shields.Modifier < 0` = 1 (`Definitions/SerializedConfigs/AmmoConstants.cs:1524`).
- AOE/EOL on shields: `Damage * radius * k`. k: Pooled none (Damage x1, radius not applied), NoFalloff 1, Linear .55, Curve .81, InvCurve .39, Squeeze .22, Exponential .29 (`Session/SessionDamageMgr.cs:222-284`). Capped by `MaxAbsorb`. Applied only when `ShieldBypassMod >= 1`.
- `Shields.Type`: Heal -> negative damage scaled by shield heat (`Session/SessionDamageMgr.cs:286-315`); Bypass/Default handled via the bypass mod. `DamageType.Shield` Energy/Kinetic is passed to the API (`Session/SessionDamageMgr.cs:198`, `Session/SessionDamageMgr.cs:321`).
- After the hit the pool is 0 unless bypassed; if the shield broke, the leftover HP continues (`Session/SessionDamageMgr.cs:343-354`).
- `Shields.BypassModifier` raw: <= 0 no bypass (< -1 reduces enemy pen chance); 0..1 -> bypass mod `1 - raw`; > 1 -> 0.00001 (`Definitions/SerializedConfigs/AmmoConstants.cs:954-969`, `Projectiles/ProjectileHits.cs:197-243`).
- Grid blocks inside a partial shield end the AOE cycle (`Session/SessionDamageMgr.cs:658-659`).
- NerdShield API is also supported (`Session/SessionDamageMgr.cs:525-565`).

### 4.6 Characters and destroyables (`Session/SessionDamageMgr.cs:1077-1152`)

`scaled = (pool * charScale * DirectDamageModifer + ByBlockHit.Damage * ByBlockHit.Radius * 0.5 * AreaDamageModifer) * ShieldResistMod`, then fallOff (`Session/SessionDamageMgr.cs:1104-1118`). `charScale` = `Characters` if > 0, else 1 (`Definitions/SerializedConfigs/AmmoConstants.cs:1365`). quirk: if the target survives, the pool is multiplied by `scaled/(scaled - hp)`, which grows it (`Session/SessionDamageMgr.cs:1120-1128`).

### 4.7 Damage to projectiles

- Each hit deals `HealthHitModifier` (<= 0 means 1), not BaseDamage (`Definitions/SerializedConfigs/AmmoConstants.cs:1362-1363`, `Session/SessionDamageMgr.cs:1170-1173`).
- If that kills the target: an attacker with `Health > 0` loses the target's HP from its own health; otherwise from its damage pool. If not, the attacker's damage pool is set to 0 (`Session/SessionDamageMgr.cs:1191-1215`).
- An armed EOL attacker damages every live projectile in `EndOfLife.Radius` (`Session/SessionDamageMgr.cs:1217-1271`).
- `MaxIntegrity` also protects projectiles whose health exceeds it (`Session/SessionDamageMgr.cs:1165-1167`).

### 4.8 Voxels, deformation

- Voxels: no damage unless `DamageScales.DamageVoxels`; otherwise a sphere cut sized by `ByBlockHit.Radius * VoxelHitModifier` and the pool (`Session/SessionDamageMgr.cs:1273-1355`).
- `Deform.DeformType`: HitBlock (primary hit only), AllDamagedBlocks, NoDeform. `DeformDelay` ticks (<= 0 = 30). Only for slim (non-fat) blocks that survive with >= 1.5 HP and dmg > 1 (`Session/SessionDamageMgr.cs:932-947`, `Definitions/SerializedConfigs/AmmoConstants.cs:1366`).

### 4.9 ArmorDefinition (`Definitions/CoreDefinitions.cs:211-229`)

- Active only when resistances differ from 0/0 and 1/1, or `MinDamage`/sacrificial is set (`Session/SessionModHandlers.cs:272-289`). `Kind` Heavy/Light adds the subtypes to the armour sets used by `Armor.*` scales (`Session/SessionModHandlers.cs:304-319`).
- Direct/area/detonation scales are divided by `EnergeticResistance` or `KineticResistance`, chosen by `DamageType.Base/AreaEffect/Detonation` (`Session/SessionDamageMgr.cs:783-788`).
- `MinDamage`: primary hits <= it do nothing but still cost pool (`Session/SessionDamageMgr.cs:809-817`).
- `IsSacrificialArmor` + `MinDamageSacrificial` + `SacrificialIntegrityThreshold`: the block dies and the projectile ends (`Session/SessionDamageMgr.cs:822-831`).

---

## 5. EWAR (`Ammo.Ewar`, `Definitions/CoreDefinitions.cs:1271-1339`)

### 5.1 Modes

- `Enable` + `Mode`. Field = `Mode == Field` (`Definitions/SerializedConfigs/AmmoConstants.cs:1190-1197`).
- Effect mode: active every tick (`Projectiles/Projectile.cs:3235-3237`). Grid hits become `Effect` events, otherwise `Field` events (`Projectiles/ProjectileHits.cs:543-554`).
- Field mode: hit volume is a sphere of `Ewar.Radius` (`Projectiles/Projectiles.cs:456-458`, `Projectiles/Projectiles.cs:498-517`). It pulses every `Field.Interval` ticks with `Field.PulseChance` percent (`Projectiles/Projectile.cs:3230-3237`, `Projectiles/Projectile.cs:3320-3361`).
- `Field.GrowTime` (ticks): the field expands from 0 to Radius after the projectile stops or reaches max range (`Projectiles/Projectile.cs:3189-3228`).
- `Field.TriggerRange` > 0: offensive effects wait until the field is triggered (`Definitions/SerializedConfigs/AmmoConstants.cs:1239`, `Projectiles/Projectile.cs:3243`).

### 5.2 Types

| Type | What it does | Cite |
|---|---|---|
| AntiSmart | Projectiles in Radius retarget onto this projectile. Pool = Health, minus each victim's `HealthHitModifier`; once <= 0 each capture costs 1 Health | `Projectiles/Projectile.cs:3246-3281`, `Projectiles/Projectile.cs:160` |
| AntiSmartv2 | Same capture; pool = `Strength`; each capture costs the victim's `Health` | `Projectiles/Projectile.cs:3282-3319` |
| Push / Pull | Impulse `Strength` (x target mass unless `Force.DisableRelativeMass`) along `ForceFrom -> ForceTo`; Pull reverses; `ShooterFeelsForce` adds recoil; fortified shield divides by 5 | `Session/SessionEwar.cs:34-121` |
| Tractor | Pushes or pulls toward `Force.TractorRange` distance | `Session/SessionEwar.cs:86-92` |
| JumpNull, EnergySink, Anchor, Nav, Offense | Turns off working functional blocks of type Jumping / Power / Thrust / Steering / Offense for `Duration` ticks | `Session/SessionEwar.cs:571-598`, `Session/SessionEwar.cs:392-443` |
| Emp | Same, but any functional fat block on the grid | `Session/SessionEwar.cs:599-604` |
| Dot | Explosion damage `Strength * scales` to blocks in range (fat or not) | `Session/SessionEwar.cs:217`, `Session/SessionEwar.cs:270-288` |

### 5.3 Disable mechanics (`ComputeEffects`, `Session/SessionEwar.cs:198-358`)

- Blocks are sorted by distance to the hit (`Session/SessionEwar.cs:563-568`).
- Each block "absorbs" `Strength` against its HP: an `EwarStrength` pool vs `blockHp * scale`. When the block's EWAR health hits 0 it is disabled and kept off by an `EnabledChanged` hook until `Endtick` (`Session/SessionEwar.cs:290-345`, `Session/SessionEwar.cs:392-443`).
- `StackDuration`/`MaxStacks` extend the end tick up to `Duration * MaxStacks` (`Session/SessionEwar.cs:204-208`, `Session/SessionEwar.cs:302-320`).
- Each block costs 1 from the health pool. Effect mode uses `Ammo.Health` (> 0) as the cap; Field mode uses `BaseHealthPool` only if `Depletable` (`Session/SessionEwar.cs:268`, `Session/SessionEwar.cs:367`, `Session/SessionEwar.cs:136-141`).
- Effect-mode hits end the projectile (pools set to 0) (`Session/SessionEwar.cs:193-194`).
- Energy cost for EWAR ammo uses `EnergyCost * Strength` (`Definitions/SerializedConfigs/AmmoConstants.cs:1384`, `EntityComp/Parts/Weapon/WeaponState.cs:91`).
- Characters are skipped by EWAR except Dot/Push/Pull/Tractor (`Projectiles/ProjectileHits.cs:38`, `Projectiles/ProjectileHits.cs:106`).

---

## 6. Gotchas

1. Ticks vs seconds: ticks are used for `ReloadTime`, `DelayAfterBurst`, `DelayUntilFire`, `DelayCeaseFire`, `MaxTrackingTime`, `MaxLifeTime`, `TargetLossTime`, `MaxChaseTime`, `OffsetTime`, fragment `StartTime/Interval/GroupDelay`, `Ewar.Duration`, `Field.Interval/GrowTime`, `MinArmingTime`, `DeformDelay`, `Mines.FieldTime`. Per second: `HeatSinkRate`, `AccelPerSec`, `DesiredSpeed` (m/s), `DragPerSecond`. `RateOfFire` is per minute (`EntityComp/Parts/Weapon/WeaponController.cs:410`).
2. Degrees vs radians: definitions use degrees for `AimingTolerance`, `DeviateShotAngle`, azimuth/elevation limits and home, `TargetLossDegree`, `Fragment.Degrees/Radial`, `DirectAimCone`. `RotateRate/ElevateRate` are radians per tick (`Support/MathFuncs.cs:218-222`). `MaxLateralThrust` is an angle-per-tick threshold, not thrust (`Projectiles/Projectile.cs:823-838`).
3. `-1` vs `0` in `DamageScales`: Grids/Armor scales < 0 = ignore, 0 = no damage (`Session/SessionDamageMgr.cs:696-729`). `Characters` <= 0 = full damage (`Definitions/SerializedConfigs/AmmoConstants.cs:1365`). `Shields.Modifier` < 0 = 1, 0 = no shield damage (`Definitions/SerializedConfigs/AmmoConstants.cs:1524`). `HealthHitModifier`/`VoxelHitModifier` <= 0 = 1 (`Definitions/SerializedConfigs/AmmoConstants.cs:1363-1364`). An omitted float defaults to 0.
4. `AreaOfDamage.*.Falloff` defaults to `Legacy` (enum value 0, `Definitions/CoreDefinitions.cs:1216-1226`). On grids `Legacy` has no case, so AOE ring damage is 0 (`Session/SessionDamageMgr.cs:627-652`). On shields it leaves the damage unscaled (`Session/SessionDamageMgr.cs:256-279`).
5. `DamageType` enums default to `Energy` (first value, `Definitions/CoreDefinitions.cs:836-840`). Any field not set to Kinetic counts as energy (`Definitions/SerializedConfigs/AmmoConstants.cs:1520-1523`).
6. `Threat.Neutrals` does nothing: `TrackNeutrals` is set (`Definitions/CoreSystems.cs:625-628`) but never read. Neutrals are gated by the terminal `Neutrals` switch, default off (`Definitions/SerializedConfigs/Weapon/ProtoWeapon.cs:589`, `Ai/AiTargeting.cs:214`).
7. `StopTrackingSpeed` only filters projectile targets (only readers: `Ai/AiTargeting.cs:667`, `Ai/AiTargeting.cs:1043`). Fast grids are still tracked.
8. Unarmed grids that are not approaching at >= 35 m/s have `OffenseRating` 0 and are never auto-targeted unless focused (`Ai/AiTypes.cs:501-509`, `Ai/AiTargeting.cs:234`). Grids with fewer than 2 fat blocks are skipped too (`Ai/AiTargeting.cs:258`).
9. Weapon range is capped by `Ammo.Trajectory.MaxTrajectory` (`EntityComp/Parts/Weapon/WeaponState.cs:173-180`).
10. `AimingTolerance <= 0` = 180 degrees: fires in any direction (`Definitions/CoreSystems.cs:855`).
11. Ammo per shot = `BarrelsPerShot`; `TrajectilesPerBarrel` is free (`EntityComp/Parts/Weapon/WeaponShoot.cs:88-108`, `EntityComp/Parts/Weapon/WeaponShoot.cs:208`). Heat is added per barrel.
12. `Smarts.TrackingDelay` is a multiple of `CollisionSize` (metres), not ticks (`Definitions/SerializedConfigs/AmmoConstants.cs:558`).
13. Projectiles need `Health > 0` to be shootable, and PD bullets only hit their own target projectile (`Projectiles/ProjectileGen.cs:32`, `Projectiles/ProjectileHits.cs:603`).
14. Pattern with `Enable` spawns every pattern entry at once per trajectile unless `Random` or `PatternSteps` is set (`EntityComp/Parts/Weapon/WeaponShoot.cs:236-268`).
15. ArmorDefinition resistances divide damage: > 1 reduces, < 1 increases (`Session/SessionDamageMgr.cs:785-787`).
16. `Cooldown` is a fraction of `MaxHeat` (max 0.95), not a time (`Definitions/CoreSystems.cs:521-522`, `EntityComp/Parts/Weapon/WeaponController.cs:320`).
17. Energy ammo with `ReloadTime` 0 is not reloadable, so it never runs out (`Definitions/SerializedConfigs/AmmoConstants.cs:1376`).
18. EWAR `Field.Interval` 0 makes `age % 0` NaN, so a Field never pulses (`Projectiles/Projectile.cs:3230-3233`; `RelativeAge` is double, `Projectiles/ProjectileTypes.cs:62`). `PulseChance` is a percent; 0 = never for Field mode.
19. quirk: EWAR Effect hits on one grid sum `Strength` per hit, then `GridEffects` multiplies by the hit count again (`Session/SessionEwar.cs:165-168`, `Session/SessionEwar.cs:368`).
20. quirk: in EWAR `ComputeEffects` the armour scales read `DamageScales.Armor.*` directly, ignoring server ammo overrides (`Session/SessionEwar.cs:242-249`). Direct damage uses the overridable `aConst` values (`Session/SessionDamageMgr.cs:416-419`).
21. Self-damage to own construct is blocked unless `DamageScales.SelfDamage` (`Session/SessionDamageMgr.cs:379-383`).

## 7. Not confirmed

- Whether the target database (`ai.Targets`/`SortedTargets`) ever contains Friends/Owner grids outside focus; the filling code (`Ai/AiDatabase.cs`) was not read.
- What `detectInfo.Armed` and `SuspectedDrone` test (feeds `OffenseRating`, `Ai/AiTypes.cs:501-520`).
- Exact behaviour of the Advanced grid/projectile lead solvers (`EntityComp/Parts/Weapon/WeaponTracking.cs:1115`, `EntityComp/Parts/Weapon/WeaponTracking.cs:1289`) beyond when they are chosen.
- Drone mission logic details (`Projectiles/Projectile.cs:2031-2490`) and the Approach stage engine (`Projectiles/Projectile.cs:927-1900`): only entry points were read.
- How `Fragment.Radial/Degrees/Reverse/DropVelocity` shape the spawn cone (`Fragments.Init` in `Projectiles/ProjectileTypes.cs` not read).
- In-game effect of the DetectSmart `RequestedStage == 1` check (3.1 quirk): inferred from code, not tested.
- `RayCheckTest` internals (tracking LOS ray, `EntityComp/Parts/Weapon/WeaponTracking.cs:461`).
- DefenseShields side of `PointAttackShieldHeat`, `ShieldResistMod` and pen chance (external API).
- Upgrade (`Def.Upgrades`) and Support (`SupportDefinition`) effects on damage and ROF.
