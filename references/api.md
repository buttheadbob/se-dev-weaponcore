# WeaponCore API (mod API, PB API, callbacks, MES usage)

Source: WeaponCore commit 25985a9 (2026-11-05). Paths are relative to Data/Scripts/CoreSystems/.
MES paths are `MES:<path>:line`, relative to the MES repo root (commit a1895d9, 2026-10-24).

Table shorthand (used only inside the tables):
- `W:n` = `Api/CoreSystemsApiBase.cs:n` (wrapper method), `K:n` = the `AssignMethod` line in the same file.
- `D:n` = key in the `ModApiMethods` dictionary, `B:n` = backend method, both in `Api/ApiBackend.cs`.
- `P:n` = `Api/CoreSystemsPbApi.cs:n`, `PD:n` = key in `PbApiMethods` (`Api/ApiBackend.cs`).

## 1. Files

| File | Role |
|---|---|
| `Api/CoreSystemsApiBase.cs` | `WcApi` partial class a mod copies. Holds the fields, wrappers, handshake, `DamageHandlerHelper` (`Api/CoreSystemsApiBase.cs:17`, `:809`). |
| `Api/CoreSystemsApiBlocks.cs` | `GetBlockWeaponMap` part of `WcApi` (`Api/CoreSystemsApiBlocks.cs:14`). |
| `Api/CoreSystemsApiPhantoms.cs` | Phantom part of `WcApi`. All its wrappers are `internal` (`Api/CoreSystemsApiPhantoms.cs:37-111`). Inside one mod assembly they still compile. |
| `Api/CoreSystemsApiDefs.cs` | `WcApiDef`, a ProtoContract copy of the definition classes (`Api/CoreSystemsApiDefs.cs:7-18`), used to deserialize `GetAllWeaponDefinitions` (`Api/CoreSystemsApiBase.cs:777`). |
| `Api/CoreSystemsPbApi.cs` | `WcPbApi`, the class a PB script copies (`Api/CoreSystemsPbApi.cs:11-16`). |
| `Api/ApiServer.cs` | WC side of the mod-message handshake (`Api/ApiServer.cs:8-58`). |
| `Api/ApiBackend.cs` | Builds `ModApiMethods` and `PbApiMethods` and implements every delegate (`Api/ApiBackend.cs:26-27`, `:32-177`, `:179-230`). |

## 2. Getting the mod API

Channel: `67549756549`, the same constant on both sides (`Api/CoreSystemsApiBase.cs:551`, `Api/ApiServer.cs:10`).

Mod side, `WcApi.Load(Action readyCallback = null, bool getWeaponDefinitions = false)` (`Api/CoreSystemsApiBase.cs:629`):
1. Throws if called twice without `Unload()` (`Api/CoreSystemsApiBase.cs:631-632`).
2. Registers `HandleMessage` on the channel, then sends the string `"ApiEndpointRequest"` (`Api/CoreSystemsApiBase.cs:637-638`).
3. `HandleMessage` ignores strings (its own request echoes back) and ignores everything once `_apiInit` is set (`Api/CoreSystemsApiBase.cs:654-656`).
4. A non-null `IReadOnlyDictionary<string, Delegate>` goes to `ApiAssign`, then `IsReady = true`, then `readyCallback` runs (`Api/CoreSystemsApiBase.cs:658-666`).

WC side:
- `ApiServer.Load()` registers its handler once, sets `IsReady`, and broadcasts `ModApiMethods` unprompted, wrapped in try/catch (`Api/ApiServer.cs:28-42`).
- On `"ApiEndpointRequest"` it replies with `Session.I.Api.ModApiMethods` (`Api/ApiServer.cs:17-21`). This reply is not wrapped in try/catch.
- `ApiServer.Load()` is called from `Session.LoadData` after `ModChecker()`, and only when `SuppressWc` is false (`Session/SessionRun.cs:351`, `:395-400`). It runs before `IsServer` is even assigned (`Session/SessionRun.cs:402`), with no server check, so the mod API exists on server, client and DS alike.
- So both load orders work. A mod registered before WC's `LoadData` gets the broadcast. A mod registering later gets the reply to its request.
- `SuppressWc` comes from `SUtils.ModActivate` unless the mod is a local "CoreSystems"/"WeaponCore" copy (`Session/SessionSupport.cs:1170`, `:1200`). It picks one active copy when several WC forks are loaded (`Support/StaticUtils.cs:15-59`). A suppressed copy never answers.

If WC is absent or suppressed:
- Nobody replies. `IsReady` stays false and `readyCallback` never fires (`Api/CoreSystemsApiBase.cs:665-666`).
- Wrappers written with `?.` return defaults: `false`, `0f`, `-1`, `null`, `Matrix.Zero` or an empty tuple (e.g. `Api/CoreSystemsApiBase.cs:125`, `:159`, `:191`).
- quirk: three wrappers have no `?.` and throw `NullReferenceException` when the API never arrived: `TargetFocushandler` (`Api/CoreSystemsApiBase.cs:360`), `RegisterSubsystemBlockFilter` (`:610`) and `RemoveSubsystemFilter` (`:620`). `DamageHandlerHelper.RegisterForDamage` is safe, because it goes through `RegisterDamageEvent`, which uses `?.` (`:827`, `:350`).

Version and compatibility:
- There is no version number. `AssignMethod` throws when a key is missing or has a different delegate type (`Api/CoreSystemsApiBase.cs:799-806`).
- A wrapper newer than the running WC therefore throws inside `HandleMessage`. Fields assigned before the missing key stay set, and `IsReady` is never set (`Api/CoreSystemsApiBase.cs:663-665`).
- Old wrappers keep working, because WC keeps legacy keys (IMyTerminalBlock/IMyEntity versions such as `"GetWeaponTarget"`, `"MonitorProjectile"`, `"SetAiFocus"`) beside the `...Base` MyEntity keys (`Api/ApiBackend.cs:34-35`, `:73-149`).
- `getWeaponDefinitions: true` deserializes every `byte[]` into `WcApiDef.WeaponDefinition` during `ApiAssign` (`Api/CoreSystemsApiBase.cs:772-778`), from `Session.I.WeaponDefinitions` (`Api/ApiBackend.cs:692-696`). It fills the public `WeaponDefinitions` list (`Api/CoreSystemsApiBase.cs:564`).

Unload:
- `WcApi.Unload()` unregisters the handler, nulls every field via `ApiAssign(null)`, and clears `_isRegistered`, `_apiInit` and `IsReady` (`Api/CoreSystemsApiBase.cs:641-650`, `:792-796`).
- `ApiServer.Unload()` unregisters and broadcasts an empty `Dictionary<string, Delegate>` (`Api/ApiServer.cs:48-57`), from `Session.UnloadData` (`Session/SessionRun.cs:419`, `:470`).
- quirk: a ready client ignores that empty dictionary because `_apiInit` is already true (`Api/CoreSystemsApiBase.cs:654`), so it keeps stale delegates. A client that registered but was never initialized would pass the empty dictionary to `ApiAssign`, which throws on the first missing key (`Api/CoreSystemsApiBase.cs:799-800`).

