# WeaponCore definitions: loading, effective values, mistakes

Source: WeaponCore commit 25985a9 (2026-11-05). Paths are relative to Data/Scripts/CoreSystems/.

Read this before you answer "why does my WeaponCore weapon not work" or "what does field X do when 0". Every rule cites the code. "Quirk" marks code that looks unintended. The text describes what the code does. It does not say what the author meant.

## 1. How definitions reach WeaponCore

### Channel and serialization

- WeaponCore listens on mod message channel **7771**: `RegisterMessageHandler(7771, Handler)` (`Session/SessionRun.cs:412`). It unregisters at unload (`Session/SessionRun.cs:449`).
- Right after registering, it sends `null` on channel **7772** (`Session/SessionRun.cs:413`). This tells weapon mods that loaded earlier to send again. The mod-side listener is not in this source (see Not confirmed).
- Both calls run in `LoadData`, and only if WeaponCore is not suppressed (`Session/SessionRun.cs:397-413`).
- The payload must be a `byte[]`. Anything else is ignored with no log (`Session/SessionModHandlers.cs:17-18`).
- WeaponCore first tries `SerializeFromBinary<ContainerDefinition>` (protobuf). Any exception there is swallowed (`Session/SessionModHandlers.cs:20-24`). On success it calls `PickDef` (`Session/SessionModHandlers.cs:26-29`).
- **Legacy path:** if the container read gives null, it reads `WeaponDefinition[]` and feeds it to the same weapon assembler (`Session/SessionModHandlers.cs:31-35`). The legacy path carries weapons only. No armor, upgrade, support or tag definitions.
- Any other exception in `Handler` goes to the game log as `Exception in Handler: ...` (`MyLog.Default`, not WeaponCore's own log) (`Session/SessionModHandlers.cs:58`). The definitions in that message are lost.
- `ContainerDefinition` members: 1 WeaponDefs, 2 ArmorDefs, 3 UpgradeDefs, 4 SupportDefs, 5 ProjectileTags, 6 TagAssigmnents (sic) (`Definitions/CoreDefinitions.cs:9-17`). The mod-side copy is `WcApiDef.ContainerDefinition` with the same member numbers (`Api/CoreSystemsApiDefs.cs:7-18`).
- All definition members are struct or class fields with no initializers (`Definitions/CoreDefinitions.cs:236-242`, `:529-547`). A field the mod leaves out arrives as 0, false or null. This matters for the "0 means..." rules in section 2.

### Mod-side API copy is behind the server copy

`Api/CoreSystemsApiDefs.cs` lacks these server fields. A mod built from that copy cannot set them, so they stay at their defaults:

| Missing in API copy | Server field | Effect of default |
|---|---|---|
| `TargetingDef.ValidControlModes` | `Definitions/CoreDefinitions.cs:337` | null, so all of Automatic, Manual and Painter (`Definitions/CoreSystems.cs:864-865`) |
| `DamageScaleDef.ArmorForCutoff`, `GridSizeForCutoff` | `Definitions/CoreDefinitions.cs:792-793` | 0, so no cutoff scaling (`Definitions/SerializedConfigs/AmmoConstants.cs:1352-1357`) |
| `CustomBlocksDef.CutoffModifier` | `Definitions/CoreDefinitions.cs:907` | 0, so cutoff factor 1 (`Definitions/SerializedConfigs/AmmoConstants.cs:1322`) |

The API Targeting struct ends at member 28 (`Api/CoreSystemsApiDefs.cs:334-335`). Its DamageScaleDef ends at member 13 (`Api/CoreSystemsApiDefs.cs:778`). Its CustomBlocksDef has two members (`Api/CoreSystemsApiDefs.cs:888-892`).

### When it must be sent

- Received definitions are only stored. `AssemblePartDefinitions` appends to `WeaponDefinitions` (`Session/SessionModHandlers.cs:197-200`).
- They are compiled once, in `Session.Init()` (`Session/SessionInit.cs:164-168`). `Init` is guarded by `Inited` and runs only once (`Session/SessionInit.cs:132-133`).
- `Init` is triggered by the first `OnEntityCreate` (`Session/SessionEvents.cs:24`) or the first phantom spawn (`Session/SessionSupport.cs:1347`). `OnEntityCreate` is hooked in `LoadData` (`Session/SessionRun.cs:406`).
- So a mod must send its definitions before the first entity is created, in practice from its own `LoadData` or `Init`. `Handler` has no `Inited` check. A late message is appended but never compiled, with no log.
- WeaponCore's own vanilla-replacement parts are loaded first, in `ModChecker` during `LoadData` (`Session/SessionSupport.cs:1203-1209`).
- The vanilla auto-converter runs inside `Init`, before compilation. It runs only if a mod named `VanillaToWCConverter` or Workshop 3763050326 is loaded (`Session/SessionSupport.cs:1196-1197`, `Session/SessionInit.cs:152-162`).

### PickDef and assembly

`PickDef` passes each array to an assembler (`Session/SessionModHandlers.cs:61-81`). Then it sets `ResourceSinkGroup = "Defense"` on every turret or conveyor-sorter block definition whose subtype appeared in a mount point (`Session/SessionModHandlers.cs:83-99`). The legacy path does the same (`Session/SessionModHandlers.cs:37-54`).

**Weapons** (`AssemblePartDefinitions(WeaponDefinition[])`, `Session/SessionModHandlers.cs:141-202`):
- No priority check at this stage. Every def with at least one mount point is appended (`:197-200`).
- **Vanilla subtype remap.** WeaponCore records the PartName of each of its own built-in mount subtypes in `VanillaPartNames` (`Session/SessionSupport.cs:1211-1218`). A received def might use one of those subtypes with a different `PartName`, or with `Type != BlockWeapon`. In that case the mount is cut out of the def. A copy is made with `PartName` forced to WeaponCore's name and `Type` forced to `BlockWeapon` (`Session/SessionModHandlers.cs:153-192`). This is logged to `debug.log` (`:156`). The forced name makes the copy compete with the built-in def through `DefinitionPriority`.
- WeaponCore's built-in defs use `DefinitionPriority = int.MinValue` (for example `Coreparts/Definitions/Gatlings.cs:55`). So a mod def at the default priority 0 replaces them.

**Duplicate weapons and multi-weapon blocks** are resolved per mount subtype in `CompileWeaponStructures` (`Session/SessionInit.cs:263-376`):
- The key is SubtypeId plus `HardPoint.PartName` plus `HardWare.Type` (`Session/SessionInit.cs:330`).
- Same key: the higher `HardPoint.DefinitionPriority` wins. On a tie the def compiled first stays, because the test is `prevPrio >= new` (`Session/SessionInit.cs:337-343`). Compile order is list order: built-ins, then mod messages in arrival order, then auto-converted defs.
- The loser is logged to `debug.log`: `WeaponDef '...' has a definition with a higher priority present for ...` (`Session/SessionInit.cs:341`). An override is logged as `... was overriden for ...` (`Session/SessionInit.cs:359`).
- Different PartName on the same SubtypeId: both defs are kept. The block becomes a multi-weapon block (`Session/SessionInit.cs:362-363`, `Definitions/CoreStructure.cs:66`).
- Priority is per subtype. A def can win on one mount subtype and lose on another.
- **Quirk (null dereference).** Take a def with `DefinitionPriority == int.MinValue` whose subtype already has defs but none with the same PartName and Type. Then `prevPrio` (int.MinValue) `>=` its priority, and the log line reads `prevDef.ModPath` while `prevDef` is null (`Session/SessionInit.cs:326-341`). Nothing in `Init` catches this.
- Auto-converted defs skip subtypes that already have a def (`Coreparts/AutoConverter.cs:51-55`, `:68`). They also skip mods that ship `Data/NoWeaponcoreConversions.txt` (`Coreparts/AutoConverter.cs:41-49`).

**Upgrades and support** are deduplicated twice. In the handler the check is by PartName across all subtypes, and ties keep the first (`Session/SessionModHandlers.cs:204-260`). At compile it is per subtype and PartName (`Session/SessionInit.cs:654-688`, `:815-849`).

**Armor** (`Session/SessionModHandlers.cs:262-325`): priority is per SubtypeId, and ties keep the first (`:295-302`). Quirk: the def is added to `CoreSystemsArmorDefs`, and `ArmorCoreActive` is set, before the priority check (`:266`, `:279`, `:288`).

**Projectile tags**: one namespace per `Namespace.ID`. It is replaced only when the new priority is strictly higher (`Session/SessionModHandlers.cs:114-118`). A namespace with an empty ID or no tags is skipped (`:111-112`). Tag assignments are keyed by ammo name string across all mods (`Session/SessionModHandlers.cs:122-138`).

### Building the block structure

For each subtype, the block definition is found by `SubtypeName`, or through `VanillaCoreIds` for vanilla types with a null subtype (`Session/SessionInit.cs:480-486`, `Session/SessionSupport.cs:1636-1655`). Then:
- `CoreSystemsDefs[subtype]` is set only when a matching block definition exists. Phantoms get an Invalid-type id (`Session/SessionInit.cs:512`, `:598-601`).
- **Silently dropped:** a non-Phantom def whose subtype matches no loaded block definition gets no structure (`Session/SessionInit.cs:606-610`), and nothing is logged.
- An exception while the block definition is changed logs `Failed to load <PartName>` (`Session/SessionInit.cs:603`).
- `new WeaponStructure(...)` is outside that try (`Session/SessionInit.cs:609`).

`WeaponStructure` (`Definitions/CoreStructure.cs:53-227`):
- `ModPath` null logs `invalid modpath:...` and returns with no parts (`:61-64`).
- A def with null or empty `Ammos` logs `CoreStructure failed to match PartName to typeName or ammo invalid` and returns, leaving a half-built structure (`:96-100`).
- Part order follows the subtype map. The primary part is the first with `Ai.PrimaryTracking`, otherwise part 0 (`:114-115`, `:218-219`).
- `ConstructPartCap` is the smallest positive cap across parts. 0 means no cap (`:110-112`, `EntityComp/PlatformInit.cs:122`).

### Ammo linking

- Fragments and patterns are looked up **by AmmoRound name inside the same WeaponDefinition's `Ammos`** (`Definitions/SerializedConfigs/AmmoConstants.cs:401-407`, `:1160-1166`). The template says "Must list all primary, shrapnel, and pattern ammos" (`Coreparts/Definitions/Gatlings.cs:126`).
- `Fragment.AmmoRound` not found: `FragmentId` stays -1, so `HasFragment` is false (`Definitions/SerializedConfigs/AmmoConstants.cs:100`, `:432`). Silently no fragments.
- An ammo is marked shrapnel (`IsShrapnel`) if its name is any `Fragment.AmmoRound`, or a pattern entry in `Fragment` or `Both` mode, within the same def (`Definitions/CoreStructure.cs:117-132`, `:160`). Shrapnel is never turret-selectable (`Definitions/SerializedConfigs/AmmoConstants.cs:445`). Weapon-mode pattern ammos are not marked shrapnel.
- Empty or null `AmmoRound` is replaced by `<SubtypeId>-<index>`, with the log `[!!! MOD ERROR !!!] Invalid AmmoName ...` (`Definitions/CoreStructure.cs:139-144`).

### Where errors go

- WeaponCore's own logs are text files in its mod local storage (`WriteFileInLocalStorage`) (`Support/Log.cs:122-132`). `Log.Line` without an instance name writes to `debug.log`, the default instance (`Support/Log.cs:126`, `:273`, `Session/SessionRun.cs:379`).
- The handler exception and the "No ammo magazine definition" message also go to the game log (`Session/SessionModHandlers.cs:58`, `Definitions/SerializedConfigs/AmmoConstants.cs:375`).
- `WeaponConstants` writes `<PartName>: <ValidControlModes>` to the game log and console for every weapon (`Definitions/CoreSystems.cs:876`).
- Block-init failures call `PlatformCrash`. With `suppress=true` this sets `SuppressWc = true`, which **stops WeaponCore for the whole session**. It also shows a 10 s notification and logs `PlatformCrash: ...` (`EntityComp/PlatformInit.cs:748-765`, `Session/SessionRun.cs:159-161`).
- The log floods are throttled after the first 3600 ticks (`Support/Log.cs:56-63`).

## 2. Effective values: changed, clamped, defaulted, derived

Paths are definition paths. "Unlimited" means the code substitutes `int.MaxValue` or `double.MaxValue`. Server-config overrides (`WeaponOverride`, `AmmoOverride` in `Definitions/SerializedConfigs/CoreSettings.cs:78`, `:146`) are clamped the same way or tighter (`Definitions/CoreSystems.cs:884-892`, `Definitions/SerializedConfigs/AmmoConstants.cs:1548-1566`).

### WeaponDefinition: Assignments, HardPoint, Targeting

| Field | Rule | Citation |
|---|---|---|
| `Assignments.MountPoints[].DurabilityMod` | Always written to the block's `GeneralDamageMultiplier`, which replaces the SBC value. 0 or less gives 0.25 on large grid, 0.05 on small. Support blocks get 0.25 on both. | `Session/SessionInit.cs:588`, `:772`, `:935` |
| `HardPoint.HardWare.InventorySize` | Block inventory = sum over all defs on the subtype (weapon blocks: `InventoryMaxVolume`). On sorters the edge length adds the cube root of each size, and volume = edge³. | `Session/SessionInit.cs:530-551` |
| `HardPoint.HardWare.FixedInventorySize` | false: inventory is multiplied by the world `BlocksInventorySizeMultiplier`. | `EntityComp/EntityInit.cs:94-97` |
| `HardPoint.Loading.RateOfFire`, `ShotsInBurst` | Also written into the vanilla weapon definition's `WeaponAmmoDatas[0]`. | `Session/SessionInit.cs:535-541` |
| `HardPoint.Loading.RateOfFire` | Negative becomes 0 (`Math.Max`). At runtime the rate is floored to 1/min. `TicksPerShot = (uint)(3600 / rate)`. | `Definitions/CoreSystems.cs:851`, `EntityComp/Parts/Weapon/WeaponController.cs:367-372` |
| `HardPoint.Loading.ReloadTime` | Negative becomes 0. 0 forces `StayCharged`. | `Definitions/CoreSystems.cs:852`, `:303` |
| `HardPoint.Loading.MagsToLoad` | 0 or less becomes 1. | `Definitions/SerializedConfigs/AmmoConstants.cs:573` |
| `HardPoint.Loading.MaxActiveProjectiles` | 0 or less: unlimited. | `Definitions/CoreSystems.cs:327` |
| `HardPoint.Loading.MaxReloads` | 0 or less: unlimited (checked as `> 0`). | `EntityComp/Parts/Weapon/WeaponReload.cs:306` |
| `HardPoint.Loading.InventoryFillAmount` / `InventoryLowAmount` | 0 or less becomes 0.75 / 0.25 of the max ammo volume. | `Definitions/CoreSystems.cs:298-299` |
| `HardPoint.Loading.UseWorldInventoryVolumeMultiplier` | Scales `MaxAmmoVolume` by the world inventory multiplier. | `Definitions/CoreSystems.cs:297` |
| `HardPoint.Loading.Cooldown` | Clamped to [0, 0.95]. | `Definitions/CoreSystems.cs:521-522` |
| `HardPoint.Loading.DegradeRofSettings.*` | Used only if `DegradeRof`. `HeatThresholdStart` outside (0,1] becomes 0.8. `HeatThresholdEnd` outside (0,1] becomes 0.4. `RofAt0Heat` 0 or less becomes 1. `RofAt100Heat` 0 or less becomes 0.25. Without `DegradeRof` these four take those defaults. | `Definitions/CoreSystems.cs:524-542` |
| `HardPoint.Loading.BarrelSpinRate` | Ignored unless `Other.RotateBarrelAxis != 0`. If > 0, capped at 3599. If 0, uses RateOfFire. Quirk: the RateOfFire branch caps at 3599 only when RoF ≥ 3699, so 3600-3698 pass through. | `Definitions/CoreSystems.cs:552-557` |
| `HardPoint.Loading.BarrelsPerShot`, `TrajectilesPerBarrel` | Not clamped. They are loop bounds, so 0 fires nothing. | `EntityComp/Parts/Weapon/WeaponShoot.cs:88`, `:208` |
| `HardPoint.Loading.ShotsInBurst` | Burst mode only if > 0 and (energy ammo, or magazine capacity ≥ ShotsInBurst). Otherwise, with `DelayAfterBurst > 0`, a shot-reload delay is used. | `Definitions/SerializedConfigs/AmmoConstants.cs:1374`, `:1378` |
| `HardPoint.HardWare.IdlePower` | Floor 0.001 MW (weapon, upgrade, support). | `Definitions/CoreSystems.cs:861`, `:59`, `:83` |
| `HardPoint.HardWare.HomeAzimuth` / `HomeElevation` | `((v + 180) % 360) - 180` degrees, then radians. Quirk: C# `%` keeps the sign, so values below -180 are not wrapped. | `Definitions/CoreSystems.cs:576-577` |
| `HardPoint.HardWare.Min/MaxAzimuth`, `Min/MaxElevation` | min == max azimuth: ElevationOnly. min == max elevation: AzimuthOnly, or Fixed if azimuth is also locked. All of muzzle, azimuth and elevation part "None" or empty (`NoSubParts`): Fixed. | `Definitions/CoreSystems.cs:579-588`, `:289` |
| `HardPoint.HardWare.*` on vanilla turret blocks | If the azimuth or elevation part id is a vanilla subpart name, WeaponCore writes Min/Max az/el into the turret block definition, sets `RotationSpeed = RotateRate/60` and `ElevationSpeed = ElevateRate/60`, and turns off vanilla AI and idle rotation. Empty ids count as `MissileTurretBase1` / `MissileTurretBarrels` here. | `Session/SessionInit.cs:559-575`, `Session/SessionSupport.cs:1774-1781` |
| `HardPoint.AimingTolerance` | 0 or less becomes 180°. | `Definitions/CoreSystems.cs:855` |
| `HardPoint.DeviateShotAngle` | Degrees to radians, not clamped. Deviation is applied only when > 0, or when a request or small-grid modifier applies. | `Definitions/CoreSystems.cs:854`, `EntityComp/Parts/Weapon/WeaponShoot.cs:211` |
| `HardPoint.DelayCeaseFire` | Active only if > 0. | `Definitions/CoreSystems.cs:300-301` |
| `HardPoint.Ui.RateOfFireMin` | Outside [0,1] becomes 0. | `Definitions/CoreSystems.cs:846` |
| `HardPoint.Other.RestrictionRadius` | Used only if > 0. Stored × 0.999 for weapons. The largest value across defs wins. | `Session/SessionInit.cs:489-510` |
| `HardPoint.Other.ConstructPartCap` | Smallest positive value across parts. 0 means no cap. | `Definitions/CoreStructure.cs:110-112`, `EntityComp/PlatformInit.cs:122` |
| `HardPoint.Ai.DefaultLeadGroup` | Taken from the first def with a value > 0 that is not `TurretAttached` or has `OverrideLeads`. | `Definitions/CoreStructure.cs:89-92` |
| `HardPoint.Ai.LockOnFocus` | If set, `MaxLockRange` is raised to `Targeting.MaxTargetDistance`. | `Definitions/CoreSystems.cs:408-409` |
| `HardPoint.PartName` | Shortened to 21 characters for `ShortName`. | `Definitions/CoreSystems.cs:459-460` |
| `Targeting.MaxTargetDistance` | 0 or less: unlimited. | `Definitions/CoreSystems.cs:849` |
| `Targeting.MinTargetDistance` | Negative becomes 0. | `Definitions/CoreSystems.cs:850` |
| `Targeting.StopTrackingSpeed` | 0 or less: unlimited. | `Definitions/CoreSystems.cs:304` |
| `Targeting.MinimumDiameter` / `MaximumDiameter` | Halved to radius. Min 0 or less becomes 0. Max 0 or less becomes radius 8192. | `Definitions/CoreSystems.cs:667-671` |
| `Targeting.MaxTrackingTime` | 0 means no limit (`MaxTrackingTime = ticks > 0`). | `Definitions/CoreSystems.cs:598-599` |
| `Targeting.Threats` | `Projectiles` first in the list sets ProjectilesFirst. Only `Projectiles` sets ProjectilesOnly. | `Definitions/CoreSystems.cs:509-510` |
| `Targeting.ValidControlModes` | Null, empty or all `Invalid`: Automatic, Manual and Painter. | `Definitions/CoreSystems.cs:864-874` |
| `Targeting.Communications.StorageLimit`, `MaxConnections` | 0 means unlimited. | `Definitions/CoreSystems.cs:339`, `:370` |
| `Targeting.Communications.Mode` | BroadCast and Repeat need a channel and `BroadCastRange > 0`. Relay needs both channels and `RelayRange > 0`. LocalNetwork needs `StorageLocation`. Anything else that has a channel becomes Receiver. Quirk: in the Receiver branch the relay channel hash is computed but not stored. | `Definitions/CoreSystems.cs:331-368` |
| `Targeting.ProjectileTagsList` | Names not in a registered tag namespace are dropped silently. | `Definitions/CoreSystems.cs:800-809` |

### AmmoDef

| Field | Rule | Citation |
|---|---|---|
| `AmmoMagazine` | `""` or `"Energy"` means energy ammo, matched to the definition with subtype `Energy`. | `Definitions/CoreStructure.cs:148-152` |
| `AmmoRound` | Empty or null: renamed `<SubtypeId>-<i>`. | `Definitions/CoreStructure.cs:139-144` |
| `TerminalName` | Empty becomes `AmmoRound`. | `Definitions/SerializedConfigs/AmmoConstants.cs:446` |
| `BaseDamage` | Floor 0.000001. | `Definitions/SerializedConfigs/AmmoConstants.cs:1514` |
| `Health` | > 0 makes the projectile targetable. A fragment or pattern ammo with Health > 0 also makes the parent targetable. | `Definitions/SerializedConfigs/AmmoConstants.cs:425-426`, `:632-644` |
| `HardPointUsable` | false makes the ammo non-selectable. Selectable = `!IsShrapnel && HardPointUsable`. | `Definitions/SerializedConfigs/AmmoConstants.cs:445` |
| `HeatModifier` | 0 or less becomes 1, unless `AllowNegativeHeatModifier`. | `Definitions/SerializedConfigs/AmmoConstants.cs:534` |
| `EnergyCost` | Used only for energy or hybrid ammo. Power per tick = cost × BaseDamage (or × `Ewar.Strength` for EWAR) × RoF/3600 × BarrelsPerShot × TrajectilesPerBarrel. | `Definitions/SerializedConfigs/AmmoConstants.cs:1380-1387` |
| `EnergyMagazineSize` | 0 or less becomes ceil(power per tick × ReloadTime). ReloadTime 0 counts as 1. If the result is 0, the log says `... Girax error detected!`. | `Definitions/SerializedConfigs/AmmoConstants.cs:1389-1393`, `:568-571` |
| `HybridRound` | Physical ammo that must also charge. | `Definitions/SerializedConfigs/AmmoConstants.cs:442`, `:1372` |
| (derived) reloadable | Physical ammo always reloads. Energy ammo reloads only if `ReloadTime > 0`. | `Definitions/SerializedConfigs/AmmoConstants.cs:1376` |
| `BackKickForce` | Used as is (override floors at 0). Zero means no recoil. | `Definitions/SerializedConfigs/AmmoConstants.cs:518-519` |
| `Trajectory.MaxLifeTime` | 0 or less: unlimited. | `Definitions/SerializedConfigs/AmmoConstants.cs:493` |
| `Trajectory.TargetLossTime` | 0 or less: unlimited. "Zombie" behaviour needs a positive value and a non-mine. | `Definitions/SerializedConfigs/AmmoConstants.cs:491-492` |
| `Trajectory.TargetLossDegree` | Stored as cos(degrees). 0 gives 0. The check runs only when the stored value is > 0, so **about 90° or more disables it**, the same as 0. | `Definitions/SerializedConfigs/AmmoConstants.cs:503`, `Projectiles/Projectile.cs:655`, `:2769` |
| `Trajectory.AccelPerSec` | 0 or less: no acceleration step. | `Definitions/SerializedConfigs/AmmoConstants.cs:510` |
| `Trajectory.TotalAcceleration` | 0 or less: unlimited. | `Definitions/SerializedConfigs/AmmoConstants.cs:497` |
| `Trajectory.DesiredSpeed` | For beams it is replaced by `MaxTrajectory × 60`. | `Definitions/SerializedConfigs/AmmoConstants.cs:532-533` |
| `Trajectory.DragPerSecond` / `DragMinSpeed` | Drag only if > 0. Per tick = value/60. `DragMinSpeed` ignored without drag. | `Definitions/SerializedConfigs/AmmoConstants.cs:511-513` |
| `Trajectory.GravityMultiplier` | > 0 means the projectile feels gravity. | `Definitions/SerializedConfigs/AmmoConstants.cs:515` |
| `Trajectory.MaxTrajectoryTime` | > 1 makes the range grow by MaxTrajectory/time per tick. | `Definitions/SerializedConfigs/AmmoConstants.cs:599`, `:1040` |
| `Trajectory.DeaccelTime` | > 0 with `Ewar.Enable` makes the ammo a field. | `Definitions/SerializedConfigs/AmmoConstants.cs:441` |
| `Trajectory.Smarts.MaxLateralThrust` | ≥ 1 means unlimited. Floor 0.0001. | `Definitions/SerializedConfigs/AmmoConstants.cs:520` |
| `Trajectory.Smarts.NavAcceleration` | < 0 gives 0 (off). 0 gives Aggressiveness/2 if Aggressiveness > 0, else 0. > 0 used as is. | `Definitions/SerializedConfigs/AmmoConstants.cs:870-874` |
| `Trajectory.Smarts.MaxChaseTime` | 0 or less: unlimited. | `Definitions/SerializedConfigs/AmmoConstants.cs:880` |
| `Trajectory.Smarts.SteeringLimit` | > 0 turns on advanced steering, with angles precomputed. | `Definitions/SerializedConfigs/AmmoConstants.cs:862`, `:2535-2555` |
| `Trajectory.Smarts.FutureIntersectionRange` | 0 or less becomes DesiredSpeed + collision size. | `Definitions/SerializedConfigs/AmmoConstants.cs:562` |
| `Trajectory.Smarts.TrackingDelay` | Squared distance = (collision size × delay)². | `Definitions/SerializedConfigs/AmmoConstants.cs:558` |
| `Trajectory.Approaches` | Ignored unless the guidance is `Smart` or `DetectSmart`. | `Definitions/SerializedConfigs/AmmoConstants.cs:852`, `:1094` |
| `Approaches[].DeAccelMulti` / `TotalAccelMulti` / `ModelMaximumAngleToRotate` | 0 becomes 1. 0 or less becomes 1 (stored squared). 0 or less becomes 0, else deg/60 in radians. | `Definitions/SerializedConfigs/AmmoConstants.cs:2322-2323`, `:2295` |
| `Approaches[].AccelMulti` | Quirk: if `AccelPerSec × AccelMulti > 0`, the step limit is `AccelMulti` alone, not the product. | `Definitions/SerializedConfigs/AmmoConstants.cs:2315` |
| `GridsTargetSeekersTargetingThis` | Needs `Health > 0`. | `Definitions/SerializedConfigs/AmmoConstants.cs:887` |
| `ObjectsHit.MaxObjectsHit` | 0 or less: unlimited. | `Definitions/SerializedConfigs/AmmoConstants.cs:500` |
| `Shape.Diameter` | 0 or less forces a line shape of size 1. Sphere size = diameter/2. A collision size > 5 logs a warning. | `Definitions/SerializedConfigs/AmmoConstants.cs:1279-1286`, `:616` |
| `Beams.Enable` | Ignored unless `Trajectory.Guidance == None`. | `Definitions/SerializedConfigs/AmmoConstants.cs:1261` |
| `Beams.VirtualBeams` / `RotateRealBeam` / `ConvergeBeams` / `OneParticle` | Each needs the one before it: beam, then virtual, then not rotate-real. | `Definitions/SerializedConfigs/AmmoConstants.cs:1262-1265` |
| `DamageScales.Grids.*`, `Armor.*` | **< 0 means no scaling. ≥ 0 multiplies, so 0 (also an omitted field) means zero damage to that class.** `NoGridOrArmorScaling` turns both off. | `Definitions/SerializedConfigs/AmmoConstants.cs:1343-1350`, `Session/SessionDamageMgr.cs:694-716` |
| `DamageScales.Grids.*` (both < 0) | Lets the server's small-vs-large buff (0.25) apply. | `Session/SessionDamageMgr.cs:494-495` |
| `DamageScales.Characters` | 0 or less becomes 1. | `Definitions/SerializedConfigs/AmmoConstants.cs:1365` |
| `DamageScales.HealthHitModifier` / `VoxelHitModifier` | 0 or less becomes 1. | `Definitions/SerializedConfigs/AmmoConstants.cs:1362-1364` |
| `DamageScales.Deform.DeformDelay` | 0 or less becomes 30. | `Definitions/SerializedConfigs/AmmoConstants.cs:1366` |
| `DamageScales.FallOff.MinMultipler` | Falloff only if > 0 and ≠ 1. | `Definitions/SerializedConfigs/AmmoConstants.cs:1348` |
| `DamageScales.Custom.Types[]` | Entry used if `Modifier ≥ 0` or `CutoffModifier > 0`. A negative Modifier becomes 1. Matched by SubtypeId against all definitions. | `Definitions/SerializedConfigs/AmmoConstants.cs:1312-1325` |
| `DamageScales.GridSizeForCutoff.*` | Only with `BaseDamageCutoff > 0`. 0 or less becomes 1. | `Definitions/SerializedConfigs/AmmoConstants.cs:1352-1357` |
| `DamageScales.Shields.Modifier` | < 0 becomes 1. 0 stays 0. | `Definitions/SerializedConfigs/AmmoConstants.cs:1524` |
| `DamageScales.Shields.BypassModifier` | ≤ 0: no bypass. < -1: anti-penetration = clamp(\|raw+1\|, 0, 1). > 1: bypass mod 0.00001. (0,1]: clamp(1-raw, 0.00001, 0.99999). | `Definitions/SerializedConfigs/AmmoConstants.cs:954-969` |
| `DamageScales.Shields.HeatModifier` | 0 becomes 1. | `Definitions/SerializedConfigs/AmmoConstants.cs:535` |
| `DamageScales.DamageType.*` | Anything other than `Kinetic` counts as energy damage. | `Definitions/SerializedConfigs/AmmoConstants.cs:1520-1523` |
| `AreaOfDamage.ByBlockHit.Radius` / `EndOfLife.Radius` | 0 when that block's `Enable` is false. | `Definitions/SerializedConfigs/AmmoConstants.cs:1211`, `:1221` |
| `AreaOfDamage.*.Depth` | 0 or less becomes Radius (only when enabled). | `Definitions/SerializedConfigs/AmmoConstants.cs:1241-1244` |
| `AreaOfDamage.*.MaxAbsorb` | 0 or less becomes 0 (no cap is implied). | `Definitions/SerializedConfigs/AmmoConstants.cs:1226`, `:1231` |
| `AreaOfDamage.EndOfLife.CustomParticle` | Empty becomes `Explosion_Missile`. | `Definitions/SerializedConfigs/AmmoConstants.cs:523` |
| `AreaOfDamage.EndOfLife.CustomSound` | Empty becomes `WepSmallMissileExpl` (none for shrapnel). `NoSound` turns it off. | `Definitions/SerializedConfigs/AmmoConstants.cs:525`, `:1425` |
| `AreaEffect.*` (legacy) | If `AreaEffect` is Explosive or Radiant, it **overwrites** `AreaOfDamage.ByBlockHit`: damage = max(Base.EffectStrength, AreaEffectDamage), or BaseDamage if that is ≤ 0; radius = max of the two radii; Depth 1; Exponential falloff. Applied only if that damage and radius are both > 0. `Detonation.DetonateOnEnd` overwrites `EndOfLife` the same way. | `Definitions/CoreSystems.cs:464-499` |
| `Fragment.Radial` / `Degrees` | Clamped to [0, 360]. | `Definitions/SerializedConfigs/AmmoConstants.cs:1053-1054` |
| `Fragment.MaxChildren` | 0 or less: unlimited. | `Definitions/SerializedConfigs/AmmoConstants.cs:1057` |
| `Fragment.Offset` | The sign selects the direction. The magnitude is used. | `Definitions/SerializedConfigs/AmmoConstants.cs:1050-1052` |
| `Fragment.TimedSpawns.*` | Need a resolved fragment. A group needs both `GroupSize` and `GroupDelay` > 0. `DirectAimCone` is used only if > 0 with `PointType Direct`, minimum 1°. | `Definitions/SerializedConfigs/AmmoConstants.cs:1074`, `:1084-1087` |
| `Pattern.*` | Weapon pattern = `Enable`, or Mode Weapon or Both. Fragment pattern = Mode Fragment or Both. If no non-empty names, both are off. Note: `Enable = true` with `Mode = Never` still gives a weapon pattern. | `Definitions/SerializedConfigs/AmmoConstants.cs:1124-1183` |
| `Ewar.Field.GrowTime` / `TriggerRange` | Expanding field if GrowTime > 0. Trigger only if > 0. | `Definitions/SerializedConfigs/AmmoConstants.cs:1195`, `:1239` |
| `Sync.*` | All need `Sync.Full` and multiplayer. PointDefense also needs Health > 0, no beam and no EWAR. | `Definitions/SerializedConfigs/AmmoConstants.cs:618-623` |
| `AmmoGraphics.ModelName` | Starts with `\` means relative to ModPath. Otherwise used as a game path. | `Definitions/SerializedConfigs/AmmoConstants.cs:1253-1255` |
| `AmmoGraphics.Lines.Tracer.Length` | 0 or less becomes 0.1. Beams use MaxTrajectory. | `Definitions/SerializedConfigs/AmmoConstants.cs:1275-1277` |
| `AmmoGraphics.Lines.Tracer.Textures` | Null or empty becomes `TracerMaterial`. Empty entries are replaced by it too. Trail and segment textures work the same way. | `Definitions/SerializedConfigs/AmmoConstants.cs:986-1023` |
| `AmmoGraphics.Lines.Tracer.Segmentation` | Resize mode needs `Enable` and `SegmentLength > 0`. | `Definitions/SerializedConfigs/AmmoConstants.cs:973-976` |
| `AmmoGraphics.Lines.Tracer.VisualFadeStart/End` | Fade only if Start > 0 and End > 1. | `Definitions/SerializedConfigs/AmmoConstants.cs:598` |
| `AmmoGraphics.Lines.ColorVariance` | Both Start and End must be > 0. `WidthVariance` needs either one > 0. | `Definitions/SerializedConfigs/AmmoConstants.cs:893`, `:483` |
| `AmmoGraphics.Lines.Trail.CustomWidth` | 0 or less becomes `Tracer.Width`. | `Definitions/SerializedConfigs/AmmoConstants.cs:602` |
| `AmmoGraphics.Lines.OffsetEffect` | On only if MaxOffset > 0.2 and MinLength > 0.1. | `Definitions/SerializedConfigs/AmmoConstants.cs:1266` |
| `AmmoGraphics.Decals` | Used only with `MaxAge > 0` and a Map. | `Definitions/SerializedConfigs/AmmoConstants.cs:1025-1031` |
| `AmmoGraphics.AdvancedLines` | Off when `Beams.Enable`. Line `TimeRendered` 0 or less becomes 1. Trail `TimeRendered == 0` becomes 1 (quirk: negative kept). | `Definitions/SerializedConfigs/AmmoConstants.cs:654`, `:672`, `:715` |
| `AmmoAudio.ShotSound` | Empty: uses the weapon's `FiringSound` unless the ammo is shrapnel or `OverrideShotSound`. Voxel and shield hit sounds fall back to `HitSound`. | `Definitions/SerializedConfigs/AmmoConstants.cs:1408-1413`, `:1470`, `:1479` |

## 3. Cross-field requirements and common mistakes

Each item says what fails and how.

1. **Definitions sent too late.** They are never compiled (section 1). The block has no structure. On a dedicated server a turret or gun block without a structure is removed from the grid unless `Enforcement.UnsupportedMode`, or its subtype is in `VanillaWeaponCompatible` (`Session/SessionEvents.cs:71-78`, `Session/SessionSupport.cs:909-912`).
2. **Mount SubtypeId typo.** The def is dropped with no log (`Session/SessionInit.cs:606-610`). Then the same removal as item 1 applies.
3. **Subpart ids.** Give names without `subpart_`. Subparts are found from `subpart_<name>` dummies (`EntityComp/ModelSupport/RecursiveSubparts.cs:72-80`). `"None"` maps to the block itself (`EntityComp/PlatformInit.cs:134`). A missing muzzle, azimuth or elevation part calls `PlatformCrash` with suppress, which **stops WeaponCore for the session** (`EntityComp/PlatformInit.cs:200-224`). Only vanilla turret blocks default empty az/el ids to `MissileTurretBase1` / `MissileTurretBarrels` (`EntityComp/PlatformInit.cs:196-197`). Auto-generated defs fall back from a missing muzzle part to the elevation part (`EntityComp/PlatformInit.cs:204-207`).
4. **Muzzle dummies.** `Assignments.Muzzles` names are looked up as dummies in the muzzle part's model. A missing dummy gives **no error**. The dummy matrix falls back to identity, so shots leave the muzzle part's origin along its Forward (`EntityComp/ModelSupport/Dummies.cs:90-96`, `:141-145`). The muzzle count is `Muzzles.Length` (`EntityComp/Parts/Weapon/WeaponFields.cs:343`).
5. **Multi-weapon blocks need distinct `MuzzlePartId`.** For all weapon types the subtype map is keyed by `MuzzlePartId` (`Session/SessionInit.cs:273-274`). Two defs on one subtype with the same MuzzlePartId overwrite one map entry, but the part count is the def count (`Definitions/CoreStructure.cs:59`, `:72`). The empty part hash then fails in `WeaponParts`, giving `PlatformCrash` "Invalid weapon system ... duplicate partnames" with suppress (`EntityComp/PlatformInit.cs:189-192`). Quirk.
6. **Unique `PartName` per weapon on a subtype.** Same PartName and Type is treated as a duplicate and resolved by priority. The loser is dropped (`Session/SessionInit.cs:330-343`). Same PartName with a different Type keeps both, but the structure picks the last def with that name for each entry (`Definitions/CoreStructure.cs:83-94`).
7. **Do not mix part kinds on one block.** Weapons, upgrades, support and phantoms on one block crash with suppress (`EntityComp/PlatformInit.cs:186-187`, `:274-275`, `:291-292`).
8. **`Ammos[0]` must be selectable.** On add-to-scene, an active ammo that is not turret-selectable (shrapnel, or `HardPointUsable` false) is reset to index 0. If index 0 is not selectable either and the weapon has more than one ammo, `PlatformCrash` runs with suppress (`EntityComp/Parts/Weapon/WeaponComp.cs:247-270`). `HardPointUsable` defaults to false when omitted (`Definitions/CoreDefinitions.cs:740`).
9. **Empty `Ammos`.** The structure is left half built (`Definitions/CoreStructure.cs:96-100`).
10. **Damage scales left at 0.** Omitted `Grids` or `Armor` multipliers are 0, which means zero damage (section 2). The templates use `-1` (`Coreparts/Definitions/AmmoTypes.cs:50-58`).
11. **Magazine not found.** `GetAmmoMagazineDefinition` failure logs `No ammo magazine definition found for '...' used by '...'` and **rethrows** (`Definitions/SerializedConfigs/AmmoConstants.cs:367-377`). That path runs from `Session/SessionInit.cs:609`, which `Init` does not catch (`Session/SessionEvents.cs:24`).
12. **Energy weapons.** Use `AmmoMagazine = "Energy"` (template comment `Coreparts/Definitions/AmmoTypes.cs:37`). Energy ammo with `EnergyCost` 0 and no `EnergyMagazineSize` gives magazine size 0 and the "Girax" log (`Definitions/SerializedConfigs/AmmoConstants.cs:1389-1393`, `:570-571`). Energy ammo with `ReloadTime` 0 is not reloadable and never charges (`Definitions/SerializedConfigs/AmmoConstants.cs:1376`).
13. **Block needs an inventory.** Blocks other than phantom, turret-controller and searchlight run `InventoryInit` (`EntityComp/EntityRun.cs:79-80`). A block without an inventory crashes with suppress (`EntityComp/EntityInit.cs:46-48`). `InventorySize` 0 on every def gives a zero-volume inventory (`Session/SessionInit.cs:530-533`).
14. **Block type decides the component type.** Turret base gives VanillaTurret. Conveyor sorter gives Support, Upgrade or SorterWeapon, depending on which def list holds it. Turret control block gives Control. Searchlight gives SearchLight. Any other block gives VanillaFixed (`EntityComp/EntityFields.cs:180-216`).
15. **Turret AI flags.** The templates say turrets need `TrackTargets`, `TurretAttached` and `TurretController` all true (`Coreparts/Definitions/Gatlings.cs:62-64`). A part with `TurretAttached` but not `TrackTargets` shares the primary weapon's target (`EntityComp/Parts/Weapon/WeaponFields.cs:339-340`). Only `TurretController` parts drive turret movement (`EntityComp/Parts/Weapon/WeaponTracking.cs:29`). On vanilla turret blocks, aiming is WeaponCore's own (`AiOnlyWeapon`) unless the vanilla subpart names are used (`EntityComp/Parts/Weapon/WeaponFields.cs:395-397`).
16. **Beams and RateOfFire.** The template says "Set this to 3600 for beam weapons" (`Coreparts/Definitions/Gatlings.cs:85`). No code forces it. At 3600, `TicksPerShot` is 1 (`EntityComp/Parts/Weapon/WeaponController.cs:372`). A beam with any guidance other than `None` is not a beam (`Definitions/SerializedConfigs/AmmoConstants.cs:1261`).
17. **TargetLossDegree 180** (as in the templates, `Coreparts/Definitions/AmmoTypes.cs:82`) disables the target-loss cone (section 2).
18. **`ModPath` must be set.** A null ModPath leaves the structure empty (`Definitions/CoreStructure.cs:61-64`). Model paths starting with `\` and phantom models are joined to it (`Definitions/SerializedConfigs/AmmoConstants.cs:1255`, `Session/SessionInit.cs:367-368`). WeaponCore sets ModPath only for its own parts (`Coreparts/PartCompile.cs:50-63`).
19. **Designator.** A mount with `MuzzlePartId == "Designator"` skips the inventory and block-definition edits (`Session/SessionInit.cs:513-525`). It aims from the elevation part (`EntityComp/PlatformInit.cs:195`, `:328-332`).
20. **Construct part cap reached.** `PlatformCrash` without suppress ("over block limits"). Only that block fails (`EntityComp/PlatformInit.cs:122-131`).

## 4. Ammo and weapon identity

- **Magazine match.** `AmmoMagazine` is compared with the SubtypeId string of **every** loaded definition, of any type. The last match wins (`Definitions/CoreStructure.cs:149-152`). Energy matches subtype `Energy` (`:148`, `:151`). The auto-converter uses `MyObjectBuilder_AmmoMagazine/Energy` and `/Energy_Missile` (`Coreparts/AutoConverter.cs:170`).
- **Energy test after matching.** The matched id's subtype is `Energy` or empty (`Definitions/SerializedConfigs/AmmoConstants.cs:1371`). Energy ammo creates no physical `AmmoItem` (`:383`). Its magazine size comes from the energy rules, not the SBC capacity (`:568`).
- **Inventory filter.** The block inventory accepts the magazine of every ammo on every weapon of the block, shrapnel included. The terminal label lists only `HardPointUsable` magazines (`EntityComp/EntityInit.cs:73-81`, `:115-116`). Reloads count items by `AmmoDefinitionId` (`EntityComp/Parts/Weapon/WeaponReload.cs:76`).
- **`AmmoDefIds`** maps magazine id to ammo **globally**, and the last registration wins (`Definitions/CoreStructure.cs:161`). All energy ammos share the `Energy` key. Inventory code tests key membership (`Session/SessionInventory.cs:54`, `Ai/AiEvents.cs:285`).
- **`AmmoMaps[subtype][AmmoRound]`** maps per block subtype, across all its weapons. A duplicate AmmoRound on one block overwrites (`Definitions/CoreStructure.cs:163`). Magazine refunds use it (`EntityComp/Parts/Weapon/WeaponComp.cs:1121-1129`).
- **AmmoRound uniqueness inside one def.** Fragment lookup takes the last match (`Definitions/SerializedConfigs/AmmoConstants.cs:405-407`). Pattern lookup adds every match into an array sized by the pattern count, so a duplicate name used in a pattern overruns the array (`:1132-1140`, `:1160-1166`). Quirk.
- **Tag assignments** (`ProjectileTagAssignment.ProjectileAmmoNames`) match AmmoRound strings across all mods (`Session/SessionModHandlers.cs:126-136`, `Definitions/SerializedConfigs/AmmoConstants.cs:827-834`).
- **Queued name.** `AmmoNameQueued` is `"*" + AmmoRound` (`Definitions/CoreStructure.cs:160`).
- **`HardPoint.PartName`** is the terminal weapon name and part of the duplicate key (with SubtypeId and Type) (`Session/SessionInit.cs:330`). It names parts as `PartName + " " + partId` (`Definitions/CoreStructure.cs:107`). Upgrade and support handlers deduplicate by PartName alone (`Session/SessionModHandlers.cs:212`, `:241`).
- **Part hash.** `(SubtypeId + partNameIdHash + elevation + muzzle + azimuth).GetHashCode()` maps to the part id (`Definitions/CoreStructure.cs:167-168`). Upgrade and support use `SubtypeId + partNameIdHash` (`:273`, `:345`).
- **Weapon values maps.** `WeaponValuesMap` and `AmmoValuesMap` are keyed by the definition objects. They are filled with null at load (`Definitions/CoreStructure.cs:101`, `:159`). Server overrides fill them (`Support/VersionControl.cs:289`, `:329`), and `UpdateEnforcement` rebuilds the constants from them (`Session/SessionSupport.cs:1784-1806`).

## 5. Not confirmed

- The mod-side template that listens on 7772 and resends is not in this export. Whether weapon mods resend on 7772 was not checked.
- Whether protobuf leaves an omitted string as null or empty. Many checks compare with `string.Empty` only (`Definitions/CoreSystems.cs:676-696`, `:547-548`). A null `AmmoMagazine` would match no definition.
- `AmmoMagazine = ""` also matches any definition whose SubtypeId string is empty (`Definitions/CoreStructure.cs:151`). Which one wins, and what follows, was not tested. Use `"Energy"`.
- The game-side result of an exception escaping `Init` from `OnEntityCreate` (items 11 and section 1) was not checked.
- What a pattern name missing from `Ammos` does at fire time. It leaves a null slot (`Definitions/SerializedConfigs/AmmoConstants.cs:1158-1166`), and the later use of that slot was not traced.
- A legacy `WeaponDefinition[]` payload might parse "successfully" as a `ContainerDefinition`. In that case the legacy path would never run. Not tested.
- Template claims of "0 = unlimited" for `TopTargets` and `TopBlocks` (`Coreparts/Definitions/Gatlings.cs:42-43`) were not traced into `Ai/AiTargeting.cs`.
- A primary weapon with `TurretAttached` but not `TrackTargets` takes its own, still unset, `Target` (`EntityComp/Parts/Weapon/WeaponFields.cs:336-340`). The runtime effect was not checked.
- The exact folder of WeaponCore's local-storage logs.