## 3. Getting the PB API

- The PB copies `WcPbApi` and calls `Activate(Me)`. That reads terminal property `"WcPbAPI"` as `IReadOnlyDictionary<string, Delegate>` and throws `"WcPbAPI failed to activate"` when it is null (`Api/CoreSystemsPbApi.cs:78-83`).
- `ApiAssign` then throws on any missing or mistyped key (`Api/CoreSystemsPbApi.cs:93-175`).
- WC creates the property in `PbInit()` with `CreateProperty<IReadOnlyDictionary<string, Delegate>, IMyTerminalBlock>("WcPbAPI")`. Its getter returns an immutable copy of `PbApiMethods`, and the property is added to `IMyProgrammableBlock` controls (`Api/ApiBackend.cs:232-248`).
- `PbInit` runs only when `IsServer && PbActivate && !PbApiInited`, checked once every 120 ticks in `Timings()` (`Session/SessionSupport.cs:33`, `:87-95`). `PbActivate` is set when the first `IMyProgrammableBlock` entity is created (`Session/SessionEvents.cs:22`, `:40`).
- quirk: so the property can be missing for up to about 2 s after the first PB appears. On MP clients it never exists. A script that calls `Activate` at world load can throw.
- What a PB can do is exactly the `PbApiMethods` set (`Api/ApiBackend.cs:179-230`): IDs as `long`, results as `MyDetectedEntityInfo`, no entity references handed out. There are no phantom, damage, handler, scan-filter or definition-blob calls.

## 4. Common backend behaviour (mod API)

- Block methods fetch `weaponBlock.Components.Get<CoreComponent>() as Weapon.WeaponComponent` and require `comp?.Platform != null`, `Platform.State == Ready` and `Weapons.Count > weaponId`; otherwise they return the default (e.g. `Api/ApiBackend.cs:1119-1130`).
- Passing a `null` entity throws, because `.Components` is dereferenced without a check (e.g. `Api/ApiBackend.cs:1119`).
- Passing a non-WC entity returns the default. Passing a WC block whose platform is not `Ready` yet (just spawned) also returns the default.
- Grid-level methods use `entity.GetTopMostParent()` and look up `Session.I.EntityAIs` or `Session.I.EntityToMasterAi` (e.g. `Api/ApiBackend.cs:986-990`, `:1001-1009`).
- None of the read methods clear the caller's collection unless noted.

## 5. Mod API method table

### Targeting

| Method | Key | Backend behaviour |
|---|---|---|
| `MyTuple<bool,bool,bool,MyEntity> GetWeaponTarget(MyEntity weapon, int weaponId = 0)` W:236 | `GetWeaponTargetBase` K:712 D:128 | Returns (isEntity, isProjectile, isFake, entity). Fake gives (true,false,true,null) and projectile gives (true,true,false,null); otherwise Item1 = `TargetState == IsEntity` and Item4 = `TargetObject`. Invalid gives all false/null. B:1117-1131 |
| `void SetWeaponTarget(MyEntity weapon, MyEntity target, int weaponId = 0)` W:114 | `SetWeaponTargetBase` K:713 D:130 | `Ai.AcquireTarget(weapon, false, target)`. No server check. B:1134-1139 |
| `bool IsTargetAligned(MyEntity weapon, MyEntity targetEnt, int weaponId)` W:139 | `IsTargetAlignedBase` K:721 D:101 | Writes `w.NewTarget.TargetObject = targetEnt` (side effect). Returns false when beyond `MaxTargetDistanceSqr`, else `Weapon.TargetAligned`. B:1283-1301 |
| `MyTuple<bool,Vector3D?> IsTargetAlignedExtended(MyEntity weapon, MyEntity targetEnt, int weaponId)` W:142 | `IsTargetAlignedExtendedBase` K:722 D:103 | Returns (false,null) while the comp is in `TrackingReticle` mode. Has no range check. Returns the predicted position only when aligned. B:1303-1321 |
| `bool CanShootTarget(MyEntity weapon, MyEntity targetEnt, int weaponId)` W:145 | `CanShootTargetBase` K:723 D:105 | Range check, then `Weapon.CanShootTargetObb` with the top parent's linear velocity and its *angular* acceleration passed as accel. B:1344-1365 |
| `Vector3D? GetPredictedTargetPosition(MyEntity weapon, MyEntity targetEnt, int weaponId)` W:148 | `GetPredictedTargetPositionBase` K:724 D:107 | Null beyond the ammo's `MaxTrajectorySqr`. Otherwise writes `NewTarget` and returns the `TargetAligned` position even when not aligned. B:1368-1383 |
| `bool IsTargetValid(MyEntity weapon, MyEntity target, bool onlyThreats, bool checkRelations)` W:196 | `IsTargetValidBase` K:738 D:84 | Target must be in `comp.MasterAi.Targets` and not closing. Threat means `OffenseRating > 0`. Relations check the comp's Unowned/Neutrals/Friendly overrides; enemies always pass. B:1666-1703 |
| `bool GetTurretTargetTypes(MyEntity weapon, IList<string> collection, int weaponId = 0)` W:130 | `GetTurretTargetTypesBase` K:718 D:116 | quirk: adds the *definition's* `Targeting.Threats` names, not the current terminal settings. B:1186-1197 |
| `void SetTurretTargetTypes(MyEntity weapon, IList<string> collection, int weaponId = 0)` W:133 | `SetTurretTargetTypesBase` K:719 D:118 | quirk: for each named threat the definition allows, it *flips* the matching override (`enabled ? 0 : 1`). It is a toggle, not a set. Only Projectiles, Characters, Grids, Neutrals, Meteors and Other map to overrides. B:1202-1255 |
| `void SetBlockTrackingRange(MyEntity weapon, float range)` W:136 | `SetBlockTrackingRangeBase` K:720 D:120 | Clamps to the largest min(hardpoint max, ammo max trajectory) over the block's weapons. Returns silently if any weapon has no active ammo. Calls `BlockUi.RequestSetRange`, which applies on the server and sends `SendComp`, or sends a request from a client. B:1258-1281, `EntityComp/Controls/Weapon/WeaponUi.cs:40-56` |
| `float GetMaxWeaponRange(MyEntity weapon, int weaponId)` W:127 | `GetMaxWeaponRangeBase` K:717 D:114 | `Weapons[id].MaxTargetDistance`, or 0. B:1177-1184 |
| `void GetSortedThreats(MyEntity shooter, ICollection<MyTuple<MyEntity,float>> c)` W:227 | `GetSortedThreatsBase` K:687 D:136 | Adds (Target, OffenseRating) from the top entity's `Ai.SortedTargets`. B:986-998 |
| `void GetObstructions(MyEntity shooter, ICollection<MyEntity> c)` W:229 | `GetObstructionsBase` K:688 D:138 | Top parent must be a `MyCubeGrid`. Adds `Ai.Obstructions[i].Target`. B:251-260 |
| `MyEntity GetAiFocus(MyEntity shooter, int priority = 0)` W:231 | `GetAiFocusBase` K:693 D:144 | `MyEntities.GetEntityById(Construct.Data.Repo.FocusData.Target)`. quirk: `priority` is unused. B:1001-1012 |
| `bool SetAiFocus(MyEntity shooter, MyEntity target, int priority = 0)` W:232 | `SetAiFocusBase` K:694 D:75 | Server only (false on a client) and needs a valid root AI. Calls `Focus.ServerChangeFocus(target, ai, 0, Add, apiCalled: true)`. quirk: `priority` is unused. B:1015-1033 |
| `bool ReleaseAiFocus(MyEntity shooter, long playerId)` W:234 | `ReleaseAiFocusBase` D:57 and D:64 (duplicate key, the second wins) K:695 | Server only. `Focus.RequestReleaseActive(ai, playerId)`. B:1036-1054 |
| `MyTuple<bool,bool> IsInRange(MyEntity entity)` W:256 | `IsInRangeBase` K:699 D:146 | (`DetectionInfo.PriorityInRange`, `OtherInRange`) of the top entity's AI. B:1720-1729 |
| `void AddScanTargetsAction(Action<MyCubeGrid,BoundingSphereD,List<MyEntity>>)` W:536 / `RemoveScanTargetsAction` W:542 | K:765/766 D:150/151 | Multicast `+=` / `-=` on `Session.ScanTargetsAction` (B:1731-1739). When it is set, it *replaces* the pruning sphere query in `Ai.Scan` (`Ai/AiDatabase.cs:44-47`). Not networked (wrapper doc W:533). |
| `void SetValidateWeaponTargetFunc(Func<IMyTerminalBlock,int,MyEntity,bool>)` W:548 | K:767 D:152 | Plain assignment, so the last mod wins (B:1741-1744). A false return skips the target in target acquisition (`Ai/AiTargeting.cs:252-254`). |
| `void RegisterSubsystemBlockFilter(string id, Func<MyCubeBlock,string> display, Func<MyCubeBlock,int,MyCubeBlock,int,bool> predicate)` W:608 | K:785 D:175 | No `?.` (W:610). Throws on a duplicate id (B:2035-2040). Predicate args are (weapon block, partId, target block, `(int)BlockTypes`), applied after WC's own checks (`EntityComp/Parts/Weapon/WeaponTracking.cs:1654-1671`). B:2063-2074 |
| `bool RemoveSubsystemFilter(string id)` W:618 | `RemoveSubsystemBlockFilter` K:786 D:176 | No `?.` (W:620). Nulls the customization when it is empty. B:2076-2094 |
| `RegisterTrajectoryPredictionShipVelocityConstraint(Func<MyCubeGrid,MyTuple<double,bool>>)` W:572, `...ShipAccelEstimator(Func<MyCubeGrid,Vector3D>)` W:582, `...ExternalForce(Func<MyCubeGrid,Vector3D,Vector3D,Vector3D>)` W:593 | K:780-782 D:170-172 | Each can be set once per session across *all* mods. A second call throws (B:1967-1997). Used in target prediction (`EntityComp/Parts/Weapon/WeaponTracking.cs:1121-1155`). |

### Firing

| Method | Key | Backend behaviour |
|---|---|---|
| `void FireWeaponOnce(MyEntity weapon, bool allWeapons = true, int weaponId = 0)` W:117 | `FireWeaponOnceBase` K:714 D:122 | `ShootManager.RequestShootSync(Session.I.PlayerId, Once, Once)` for the *whole comp*. quirk: `allWeapons` and `weaponId` only feed the bounds check. B:1142-1149 |
| `void ToggleWeaponFire(MyEntity weapon, bool on, bool allWeapons, int weaponId = 0)` W:120 | `ToggleWeaponFireBase` K:715 D:124 | `RequestShootSync(0, on ? On : Off, Signals.On)` for the whole comp. Same quirk. B:1151-1159 |
| `bool IsWeaponReadyToFire(MyEntity weapon, int weaponId = 0, bool anyWeaponReady = true, bool shootReady = false)` W:123 | `IsWeaponReadyToFireBase` K:716 D:126 | Needs `comp.IsWorking`. Returns true if any weapon (or only `weaponId` when `anyWeaponReady` is false) has `ShotReady`. quirk: `shootReady` is unused. B:1161-1175 |
| `bool ShootRequest(MyEntity weaponEntity, object target, int weaponId = 0, double additionalDeviateShotAngle = 0)` W:426 | `ShootRequest` K:709 D:62 | `Weapon.ShootRequest.Update`. False if a request is pending, ammo is 0, the weapon is loading or waiting for the client, or reloads are exhausted. Target may be `MyEntity`, `Vector3D?` or `ulong?` (projectile id); anything else is cleaned and returns false. Each accepted request issues `RequestShootSync(PlayerId, Once, Once)`. B:888-897, `EntityComp/Parts/Weapon/WeaponTypes.cs:207-254` |

`RequestShootSync` sends ShootSync packets when MP is active: the server as `ServerRequest`/`ServerRelay`, a client as `ClientRequest` (`EntityComp/Parts/Weapon/WeaponTypes.cs:342-384`).

### Ammo

| Method | Key | Backend behaviour |
|---|---|---|
| `string GetActiveAmmo(MyEntity weapon, int weaponId)` W:182 | `GetActiveAmmoBase` K:733 D:95 | `ActiveAmmoDef.AmmoDef.AmmoRound`, or null. B:1534-1541 |
| `void SetActiveAmmo(MyEntity weapon, int weaponId, string ammoType)` W:185 | `SetActiveAmmoBase` K:734 D:97 | Server only. Matches `AmmoRound` and needs `IsTurretSelectable`. Sets `Reload.AmmoTypeId` and calls `SendWeaponReload` in MP. Silent no-op otherwise. B:1544-1566 |
| `MyTuple<MyDefinitionId,string,string,bool> GetMagazineMap(MyEntity weapon, int weaponId)` W:501 | `GetMagazineMap` K:760 D:65 | (ammo definition id, `AmmoMagazine`, `AmmoRound`, `Const.SkipAimChecks`). B:1056-1078 |
| `bool SetMagazine(MyEntity weapon, int weaponId, MyDefinitionId id, bool forceReload)` W:514 | `SetMagazine` K:762 D:66 | `id` must be in `Session.AmmoDefIds`. Calls `QueueAmmoChange(AmmoIdxPos)` (B:1092-1108), which accepts on the server when not loading and on a client when no reload is pending (`EntityComp/Parts/Weapon/WeaponReload.cs:128-141`). With `forceReload` it then calls `Comp.ForceReload()`; see the next row. |
| `bool ForceReload(MyEntity weapon, int weaponId)` W:526 | `ForceReload` K:763 D:67 | Calls `WeaponComponent.ForceReload()` (B:1080-1090). quirk: that method writes `Rifle.CurrentMagazineAmount` first (`EntityComp/Parts/Weapon/WeaponHand.cs:71-76`), and `Rifle` is only assigned for handheld rifles (`EntityComp/Parts/Weapon/WeaponComp.cs:68`, `:135-138`). On a block weapon this reads as a `NullReferenceException` thrown back to the caller. |

### Heat and power

| Method | Key | Backend behaviour |
|---|---|---|
| `float GetHeatLevel(MyEntity weapon)` W:151 | `GetHeatLevelBase` K:725 D:109 | `comp.CurrentHeat` (sum over weapons), 0 if `MaxHeat <= 0`. B:1406-1414 |
| `int GetWeaponMaxHeatLevel(MyEntity weapon, int weaponId)` W:159 | `GetMaxWeaponHeatLevel` K:726 D:111 | `System.MaxHeat`, or -1. B:1416-1424 |
| `float GetWeaponHeatLevel(MyEntity weapon, int weaponId)` W:166 | `GetWeaponHeatLevel` K:727 D:112 | `PartState.Heat`, or -1. B:1426-1434 |
| `bool SetWeaponHeatLevel(MyEntity weapon, int weaponId, float heat)` W:175 | `SetWeaponHeatLevel` K:728 D:113 | Sets `PartState.Heat` and recomputes `CurrentHeat`. Local only; the wrapper says to sync it yourself (W:169). B:1436-1451 |
| `float GetCurrentPower(MyEntity weapon)` W:176 | `GetCurrentPowerBase` K:729 D:88 | `comp.SinkPower`. B:1454-1461 |
| `float GetMaxPower(MyDefinitionId weaponDef)` W:238 | `GetMaxPower` K:689 D:51 | `MaxPowerMW + CombinedIdlePower` of the part platform. B:1463-1472 |
| `void DisableRequiredPower(MyEntity weapon)` W:177 | `DisableRequiredPowerBase` K:730 D:91 | `ModOverride` (B:1475-1485): sets `comp.ModOverride` and `Ai.ModOverride` to true, then `ResourceSink.Update()`. Local, no sync found in the method. |
| `void EnableRequiredPower(MyEntity weapon)` W:178 | `EnableRequiredPowerBase` K:731 D:90 | `ModOverrideOff`, which sets both flags to false. B:1487-1497 |
| `bool ToggleInfiniteResources(MyEntity entity)` W:317 | `ToggleInfiniteAmmoBase` K:757 D:70 | Weapon entity: flips `comp.InfiniteResource`. Grid/top entity: `Construct.GiveAllCompsInfiniteResources()` flips the construct flag across all AIs in the group. Returns the new state. B:823-838, `Ai/AiConstruct.cs:918-929` |

### Projectiles

| Method | Key | Backend behaviour |
|---|---|---|
| `MyTuple<bool,int,int> GetProjectilesLockedOn(MyEntity victim)` W:215 | `GetProjectilesLockedOnBase` K:690 D:71 | Counts `ai.LiveProjectile` entries with value true on the victim's master AI. Returns (true, count, ticks since `LiveProjectileTick`) or (false,0,-1). B:933-951 |
| `void GetProjectilesLockedOnPos(MyEntity victim, ICollection<Vector3D> c)` W:220 | `GetProjectilesLockedOnPos` K:691 D:72 | Clears `c`, then adds the positions of the same set. B:953-968 |
| `void GetAllSmartProjectiles(ICollection<MyTuple<ulong,Vector3D,int,long>> c)` W:225 | `GetAllSmartProjectiles` K:692 D:74 | Clears `c`. Adds (Id, Position, Age, FactionId) for every active projectile whose ammo `IsSmart`. B:970-981 |
| `MyTuple<Vector3D,Vector3D,float,float,long,string> GetProjectileState(ulong id)` W:241 | `GetProjectileState` K:700 D:56 | (Position, Velocity, BaseDamagePool, BaseHealthPool, Target.TargetId, AmmoRound). Only works for projectiles in `Session.MonitoredProjectiles`, which exist only while the firing weapon has at least one projectile monitor (`Projectiles/Projectile.cs:355-358`). B:1614-1621 |
| `void SetProjectileState(ulong id, MyTuple<bool,Vector3D,Vector3D,float> v)` W:268 | `SetProjectileState` K:701 D:164 | Same `MonitoredProjectiles` limit. Item1 true means early end (the rest is ignored). Otherwise Item2 sets the position unless `Vector3D.MinValue`, Item3 is *added* to the velocity unless `MinValue`, Item4 sets BaseDamagePool when `> float.MinValue`. Local only. B:1624-1652 |
| `AddProjectileCallback(MyEntity entity, int weaponId, Action<long,int,ulong,long,Vector3D,bool>)` W:248 / `RemoveProjectileCallback` W:251 | `AddMonitorProjectile` / `RemoveMonitorProjectile` K:703/704 D:55/54 | Adds to or removes from `comp.ProjectileMonitors[weaponId]`. Needs only `Platform != null` and the bounds check, not Ready. B:1598-1611. See section 7. |

### Events and handlers

| Method | Key | Backend behaviour |
|---|---|---|
| `MonitorEvents(MyEntity entity, int partId, Action<int,bool>)` W:327 / `UnMonitorEvents` W:337 | `RegisterEventMonitor` / `UnRegisterEventMonitor` K:758/759 D:166/167 | Adds to or removes from `comp.EventMonitors[partId]` (B:901-914). See section 7. |
| `void RegisterDamageEvent(long modId, int type, Action<ListReader<...>>)` W:348 | `DamageHandler` K:770 D:165 | 0 unregisters, 1 is `SystemWideDamageEvents` (W:889-893). Keyed by `modId`. B:1942-1964. See section 7. |
| `void TargetFocushandler(long handledEntityId, bool unregister)` W:358 | `TargetFocusHandler` K:706 D:59 | No `?.` (W:360). Always passes the wrapper's own private `TargetFocusCallback` (W:371-376), so you must edit the wrapper to change behaviour. Backend: one handler per id; registering an existing id returns false; unregister removes it (B:844-854). |
| `void Hudhandler(long handledEntityId, bool unregister)` W:389 | `HudHandler` K:707 D:60 | Same pattern with the private `HudCallback` (W:401-406). B:860-870 |
| `void ShootRequestHandler(long handledEntityId, bool unregister, Func<Vector3D,Vector3D,int,bool,object,int,int,int,bool> cb)` W:434 | `ShootHandler` K:708 D:61 | Your callback, one per id. B:876-886 |

### Definitions

| Method | Key | Backend behaviour |
|---|---|---|
| `GetAllWeaponDefinitions(IList<byte[]>)` W:199 | K:673 D:38 | Protobuf blobs of `Session.WeaponDefinitions`. B:692-696 |
| `GetAllCoreWeapons(ICollection<MyDefinitionId>)` W:200 | `GetCoreWeapons` K:674 D:44 | All values of `Session.CoreSystemsDefs` (B:698-702), the same map `SpawnPhantom` indexes by subtype (`Session/SessionSupport.cs:1350`). |
| `GetNpcSafeWeapons(...)` W:201 | K:675 D:42 | `Session.NpcSafeWeaponDefs.Values`. B:704-708 |
| `GetAllCoreStaticLaunchers` W:203 / `GetAllCoreTurrets` W:207 / `GetAllCorePhantoms` W:208 / `GetAllCoreRifles` W:209 | K:680-683 D:45-48 | `CoreSystemsFixedBlockDefs` / `CoreSystemsTurretBlockDefs` / `CoreSystemsPhantomDefs` / `CoreSystemsRifleDefs`. B:756-783 |
| `GetAllCoreArmors(IList<byte[]>)` W:210 | K:684 D:49 | Protobuf blobs of `CoreSystemsArmorDefs`. B:774-778 |
| `GetAllWeaponMagazines(IDictionary<MyDefinitionId, List<MyTuple<int, MyTuple<MyDefinitionId,string,string,bool>>>>)` W:204 / `GetAllNpcSafeWeaponMagazines` W:205 | K:677/678 D:39/41 | Clears the dictionary. One list per key of `SubTypeIdToWeaponMagMap` / `SubTypeIdToNpcSafeWeaponMagMap`, entries (WeaponId, (ammo def id, AmmoMagazine, AmmoRound, SkipAimChecks)). B:710-754 |
| `bool GetBlockWeaponMap(IMyTerminalBlock block, IDictionary<string,int> c)` `Api/CoreSystemsApiBlocks.cs:14` | `GetBlockWeaponMap` K:686 D:36 | False unless the block definition maps to a `WeaponStructure`. Adds PartName to WeaponId and skips existing keys. A null block throws (`.SlimBlock`). B:916-930 |

### Misc and info

| Method | Key | Backend behaviour |
|---|---|---|
| `bool HasCoreWeapon(MyEntity weapon)` W:180 | `HasCoreWeaponBase` K:732 D:93 | `Components.Has<CoreComponent>()`, true for any WC comp, not only weapons. B:1508-1511 |
| `bool HasAi(MyEntity entity)` W:239 | `HasGridAiBase` K:696 D:142 | Top parent is in `EntityAIs`. B:1500-1505 |
| `float GetOptimalDps(MyEntity entity)` W:240 | `GetOptimalDpsBase` K:697 D:140 | quirk: any `IMyTerminalBlock` takes the comp branch and returns `PeakDps`, or 0 for a non-weapon block. Only non-terminal entities (a grid) return `ai.OptimalDps`. B:1514-1531 |
| `float GetConstructEffectiveDps(MyEntity entity)` W:244 | `GetConstructEffectiveDpsBase` K:698 D:148 | Master AI `EffectiveDps`. B:1655-1663 |
| `long GetPlayerController(MyEntity weapon)` W:188 | `GetPlayerControllerBase` K:735 D:99 | `Data.Repo.Values.State.PlayerId`, or -1. B:786-793 |
| `Matrix GetWeaponAzimuthMatrix(MyEntity weapon, int weaponId)` W:190 / `GetWeaponElevationMatrix` W:193 | K:736/737 D:132/134 | Local matrix of the azimuth/elevation part. quirk: no `weaponId` bounds check, so an out-of-range id throws. B:796-821 |
| `MyTuple<Vector3D,Vector3D> GetWeaponScope(MyEntity weapon, int weaponId)` W:245 | `GetWeaponScopeBase` K:739 D:86 | (`GetScope.Info.Position`, `Direction`). B:1706-1716 |
| `internal IsWeaponShooting` W:278, `GetShotsFired` W:287, `GetMuzzleInfo` W:297, `GetMuzzleParentEntity` W:309 | K:752-755 D:82/77/79/80 | ANPaL helpers. quirk: `IsWeaponShooting`, `GetMuzzleInfo` and `GetMuzzleParentEntity` do not null-check `comp`, so a non-WC entity throws. `GetShotsFired` returns -1. None check Ready. B:1878-1938 |

### Phantoms (`Api/CoreSystemsApiPhantoms.cs`, all `internal`)

| Method | Key | Backend behaviour |
|---|---|---|
| `void GetTargetAssessment(MyEntity phantom, MyEntity target, int weapon = 0, bool mustBeInrange = false, bool checkTargetOrb = false)` :37 | `GetTargetAssessment` K:742 D:155 | quirk: the wrapper returns `void`, so the backend's (aligned, inRange, pos) tuple is thrown away. quirk: with `checkTargetObb` false the backend tests `w.NewTarget` without assigning `target` to it. B:1750-1781 |
| `void SetTriggerState(MyEntity phantom, TriggerActions trigger)` :51 | `SetTriggerState` K:744 D:157 | Server only. `ResetShootState((Trigger)trigger, ai.AiOwner)`. Logs on failure. B:1853-1864 |
| `void AddMagazines(MyEntity phantom, int weapon, long quanity)` :59 | `AddMagazines` K:745 D:158 | quirk: *sets* `Reload.CurrentMags = (int)magCount`; it does not add. B:1838-1851 |
| `void SetAmmo(MyEntity phantom, int weapon, string ammoName)` :66 | `SetAmmo` K:746 D:159 | `ChangeAmmo` on the first matching `AmmoRound`. B:1816-1836 |
| `bool ClosePhantom(MyEntity phantom)` :72 | `ClosePhantom` K:747 D:160 | `ForceClose` unless `CloseCondition` is already set. B:1804-1814 |
| `MyEntity SpawnPhantom(string phantomType, uint maxAge = 0, bool closeWhenOutOfAmmo = false, long defaultReloads = long.MaxValue, string ammoOverideName = null, TriggerActions trigger = TriggerOff, float? modelScale = null, MyEntity parnet = null, bool addToPrunning = false, bool shadows = false, long identityId = 0, bool sync = false)` :101 | `SpawnPhantom` K:748 D:162 | `Session.CreatePhantomEntity` (B:1798-1802). An unknown subtype throws `KeyNotFoundException` from `CoreSystemsDefs[phantomType]` (`Session/SessionSupport.cs:1350`). `sync:false` makes the entity a preview entity with no sync (`Session/SessionSupport.cs:1349-1356`). |
| `bool SetPhantomFocusTarget(MyEntity phantom, MyEntity target, int focusId)` :111 | `SetFocusTarget` K:749 D:161 | Server only. quirk: `focusId` is unused; it always calls `ServerChangeFocus(..., Add, true)`. B:1784-1797 |

### Keys in `ModApiMethods` with no current wrapper

- Legacy IMyTerminalBlock/IMyEntity variants (`Api/ApiBackend.cs:34-35`, `:73-149`).
- `RegisterProjectileAdded` / `UnRegisterProjectileAdded` (`Api/ApiBackend.cs:52-53`). quirk: they edit `Session.ProjectileAddedCallback` (`Api/ApiBackend.cs:1568-1583`), but nothing in the tree invokes that field. Its only occurrence is the declaration (`Session/SessionFields.cs:350`), so the callback never fires.
- `ToggleDamageEvents`, whose body is empty (`Api/ApiBackend.cs:163`, `:1870-1872`).

### Server-only and sync summary

- Return false or do nothing on a client: `SetAiFocus`, `ReleaseAiFocus` (`Api/ApiBackend.cs:1025`, `:1046`), `SetActiveAmmo` (`:1547`), `SetPhantomTriggerState` (`:1857`), `SetPhantomFocusTarget` (`:1789`).
- Networked by WC: the fire calls through ShootSync (`EntityComp/Parts/Weapon/WeaponTypes.cs:363-379`), `SetBlockTrackingRange` (`EntityComp/Controls/Weapon/WeaponUi.cs:48-55`), `SetActiveAmmo` (`Api/ApiBackend.cs:1557-1558`).
- Local only (no send in the backend method): `SetWeaponHeatLevel`, `SetProjectileState`, `Disable/EnableRequiredPower`, `ToggleInfiniteResources`, scan/validate/subsystem/trajectory registrations (`Api/ApiBackend.cs:1436-1451`, `:1624-1652`, `:1475-1497`, `:823-838`, `:1731-1744`).

## 6. PB API table (`WcPbApi`)

PB wrappers all use `?.` and return defaults when unbound (`Api/CoreSystemsPbApi.cs:183-748`). Unless noted, each PB backend casts the block to `MyEntity` and calls the same backend as the mod API.

| PB method (`P:` line) | Key (`PD:`) | Backend / difference |
|---|---|---|
| `GetAllCoreWeapons` 183, `GetAllCoreStaticLaunchers` 191, `GetAllCoreTurrets` 200 | 181-183 | Same as the mod API. |
| `bool GetBlockWeaponMap(IMyTerminalBlock, IDictionary<string,int>)` 212 | 184 | Same. B:632-635 |
| `MyTuple<bool,int,int> GetProjectilesLockedOn(long victim)` 227 | 185 | Unknown id gives (false, int.MinValue, int.MinValue). B:624-630 |
| `void GetSortedThreats(IMyTerminalBlock, IDictionary<MyDetectedEntityInfo,float>)` 239 | 186 | Converts with `GetDetailedEntityInfo` (no concealment). Does not clear the dictionary. B:593-605 |
| `void GetSortedThreatsByID(IMyTerminalBlock, IDictionary<long,MyDetectedEntityInfo>)` 251 | 187 | PB only. Keeps only entries whose info `EntityId` equals the target id, which drops out-of-range (empty) infos. B:607-622 |
| `void GetObstructions(IMyTerminalBlock, ICollection<MyDetectedEntityInfo>)` 262 | 188 | Clears the collection first. B:263-274 |
| `MyDetectedEntityInfo? GetAiFocus(long shooter, int priority = 0)` 277 | 189 | Unknown id gives an empty info. Uses `GetEntityInfo(..., conceal: true)`. quirk: `Relationship` is always `Enemies` (B:567). Empty beyond `ai.MaxTargetingRange` + target extents (B:552-558). B:442-448 |
| `bool SetAiFocus(IMyTerminalBlock, long target, int priority = 0)` 289 | 190 | Server-only backend. B:433-440 |
| `bool ReleaseAiFocus(IMyTerminalBlock, long playerId)` 301 | 191 | B:1035 |
| `MyDetectedEntityInfo? GetWeaponTarget(IMyTerminalBlock, int weaponId = 0)` 313 | 192 | `GetDetailedEntityInfo(..., conceal: true)`. Projectile target gives id -1 "Projectile" (type Missile); manual target gives id -2 "ManualTargeting". Empty beyond `Construct.MaxLockRange` + grid extents. B:423-431, B:486-541 |
| `void SetWeaponTarget(IMyTerminalBlock, long target, int weaponId = 0)` 322 | 193 | Unknown id is a no-op. B:414-421 |
| `FireWeaponOnce` 334, `ToggleWeaponFire` 347, `IsWeaponReadyToFire` 361, `GetMaxWeaponRange` 371, `GetTurretTargetTypes` 384, `SetTurretTargetTypes` 396, `SetBlockTrackingRange` 407 | 194-200 | Same as the mod API, quirks included. B:379-412 |
| `IsTargetAligned` 417, `CanShootTarget` 446, `IsTargetValid` 657 (target as `long`) | 201, 203, 225 | Unknown id gives false. B:352-368, B:652-660 |
| `IsTargetAlignedExtended` 433, `GetPredictedTargetPosition` 456 | 202, 204 | Use the `...Offset` backends, which pass the position through `PbRandomizePredictedPosition` (B:370-377, B:343-350, B:1323-1341, B:1385-1401). On a dedicated server, unless the root construct is not player-controlled, that adds a random offset of up to distance/200, re-rolled every 60 ticks (`EntityComp/Parts/Weapon/WeaponState.cs:473-497`). |
| `GetHeatLevel` 467, `GetWeaponHeatLevel` 478, `GetMaxWeaponHeatLevel` 489, `GetCurrentPower` 496, `GetMaxPower` 503 | 205-209 | Same. No `SetWeaponHeatLevel` for PBs. |
| `bool HasGridAi(long)` 510, `float GetOptimalDps(long)` 524, `float GetConstructEffectiveDps(long)` 618 | 210, 212, 221 | Unknown id gives false / `float.MinValue` / `float.MinValue` (B:276-322). The `GetOptimalDps` terminal-block quirk applies, so pass a grid id for grid DPS. |
| `bool HasCoreWeapon(IMyTerminalBlock)` 517 | 211 | Same. |
| `int GetAmmoCount(IMyTerminalBlock, int weaponId)` 541 | 213 | PB only. `ProtoWeaponAmmo.CurrentAmmo`, or -1. B:289-296 |
| `GetActiveAmmo` 532, `SetActiveAmmo` 552 | 214-215 | Same (set is server only). |
| `MonitorProjectileCallback(IMyTerminalBlock, int, Action<long,int,ulong,long,Vector3D,bool>)` 572 / `UnMonitorProjectileCallback` 592 | 219 / 218 | `PbMonitorProjectileCallback` writes `ProjectileMonitors[weaponId]` with no `?.` on the list. B:668-681 |
| `GetProjectileState(ulong)` 610 | 220 | Same. There is no PB `SetProjectileState`. |
| `GetPlayerController` 625, `GetWeaponAzimuthMatrix` 633, `GetWeaponElevationMatrix` 642, `GetWeaponScope` 672 | 222-224, 226 | Same. B:637-665 |
| `MyTuple<bool,bool> IsInRange(IMyTerminalBlock)` 690 | 227 | B:684-689 |
| `MonitorEvents` 731 / `UnMonitorEvents` 747 | 228-229 | B:900, B:908 |

- quirk: `PbApiMethods` also exposes `RegisterProjectileAdded` / `UnRegisterProjectileAdded` (`Api/ApiBackend.cs:216-217`). `WcPbApi` does not bind them, and the callback never fires anyway (see section 5).
- Concealment: with `conceal` true and a block target, the PB sees the grid's id and name and a 1 m box at the block's center (`Api/ApiBackend.cs:450-484`).

## 7. Callbacks and monitors

**Projectile monitor** `Action<long,int,ulong,long,Vector3D,bool>`, with a comment layout of (Block EntityId, PartId, ProjectileId, LastHitId, LastPos, Start) (`Api/ApiBackend.cs:1597`):
- Storage: one list per part, created in comp init (`EntityComp/EntityFields.cs:254-256`), cleared on comp removal (`Session/SessionCompMgr.cs:239`).
- Start: in `Projectile.Start()`, if the list is non-empty, the projectile is added to `MonitoredProjectiles` and each callback gets (CoreEntity.EntityId, PartId, Info.Id, Target.TargetId, Position, true), each in try/catch with a log line (`Projectiles/Projectile.cs:89`, `:355-370`).
- End: in `ProjectileInfo.Clean()` each callback gets (..., `ProHit.LastHit`, false), then the projectile leaves `MonitoredProjectiles` (`Projectiles/ProjectileTypes.cs:111-124`).
- quirk: the end call has no try/catch, so an exception propagates into WC.

**Event monitor** `Action<int,bool>`:
- Storage: one list per part (`EntityComp/EntityFields.cs:258-260`).
- Fired from `Weapon.EventTriggerStateChanged(state, active)` as `((int)state, active)` with try/catch (`EntityComp/Parts/Weapon/WeaponAv.cs:135`, `:174-190`).
- The int maps to `EventTriggers` (Reloading=0 ... TargetRanged25=20). The internal enum, `WcApi.EventTriggers` and `WcApiDef` all agree (`Definitions/CoreDefinitions.cs:397-419`, `Api/CoreSystemsApiBase.cs:470-493`, `Api/CoreSystemsApiDefs.cs:386-409`).

**Shoot handler** `Func<Vector3D scopePos, Vector3D scopeDir, int requestState, bool hasLos, object target, int currentAmmo, int remainingMags, int requestStage, bool>`:
- Fired in the same `EventTriggerStateChanged`, looked up by the weapon's `CoreEntity.EntityId`, then `TopEntity.EntityId` (`EntityComp/Parts/Weapon/WeaponAv.cs:163-164`).
- Args are `active ? 0 : 1` (EventStart/EventEnd), `hasLos` always `true`, target = `ShootRequest.RawTarget ?? Target.TargetObject`, and stage = `(int)EventTriggers` (`EntityComp/Parts/Weapon/WeaponAv.cs:166-167`).
- A false return, or StopFiring+active, clears a pending API shoot request (`EntityComp/Parts/Weapon/WeaponAv.cs:168-171`).
- quirk: the wrapper doc says `hasLos` is false when occluded (`Api/CoreSystemsApiBase.cs:445`), but the code always passes true.

**Target focus handler** `Func<MyEntity target, IMyCharacter, long handledId, int mode, bool>`:
- Consulted in `Focus.ServerChangeFocus` only when `!apiCalled && playerId != 0` (`Ai/AiConstruct.cs:978-984`). API `SetAiFocus` bypasses it.
- The first handler whose entity is in the requesting AI's construct decides. A **true return blocks** the change (`Ai/AiConstruct.cs:982-983`, `:1186-1198`).
- Mode is `ChangeMode` Add=0, Release=1, Lock=2 (`Ai/AiConstruct.cs:941-946`).
- quirk: the shipped wrapper callback returns `true` (`Api/CoreSystemsApiBase.cs:375`), which blocks every player focus change on the handled construct. The backend comment says the return "controls if the request is allowed to proceed" (`Api/ApiBackend.cs:843`), but the code treats true as restrict.

**HUD handler** `Func<IMyCharacter, long, int mode, bool>`:
- A true return restricts that HUD element (`Ui/Hud/HudSupport.cs:59-72`). Modes are `HudMode` Selector..PainterMarks (`Ui/Hud/HudFields.cs:101-109`).
- Used for reload, selector, target info, drone, painter and lead draws (`Ui/Hud/HudDraw.cs:85`, `Ui/Targeting/TargetUiDraw.cs:100`, `:399`, `Ui/Targeting/TargetUiSelect.cs:334-350`).
- The wrapper's sample also returns true (`Api/CoreSystemsApiBase.cs:405`), hiding everything.

**Damage handler** `Action<ListReader<MyTuple<ulong projectileId, long playerId, int partId, MyEntity weaponEntity, MyEntity topEntity, ListReader<MyTuple<Vector3D hitPos, object hitObject, float damage>>>>>`:
- Registration: keyed by `modId`. type 1 adds to `SystemWideDamageRegistrants` and sets `GlobalDamageHandlerActive`; type 0 removes (`Api/ApiBackend.cs:1942-1964`).
- quirk: re-registering an existing `modId` reuses the *old* registrant (`oldEventReq ?? new ...`), so the new callback is ignored (`Api/ApiBackend.cs:1955`). Unregister first to swap callbacks.
- Fill: in `ProcessHits`, when `GlobalDamageHandlerActive && info.ObjectsHit > 0`, one entry per projectile (`Session/SessionDamageMgr.cs:128-129`). Hit objects can be a shield entity, `IMySlimBlock`, an entity or a projectile id (`ulong`) (`Session/SessionDamageMgr.cs:330-331`, `:970-971`, `:1136-1137`, `:1222-1223`).
- quirk (as read): each hit assigns a fresh or pooled list to `info.ProHits` before adding (`Session/SessionDamageMgr.cs:970`, `:1136`). That looks like it keeps only the last hit per projectile in `ObjectsHit`. Not tested.
- Dispatch: `Projectiles.Damage()` clears `ProjectileDamageEvents`, runs `ProcessHits`, then invokes every system-wide callback once with the batch (`Projectiles/Projectiles.cs:81`, `:92-99`, `Session/SessionJobs.cs:330-336`). Called from `Session.Simulate` (`Session/SessionRun.cs:159`, `:218`).
- The data is valid until the next batch. The wrapper's `DamageHandlerHelper` copies it into structs and clears them after your function returns (`Api/CoreSystemsApiBase.cs:815-819`, `:830-863`).

**Scan, validate, subsystem and trajectory callbacks:** see the targeting table (`Ai/AiDatabase.cs:44-47`, `Ai/AiTargeting.cs:252-254`, `EntityComp/Parts/Weapon/WeaponTracking.cs:1121-1155`, `:1654-1671`).

## 8. How MES uses the API

Copy and load:
- MES ships its own older copy in namespace `ModularEncountersSystems.API` (`MES:Data/Scripts/ModularEncountersSystems/API/CoreSystemsApiBase.cs:11-15`, 698 lines against WC's 896).
- Its 73 `AssignMethod` keys are a strict subset of the current wrapper's keys. It lacks the scan/validate, heat get/set, `EnableRequiredPowerBase`, `GetAllSmartProjectiles`, `GetMuzzleParentEntityBase`, trajectory and subsystem keys, so it loads against this WC without the missing-key exception.
- Same channel and handshake (`MES:Data/Scripts/ModularEncountersSystems/API/CoreSystemsApiBase.cs:448`, `:469-505`).

When it loads:
- Detection: workshop ids 1918681825, 2189703321, 3154371364, 3149625043, 3191232165, or a local `Mods\CoreSystems` path (`MES:Data/Scripts/ModularEncountersSystems/API/AddonManager.cs:81-85`, `:231-234`).
- `APIs.WeaponCore.Load(AddonManager.WeaponCoreCallback, true)` runs only when `phase == 2 && MES_SessionCore.IsServer` (`MES:Data/Scripts/ModularEncountersSystems/API/APIs.cs:14`, `:66-68`), and phase 2 is `BeforeStart` (`MES:Data/Scripts/ModularEncountersSystems/Core/MES_SessionCore.cs:114`, `:135`). MES clients never load the WC API.
- `WeaponCoreCallback` returns unless `IsReady`, then sets `APIs.WeaponCoreApiLoaded` and fills `BlockManager.AllWeaponCoreBlocks`/`Turrets`/`Guns` from `GetAllCoreWeapons`/`GetAllCoreTurrets`/`GetAllCoreStaticLaunchers` (`MES:Data/Scripts/ModularEncountersSystems/API/AddonManager.cs:319-328`).
- If the turret or gun list is empty, it classifies blocks with `WeaponDefinitions` (`HardPoint.Ai.TurretAttached`, first mount point subtype) (`MES:Data/Scripts/ModularEncountersSystems/API/AddonManager.cs:330-359`).
- MES never calls `WeaponCore.Unload()` (no match in the repo for `WeaponCore.Unload`).

Per NPC grid (`WeaponSystem.Setup`, `MES:Data/Scripts/ModularEncountersSystems/Behavior/Subsystems/Weapons/WeaponSystem.cs:155`):
- For each WC block: `GetBlockWeaponMap(block, dict)`, then one `CoreWeapon` per PartName, matched to `WeaponDefinitions` by `HardPoint.PartName`, with the WC weaponId from the map (`MES:Data/Scripts/ModularEncountersSystems/Behavior/Subsystems/Weapons/WeaponSystem.cs:181-202`).
- After the part loop it calls `DisableRequiredPower(block)` for every WC block (`MES:Data/Scripts/ModularEncountersSystems/Behavior/Subsystems/Weapons/WeaponSystem.cs:229`). NPC WC weapons therefore run with `ModOverride` set.
- Gotcha (MES): when no definition matches the PartName, `weaponDef` stays `new WeaponDefinition()`. `CoreWeapon` then reads `_weaponDefinition.Ammos.Length` (`MES:Data/Scripts/ModularEncountersSystems/Behavior/Subsystems/Weapons/CoreWeapon.cs:56`) on a class whose arrays are null (`Api/CoreSystemsApiDefs.cs:233`), so expect a NullReferenceException. Not tested.

`CoreWeapon` calls (`MES:Data/Scripts/ModularEncountersSystems/Behavior/Subsystems/Weapons/CoreWeapon.cs`):
- `GetActiveAmmo(block, weaponId)` to pick the ammo definition. A null result (platform not Ready) falls back to `Ammos[0]` (`:263-299`).
- `GetWeaponTarget(block, weaponId).Item4` for the current target (`:316`).
- Static guns only: `FireWeaponOnce(block, false, weaponId)` (`:366`) and `ToggleWeaponFire(block, on, false, weaponId)` (`:443`, `:453`).
- Gotcha: WC ignores `allWeapons`/`weaponId` and fires or stops the whole block (`Api/ApiBackend.cs:1142-1159`). On a multi-weapon block, one `CoreWeapon` turning off also stops its siblings.
- `SetWeaponTarget(block, target, weaponId)` (`:397`, `:407`). The `SetAiFocus` calls in this file are commented out (`:398`, `:408`, `:423-435`).

`WeaponSystem` calls:
- `FireWeapons()`: when the autopilot has a target and `GetAiFocus(grid)` is null, at most every 2 s it calls `SetAiFocus(grid, target.GetParentEntity())` and re-checks, inside try/catch (`MES:Data/Scripts/ModularEncountersSystems/Behavior/Subsystems/Weapons/WeaponSystem.cs:624-658`). Works because MES runs server-side and `SetAiFocus` is server only (`Api/ApiBackend.cs:1025`).
- `GetProjectilesLockedOn(remoteControl).Item1` sets `IncomingHomingProjectiles` when `UseAntiSmartWeapons` is on (`MES:Data/Scripts/ModularEncountersSystems/Behavior/Subsystems/Weapons/WeaponSystem.cs:428-434`).

Spawn manipulation:
- `SetWeaponCoreRandomRanges` (via `GridEntity.SetAutomatedWeaponRanges`), per WC block: `GetMaxWeaponRange(block, 0)` cached per definition in `DefaultRangeWC`, then `DisableRequiredPower`, then `SetBlockTrackingRange(block, min(max, 800))` unless `useMax` (`MES:Data/Scripts/ModularEncountersSystems/Spawning/Manipulation/WeaponRandomizer.cs:1289-1335`, `MES:Data/Scripts/ModularEncountersSystems/Entities/GridEntity.cs:1727-1729`).
- Gotcha: `GetMaxWeaponRange` returns 0 while the platform is not Ready (`Api/ApiBackend.cs:1180-1183`), and MES caches that value per definition id (`MES:Data/Scripts/ModularEncountersSystems/Spawning/Manipulation/WeaponRandomizer.cs:1319-1322`). Whether this happens depends on timing that was not traced.

Ammo replenishment:
- `WeaponCoreReplenishment` calls `DisableRequiredPower`. `GetCompatibleWeaponCoreAmmos` uses `GetBlockWeaponMap` plus `WeaponDefinitions` (`MES:Data/Scripts/ModularEncountersSystems/Helpers/InventoryHelper.cs:288-292`, `:392-412`).

MES never uses: damage handlers, projectile/event monitors, `ShootRequest`, phantoms, `SetActiveAmmo`, or the PB API.

## 9. Not confirmed

- Whether `MyAPIGateway.Utilities.SendModMessage` runs handlers synchronously, i.e. whether `readyCallback` fires inside `Load()` when WC is already loaded. That is game code, not checked here.
- Session component order between WC (`MySessionComponentDescriptor(..., int.MaxValue - 1)`, `Session/SessionRun.cs:18`) and a given mod. Both orders are handled by the broadcast plus request.
- Whether `ProcessHits` and the damage callbacks run on MP clients as well as the server. `ProcessHits` has server-specific branches (`Session/SessionDamageMgr.cs:44`), but no client gate was found around the dispatch.
- Whether event monitors and shoot handlers fire on clients, the server or both. `EventTriggerStateChanged` was not traced to its callers.
- Byte-for-byte protobuf compatibility of `WcApiDef.WeaponDefinition` with WC's internal definition. Enums `EventTriggers` and `Threat` match; the full member layout was not diffed.
- The `ProHits` "last hit only" reading in the damage path (section 7). Taken from code reading only.
- The `ForceReload` NRE on block weapons. Inferred from `Rifle` only being assigned in the rifle branch, not run.
- The phantom `maxAge` cap of 14400 ticks claimed in the wrapper doc (`Api/CoreSystemsApiPhantoms.cs:76`). The cap was not found in `CreatePhantomEntity`'s first 50 lines.
- What `SubTypeIdToWeaponMagMap` uses as its key (block id or weapon id). The key type is `MyDefinitionId`, but how it is filled was not traced.
- The MES `DefaultRangeWC` zero-caching risk depends on when `SetAutomatedWeaponRanges` runs relative to WC platform init. Not traced.
