# WeaponCore config, controls, commands, vanilla handling, integrations, logs

Source: WeaponCore commit 25985a9 (2026-11-05). Paths are relative to Data/Scripts/CoreSystems/.

Citations are `file:line`. "quirk" marks code that behaves differently from what its name or text suggests.

## 1. Server / world config

### File and load flow

- File name `CoreSystemsServer.cfg` (`Session/SessionFields.cs:56`), XML, written with `WriteFileInWorldStorage(name, typeof(ServerSettings))`, so it lives in the world's mod storage, not local storage (`Support/VersionControl.cs:125-131`).
- Expected version: `ModVersion = 29` (`Session/SessionFields.cs:54`). Server only: the file is read only when `IsServer` (`Support/VersionControl.cs:48-77`).
- Settings object is created once in `BeforeStartInit` (`Session/SessionInit.cs:69`), via `CoreSettings` ctor -> `VersionControl.InitSettings()` (`Definitions/SerializedConfigs/CoreSettings.cs:17-25`).
- File present, `Version == 29`: used as is, then `CorruptionCheck(true)` fixes bad values and rewrites the file every load (`Support/VersionControl.cs:63-67`, `Support/VersionControl.cs:194-249`).
- File present, other version: `RebuildConfig` copies some old values into a fresh object and saves (`Support/VersionControl.cs:95-105`, `Support/VersionControl.cs:140-192`).
- File missing or XML that fails to parse: fresh defaults written over it (`Support/VersionControl.cs:58-71`, `Support/VersionControl.cs:99-100`). quirk: a typo in the XML silently resets the whole file.
- quirk: `RebuildConfig` keeps only BlockModifers, ShipSizes, DefinitionOverrides, ServerSleepSupport, Base/AdvancedOptimizations, Min/MaxHudFocusDistance, DisableAi, DisableLeads, DisableHudReload, DisableHudTargetInfo, UnsupportedMode, DisableSmallVsLargeBuff; it resets Large/SmallGridDamageMultiplier to 1 and drops Direct/Area/ShieldDamageModifer, DisableTargetCycle, ProhibitHUDPainter, ProhibitShooting, DisableVanillaConversion (`Support/VersionControl.cs:142-191`).
- quirk: legacy `ServerModifiers` are remapped into DefinitionOverrides, then overwritten if the old file also had `DefinitionOverrides` (`Support/VersionControl.cs:161-174`).
- `CorruptionCheck` sets negative global damage modifiers/multipliers back to 1, and inserts sample entries (`TestSubId1`, `AmmoRound1`, `PartName1`, `Subtype1`...) when `BlockModifers` or `DefinitionOverrides` is null (`Support/VersionControl.cs:196-245`). The samples never match real defs unless names collide.

### Top-level settings (`ServerSettings`)

| Setting | Type | Default | Effect |
|---|---|---|---|
| Version | int | -1 (written as 29) | version gate `Definitions/SerializedConfigs/CoreSettings.cs:198`, `Support/VersionControl.cs:63` |
| Debug | int | -1 | no reader found (unused) `Definitions/SerializedConfigs/CoreSettings.cs:199` |
| AdvancedOptimizations | bool | true | no reader outside VersionControl (unused) `Definitions/SerializedConfigs/CoreSettings.cs:200` |
| DirectDamageModifer | float | 1 | global multiplier on direct damage to shields and blocks `Session/SessionDamageMgr.cs:186`, `Session/SessionDamageMgr.cs:675` |
| AreaDamageModifer | float | 1 | global multiplier on area damage `Session/SessionDamageMgr.cs:187`, `Session/SessionDamageMgr.cs:676` |
| ShieldDamageModifer | float | 1 | read in the Defense Shields hit path `Session/SessionDamageMgr.cs:188` |
| BaseOptimizations | bool | true | projectile hit checks go parallel above 96 live projectiles (else 99999) `Projectiles/Projectiles.cs:359-361` |
| ServerSleepSupport | bool | false | WC comps sleep when nothing in range, no tracking, no controlling player, terminal not open, trigger off `EntityComp/Parts/Weapon/WeaponComp.cs:509`, `EntityComp/Parts/Control/ControlComp.cs:70` |
| DisableAi | bool | false | `AcquireTargets` false for every AI (no auto targeting) `Ai/AiFields.cs:253` |
| DisableLeads | bool | false | skips HUD target-lead groups `Session/SessionLocalPlayer.cs:113` |
| MinHudFocusDistance | double | 0 | initial `MaxTargetingRange` of a new AI `Ai/AiFields.cs:265` |
| MaxHudFocusDistance | double | 10000 | cap on AI `MaxTargetingRange` (HUD/target selection reach) `Ai/AiSupport.cs:216-221`, `EntityComp/EntitySupport.cs:177` |
| BlockModifers | BlockModifer[] | {} | per block SubtypeId Direct/Area multipliers (legacy tag, still applied) `Support/VersionControl.cs:252-268`, `Session/SessionDamageMgr.cs:768-780` |
| ShipSizes | ShipSize[] | {} | legacy; no reader outside VersionControl `Definitions/SerializedConfigs/CoreSettings.cs:211` |
| ServerModifiers | Modifiers | null | legacy string-based mods, converted on rebuild `Support/VersionControl.cs:370-584` |
| DisableTargetCycle | bool | false | blocks wheel / PageUp/PageDown target cycling `Ui/Targeting/TargetUiSelect.cs:83-87` |
| DisableHudTargetInfo | bool | false | hides target info HUD `Ui/Targeting/TargetUiDraw.cs:399` |
| DisableHudReload | bool | false | hides reload/weapon HUD panel `Session/SessionRun.cs:306`, `Session/SessionUpdate.cs:644` |
| UnsupportedMode | bool | false | keep non-WC weapon blocks instead of deleting them (see section 5) `Session/SessionSupport.cs:909-927` |
| DisableSmallVsLargeBuff | bool | false | when false, LG shooter vs SG target gets 0.25 factor if ammo Grids Large and Small are both < 0 `Session/SessionDamageMgr.cs:494-495` |
| DefinitionOverrides | Overrides | samples | ammo/weapon/armor overrides (tables below) `Definitions/SerializedConfigs/CoreSettings.cs:219` |
| LargeGridDamageMultiplier | float | 1 | damage factor vs large grid targets `Session/SessionDamageMgr.cs:492` |
| SmallGridDamageMultiplier | float | 1 | damage factor vs small grid targets `Session/SessionDamageMgr.cs:492` |
| ProhibitHUDPainter | bool | false | removes Painter control mode from lists, actions, data checks, painter updates `EntityComp/Controls/TerminalHelpers.cs:279`, `Session/SessionControls.cs:381`, `EntityComp/Parts/Weapon/WeaponData.cs:152-158`, `Session/SessionRun.cs:271` |
| ProhibitShooting | bool | false | skips `ShootWeapons()` for everyone; info panel line `Session/SessionRun.cs:195-200`, `EntityComp/EntityEvents.cs:227-230` |
| DisableVanillaConversion | bool | false | no reader found (unused); conversion is gated by a mod check instead (section 5) `Definitions/SerializedConfigs/CoreSettings.cs:224` |

### `DefinitionOverrides.AmmoOverrides` (match `AmmoName` == ammo `AmmoRound`)

Matching: first entry with a given name wins, later duplicates are logged as SHADOWED in `overrides.log` (`Support/VersionControl.cs:294-332`). All fields are nullable; only set fields apply.

| Field | Type | Applied at |
|---|---|---|
| BaseDamage | float | min 0.000001 `Definitions/SerializedConfigs/AmmoConstants.cs:1548` |
| AreaEffectDamage, AreaEffectRadius | float, double | `Definitions/SerializedConfigs/AmmoConstants.cs:1203-1211` |
| DetonationDamage, DetonationRadius | float | `Definitions/SerializedConfigs/AmmoConstants.cs:1213-1221` |
| ByBlockHitMaxAbsorb, EndOfLifeMaxAbsorb | float | `Definitions/SerializedConfigs/AmmoConstants.cs:1223-1230` |
| Health | float | min 0 `Definitions/SerializedConfigs/AmmoConstants.cs:1549` |
| MaxTrajectory | float | min 0 `Definitions/SerializedConfigs/AmmoConstants.cs:1551-1555` |
| DesiredSpeed | float | `Definitions/SerializedConfigs/AmmoConstants.cs:532` |
| EnergyCost | float | `Definitions/SerializedConfigs/AmmoConstants.cs:1383` |
| GravityMultiplier | float | `Definitions/SerializedConfigs/AmmoConstants.cs:1550` |
| ShieldModifier | double | <0 becomes 1 `Definitions/SerializedConfigs/AmmoConstants.cs:1561` |
| EnergyBaseDamage / EnergyAreaEffectDamage / EnergyDetonationDamage / EnergyShieldDamage | bool | damage type kinetic vs energy `Definitions/SerializedConfigs/AmmoConstants.cs:1557-1560` |
| DisableClientPredictedAmmo | bool | `Definitions/SerializedConfigs/AmmoConstants.cs:577` |
| FallOffDistance, FallOffMinMultipler | float | `Definitions/SerializedConfigs/AmmoConstants.cs:1563-1564` |
| ShieldBypass | float | `Definitions/SerializedConfigs/AmmoConstants.cs:1566` |
| Mass | float | `Definitions/SerializedConfigs/AmmoConstants.cs:1565` |
| HealthHitModifier | double | `Definitions/SerializedConfigs/AmmoConstants.cs:1362` |
| BackKickForce | float | `Definitions/SerializedConfigs/AmmoConstants.cs:518` |
| GridSizeLarge, GridSizeSmall, Armor, ArmorLight, ArmorHeavy, ArmorNonArmor | float | `Definitions/SerializedConfigs/AmmoConstants.cs:1293-1307`; any of these forces `NoGridOrArmorScaling` false `Definitions/SerializedConfigs/AmmoConstants.cs:1536-1544` |

### `DefinitionOverrides.WeaponOverrides` (match `PartName` == `HardPoint.PartName`)

Matched by PartName only, so one entry hits every definition sharing that PartName (`Support/VersionControl.cs:275-290`). Applied in `WeaponConstants` (`Definitions/CoreSystems.cs:878-892`).

| Field | Type | Applied | Notes |
|---|---|---|---|
| MaxTargetDistance | float | `Definitions/CoreSystems.cs:884` | <=0 means unlimited |
| MinTargetDistance | float | `Definitions/CoreSystems.cs:885` | min 0 |
| RateOfFire | int | `Definitions/CoreSystems.cs:886` | |
| ReloadTime | int | `Definitions/CoreSystems.cs:887` | ticks |
| DeviateShotAngle | float | `Definitions/CoreSystems.cs:888` | degrees |
| AimingTolerance | double | `Definitions/CoreSystems.cs:889` | <=0 means 180 |
| HeatPerShot | int | `Definitions/CoreSystems.cs:890` | |
| HeatSinkRate | float | `Definitions/CoreSystems.cs:891` | |
| IdlePower | float | `Definitions/CoreSystems.cs:892` | min 0.001 |
| InventorySize, MaxHeat, Cooldown, ConstructPartCap, RestrictionRadius, CheckInflatedBox, CheckForAnyWeapon, MuzzleCheck | various | none | quirk: serialized but no reader found `Definitions/SerializedConfigs/CoreSettings.cs:163-182` |

### `DefinitionOverrides.ArmorOverrides`

`SubtypeIds[]`, `KineticResistance`, `EnergeticResistance`; applied only when ArmorCore is active and the subtype is in the armor map (`Session/SessionSupport.cs:1817-1836`).

### Sync to clients, and what reloads when

- Server applies overrides in `BeforeStartInit` via `UpdateEnforcement()` (`Session/SessionInit.cs:74-75`, `Session/SessionSupport.cs:1784-1815`); blocks with overrides show two "server modded" lines in custom info (`EntityComp/EntityEvents.cs:237-239`).
- On player connect (MP server) the whole `ServerSettings` is sent in a `ServerData` packet (`Session/SessionEvents.cs:619-623`, `Session/SessionNetworkSupport.cs:740-759`).
- Client handler replaces its `Enforcement`, rebuilds maps, reruns `UpdateEnforcement()` (`Session/SessionNetworkCMethods.cs:466-479`, `Support/VersionControl.cs:86-93`). Client comps do not start until `Enforcement` arrives (`Session/SessionCompMgr.cs:87-88`).
- No reload command exists; edit the file and reload the world. `/wc ts` and `/wc debugserver` change memory only (section 3).

## 2. Client config

- File `CoreSystemsClient.cfg` (`Session/SessionFields.cs:57`) in global storage (`ReadFileInGlobalStorage`/`WriteFileInGlobalStorage`) (`Support/VersionControl.cs:25-46`, `Support/VersionControl.cs:117-123`). Read on every machine, DS included (no guard in `InitSettings`).
- Version must equal `ClientCfgVersion = 9` or the file is replaced with defaults (`Session/SessionFields.cs:55`, `Support/VersionControl.cs:32-46`).
- quirk: key names are looked up with a dictionary indexer, so an invalid key name in the file throws (`Support/VersionControl.cs:36-41`).
- A new/regenerated config shows a one-time `/wc` tip at tick 1200 (`Support/VersionControl.cs:79-83`, `Session/SessionSupport.cs:105-108`).

| Setting | Type | Default | Effect |
|---|---|---|---|
| ClientOptimizations | bool | true | enables adaptive AV scaling `Session/SessionSupport.cs:337` |
| AvLimit | int | 0 | floor for AV reduction level, 0-20 via `/wc avlimit` `Session/SessionSupport.cs:366`, `Session/SessionSupport.cs:741-756` |
| MenuButton | string | Middle | menu mouse button `Definitions/SerializedConfigs/CoreSettings.cs:234` |
| ControlKey | string | R | see keybinds `Definitions/SerializedConfigs/CoreSettings.cs:235` |
| ShowHudTargetSizes | bool | false | retired `Definitions/SerializedConfigs/CoreSettings.cs:236` |
| ActionKey | string | NumPad0 | `Definitions/SerializedConfigs/CoreSettings.cs:237` |
| HudPos | Vector2 | (0,0) | HUD offset, moved with arrows `Ui/Targeting/SupportClasses.cs:47`, `Ui/UiInput.cs:252-271` |
| HudScale | float | 1 | HUD scale, +/- keys, clamp 0.1-10 `Ui/Hud/HudSupport.cs:22-23`, `Ui/UiInput.cs:277-288` |
| InfoKey | string | Decimal | `Definitions/SerializedConfigs/CoreSettings.cs:240` |
| MinimalHud | bool | false | minimal target HUD `Ui/Targeting/TargetUiDraw.cs:384` |
| StikcyPainter | bool | true | when false, a painted point on a missing block is cleared after 3 ray misses `Session/SessionJobs.cs:283-297` |
| CycleNextKey / CyclePrevKey | string | PageDown / PageUp | target cycling `Ui/UiInput.cs:345-357` |
| AdvancedMode | bool | false | shows advanced terminal controls/actions and detailed HUD `Session/SessionControls.cs:319-326`, `Session/SessionControls.cs:345-351` |
| HideReload | bool | false | hides right info (reload) panel `Session/SessionUpdate.cs:644` |

### Keybinds (only active while controlling a grid with WC AI, unless noted)

| Input | Default | Action |
|---|---|---|
| Control key + Ctrl, aiming at a WC block (not in an AI block) | R | generate problem report to `report.log` `Ui/UiInput.cs:223-229`, `Session/SessionRun.cs:101-102` |
| Action key (hold) | NumPad0 | with `/wc changehud` on: arrows move HUD, numpad +/- scale it `Ui/UiInput.cs:246-290` |
| Info key | Decimal (also Delete) | cycles Full HUD -> Minimal -> Minimal+panel off `Ui/UiInput.cs:239-315` |
| Right mouse | - | select target `Ui/Targeting/TargetUiSelect.cs:81-82` |
| Wheel / Cycle keys | PageDown/PageUp | cycle targets unless `DisableTargetCycle` `Ui/Targeting/TargetUiSelect.cs:83-87` |
| Alt + Shift release | - | release focus target `Ui/Targeting/TargetUiSelect.cs:79-80` |
| Ctrl release (3rd person) | - | cycle reticle mode None/Dot/Crosshair `Ui/Targeting/TargetUiSelect.cs:22-35` |
| Menu mouse (hand weapon) | Middle | select/paint; hold 90 ticks with smart iron sights toggles Painter/Auto `Ui/Targeting/TargetUiSelect.cs:56-71`, `Ui/UiInput.cs:146-149`, `Ui/UiInput.cs:445-451` |
| Game RELOAD (hand weapon) | game bind | tap = force reload, hold 60 ticks = cycle ammo `Ui/UiInput.cs:128-139` |
| Gamepad J05+J06 with J10/J09 | - | cycle next/prev `Ui/UiInput.cs:359-374` |

- quirk: menu "new press/release" use the hardcoded middle button, so a remapped menu button only feeds `ClientInputState` (`Ui/UiInput.cs:116-118`, `Ui/UiInput.cs:157`).
- quirk: key blacklisting while the action/info key is held hardcodes NumPad0 and Decimal, not the remapped keys (`Ui/UiInput.cs:391-443`).

### HUD options summary

Server: `DisableHudTargetInfo`, `DisableHudReload`, `DisableLeads`, `MaxHudFocusDistance`. Client: `MinimalHud`, `HideReload`, `HudPos`, `HudScale`, `AdvancedMode`. The WC HUD is skipped entirely when the game's own minimal HUD is on (`Session/SessionRun.cs:304`). Mods can restrict HUD via HudHandlers (`Ui/Targeting/TargetUiDraw.cs:399`).

## 3. Chat commands and debug

Handler `ChatMessageSet`, registered only where `HandlesInput` (clients, SP, listen host; not DS) (`Session/SessionInit.cs:28`, `Session/SessionInit.cs:55-56`). Any `/wc` message is not sent to others (`Session/SessionSupport.cs:883`).

| Command | Who | Effect |
|---|---|---|
| `/wc` | anyone | help text (only when message length <= 3) `Session/SessionSupport.cs:878-879` |
| `/wc remap keyboard\|mouse\|action\|info\|next\|prev` | anyone | next key/button pressed becomes the bind, saved to client cfg `Session/SessionSupport.cs:699-728`, `Session/SessionSupport.cs:577-677`. Left/Right mouse rejected `Session/SessionSupport.cs:632` |
| `/wc remap ...` other | anyone | remap help `Session/SessionSupport.cs:880-881` |
| `/wc avlimit N` | anyone | AvLimit = clamp(N,0,20); ClientOptimizations = N>0 `Session/SessionSupport.cs:741-756` |
| `/wc stickypainter` | anyone | toggle StikcyPainter `Session/SessionSupport.cs:757-762` |
| `/wc changehud` | anyone | toggle HUD edit mode (not saved) `Session/SessionSupport.cs:763-767` |
| `/wc advanced` | anyone | toggle AdvancedMode `Session/SessionSupport.cs:768-773` |
| `/wc setdefaults` | anyone | new `ClientSettings()`, saved `Session/SessionSupport.cs:774-779` |
| `/wc debug` | anyone | toggle local `DebugMod` `Session/SessionSupport.cs:780-784` |
| `/wc debugserver` | MP admin (checked client and server) | toggle DebugMod, broadcast to all `Session/SessionSupport.cs:785-813`, `Session/SessionNetwork.cs:497-523`, `Session/SessionNetwork.cs:269-276` |
| `/wc unsupportedmode` | anyone with input, no admin check | toggle UnsupportedMode and `SaveServerCfg()` locally `Session/SessionSupport.cs:814-829` |
| `/wc toggleshooting`, `/wc ts` | MP admin; anyone in SP | toggle ProhibitShooting, broadcast `Session/SessionSupport.cs:830-865`, `Session/SessionNetwork.cs:471-496` |
| `/wc checkshooting`, `/wc cs` | anyone | show shooting state `Session/SessionSupport.cs:866-870` |

- Quirks: `ts` is never saved to the cfg (no `SaveServerCfg` call in either path); `setdefaults` writes `Version = -1`, so the next load regenerates the file, and live keybinds are not reset; help text says `setdefaults` "Resets shield client configs" (`Session/SessionSupport.cs:879`); `unsupportedmode` on an MP client changes only that client's copy and its local world storage.
- Remap matches the whole message exactly (`switch (message)`), other subcommands use the second token (`Session/SessionSupport.cs:696-740`).

Debug options:
- `DebugMod` forced on when the mod id is `CoreSystems` or `WeaponCore` (local unpacked copy) (`Session/SessionSupport.cs:1170-1176`); it enables visual debug drawing (`Session/SessionRun.cs:285-286`) and turns off log flood suppression (`Support/Log.cs:62`).
- Per-block `WC_Debug` switch stores `Overrides.Debug`, adds detail to custom info (`EntityComp/Controls/TerminalHelpers.cs:150`, `EntityComp/EntityEvents.cs:224-225`).
- Compile-time flags: `DebugLog.ForceDebug = false` (`Support/DebugLog.cs:10`), `DebugSupport.DebugWeaponSync = false` (`Support/DebugSupport.cs:16`).

## 4. Terminal controls and toolbar actions

### Where they are added

- Block types: conveyor sorter, `IMyLargeTurretBase`, searchlight, small missile launcher (+reload), small gatling gun, turret control block (CTC), offensive combat block, decoy, camera (`Session/SessionControls.cs:43-91`).
- Weapon blocks: `CreateGenericControls`, `AddUiControls`, then actions, then `AddTurretOrTrackingControls` (`Session/SessionControls.cs:154-168`). CTC and searchlight get their own sets (`Session/SessionControls.cs:141-152`).
- Control ids: checkbox/switch/combobox/listbox/button get `"WC_" + name` (`EntityComp/Controls/TerminalHelpers.cs:1056`, `EntityComp/Controls/TerminalHelpers.cs:1132`, `EntityComp/Controls/TerminalHelpers.cs:1218`); sliders use the bare name (`EntityComp/Controls/TerminalHelpers.cs:758`, `EntityComp/Controls/TerminalHelpers.cs:940`).
- Vanilla controls on WC blocks: hidden unless whitelisted (`Session/SessionControls.cs:518-575`, `Session/SessionControls.cs:661-666`); vanilla `Control` only for turrets/CTC (`EntityComp/Controls/TerminalHelpers.cs:650-654`); vanilla `Range` and `UseConveyor` removed (`Session/SessionControls.cs:353-360`). Vanilla actions disabled except Shoot*, OnOff, WC_*, Control; `Shoot`, `Shoot_On`, `Shoot_Off` rewired to WC shoot sync (`Session/SessionControls.cs:394-516`).
- Without AdvancedMode these are hidden: controls in `AdvancedControls`, actions in `AdvancedActions` (`Session/SessionControls.cs:577-630`).
- Most visibility helpers also require the local player to own the block state or take ownership (`EntityComp/Controls/TerminalHelpers.cs:253`).

### Weapon block controls

Definition-derived comp flags are set in `SetupWeaponUi` (`EntityComp/PlatformInit.cs:705-739`); threat flags come from `Targeting.Threats` (`Definitions/CoreSystems.cs:591-630`).

| Id | Kind | Visible when (def source) |
|---|---|---|
| WC_Advanced | checkbox | not AlternateUi; toggles client AdvancedMode `EntityComp/Controls/TerminalHelpers.cs:149`, `EntityComp/Controls/Weapon/WeaponUi.cs:312-321` |
| WC_Debug | switch | guided ammo and no turret `EntityComp/Controls/TerminalHelpers.cs:150` |
| WC_ShareFireControlEnabled | switch | `Ai.TrackTargets` or guided ammo `EntityComp/Controls/TerminalHelpers.cs:153` |
| WC_Shoot | switch | not bomb, not AlternateUi `EntityComp/Controls/TerminalHelpers.cs:155` |
| WC_Override | switch | some ammo RequiresTarget `EntityComp/Controls/TerminalHelpers.cs:156`, `EntityComp/Controls/TerminalHelpers.cs:524-533` |
| WC_Shoot Mode | combo AiShoot/MouseControl/KeyToggle/KeyFire | not bomb `EntityComp/Controls/TerminalHelpers.cs:19`, `EntityComp/Controls/Weapon/WeaponUi.cs:621-627` |
| Weapon ROF | slider min..1 | `Ui.RateOfFire` `EntityComp/Controls/TerminalHelpers.cs:20`, `EntityComp/Controls/Weapon/WeaponUi.cs:207-229` |
| WC_Overload | checkbox (Overload 1/2) | `Ui.EnableOverload` `EntityComp/Controls/TerminalHelpers.cs:21`, `EntityComp/Controls/Weapon/WeaponUi.cs:145-156` |
| Detonation, WC_StartCount, WC_StopCount, WC_Arm, WC_Trigger | slider 0-3600 / buttons / checkbox | `CriticalReaction.Enable && TerminalControls` `EntityComp/Controls/TerminalHelpers.cs:22-26`, `EntityComp/PlatformInit.cs:720` |
| WC_ControlModes | combo Auto/Manual/Painter | turret or guided ammo, and >1 valid mode after ProhibitHUDPainter `EntityComp/Controls/TerminalHelpers.cs:32`, `EntityComp/Controls/TerminalHelpers.cs:270-286` |
| WC_ObjectiveMode | combo Default/Disabled/Destroyed | TrackGrids `EntityComp/Controls/TerminalHelpers.cs:33` |
| WC_TrackingMode | combo Any/Moving/Mobile/Moored/ShipAny | TrackGrids `EntityComp/Controls/TerminalHelpers.cs:34` |
| WC_PickAmmo | combo | >1 ammo with `HardPointUsable` and not shrapnel `EntityComp/Controls/TerminalHelpers.cs:35`, `Definitions/SerializedConfigs/AmmoConstants.cs:445`, `Definitions/CoreSystems.cs:453` |
| WC_ForceReload | button | pending ammo change `EntityComp/Controls/TerminalHelpers.cs:36`, `EntityComp/Controls/TerminalHelpers.cs:288-304` |
| Weapon Range | slider min(MinTargetDistance)..max weapon range | turret only `EntityComp/Controls/TerminalHelpers.cs:37`, `EntityComp/Controls/Weapon/WeaponUi.cs:244-286` |
| WC_SubSystems, WC_PickSubSystem | switch, combo 8 types | TrackGrids and not `Other.ProhibitSubsystemChanges` `EntityComp/Controls/TerminalHelpers.cs:41-42`, `EntityComp/Controls/TerminalHelpers.cs:222-227` |
| WC_FocusFire | switch | TrackGrids, not a slaved radio `EntityComp/Controls/TerminalHelpers.cs:44`, `EntityComp/Controls/TerminalHelpers.cs:465-475` |
| WC_Repel | switch | TrackGrids `EntityComp/Controls/TerminalHelpers.cs:45` |
| WC_Neutrals, WC_Unowned | switch | tracking or guidance `EntityComp/Controls/TerminalHelpers.cs:47-48` |
| WC_Grids | switch | Threat Grids `EntityComp/Controls/TerminalHelpers.cs:49` |
| WC_LargeGrid, WC_SmallGrid | switch | Grids and neither `Other.ProhibitLGTargeting` nor `ProhibitSGTargeting` `EntityComp/Controls/TerminalHelpers.cs:50-51`, `EntityComp/Controls/TerminalHelpers.cs:453-463` |
| WC_Biologicals / WC_Projectiles / WC_Meteors | switch | Threat Characters / Projectiles / Meteors `EntityComp/Controls/TerminalHelpers.cs:52-55` |
| WC_Supporting PD | switch | Projectiles and not `Ui.DisableSupportingPD` `EntityComp/Controls/TerminalHelpers.cs:54`, `EntityComp/Controls/TerminalHelpers.cs:234-239` |
| Burst Count | slider 1..MaxAmmoCount | not `Ui.ProhibitBurstCount`, not multipart, magazine >1 `EntityComp/Controls/TerminalHelpers.cs:59`, `EntityComp/Controls/TerminalHelpers.cs:306-315`, `EntityComp/PlatformInit.cs:729` |
| Burst Delay | slider 0..max(600, 3*ReloadTime) | not `Ui.ProhibitShotDelay` `EntityComp/Controls/TerminalHelpers.cs:60`, `EntityComp/Controls/Weapon/WeaponUi.cs:1033-1045` |
| Sequence Id | slider -1..99 | not bomb `EntityComp/Controls/TerminalHelpers.cs:61` |
| Weapon Group Id | slider 0..100 | not bomb `EntityComp/Controls/TerminalHelpers.cs:62` |
| Target Group | slider 0..5 (lead group) | fixed weapon without `Ai.OverrideLeads`, or turret with it `EntityComp/Controls/TerminalHelpers.cs:66`, `EntityComp/Controls/TerminalHelpers.cs:559-563` |
| Camera Channel | slider 0..24 | tracking or guidance `EntityComp/Controls/TerminalHelpers.cs:67` |
| WC_Friend, WC_Enemy | listbox | drone ammo `EntityComp/Controls/TerminalHelpers.cs:68-69` |
| WC_ReportTarget | switch | RequiresTarget and TrackGrids `EntityComp/Controls/TerminalHelpers.cs:70`, `EntityComp/Controls/TerminalHelpers.cs:202-207` |
| WC_TargetClosest | switch | `Targeting.AllowSwitchTargetPriority` `EntityComp/Controls/TerminalHelpers.cs:72`, `EntityComp/Controls/TerminalHelpers.cs:579-585` |
| WC_EnableFireDistribution, TurnCost (1-1000), MinLockTime (15-1200) | switch, sliders | `Targeting.AllowFireDistribution` `EntityComp/Controls/TerminalHelpers.cs:73-76`, `Support/FireDistribution/FireDistributionSupport.cs:117-119` |
| WC_ShowPTags, WC_PTagsWhitelistToggle, WC_PTagsList | switch, combo, list | `Ui.UiSetTags.Enable` (+`AllowUserWhitelistChange`) `EntityComp/Controls/TerminalHelpers.cs:80-82`, `EntityComp/Controls/TerminalHelpers.cs:595-618` |

Most of the above are also hidden when `Ui.AlternateUi` is set (`Definitions/CoreSystems.cs:315`).

### Control block (turret control block, `ControlComponent`)

All visible when the CTC comp is ready (`EntityComp/Controls/TerminalHelpers.cs:431-439`): WC_ToolsAndWeapons list, WC_Advanced, WC_ShareFireControlEnabled, WC_WCAiEnabled, WC_ControlModes, WC_TrackingMode, Weapon Range (0..max(AI MaxTargetingRange, 800)), WC_SubSystems, WC_PickSubSystem, WC_FocusFire, WC_Repel, WC_Neutrals, WC_Unowned, WC_Grids, WC_LargeGrid, WC_SmallGrid, WC_Biologicals, WC_Projectiles, WC_Supporting PD, WC_Meteors, WC_ReportTarget (`EntityComp/Controls/TerminalHelpers.cs:88-113`, `EntityComp/Controls/Control/ControlUi.cs:133-139`). quirk: on the server the CTC range setter does not call SetRange (commented out) (`EntityComp/Controls/Control/ControlUi.cs:68-70`). CTC saves a `ProtoWeaponSettings` too (`Definitions/SerializedConfigs/Control/ProtoControl.cs:39`).

Other blocks: searchlight gets range, target-type switches, camera channel (`EntityComp/Controls/TerminalHelpers.cs:116-129`); decoy gets WC_PickSubSystem (`EntityComp/Controls/TerminalHelpers.cs:131-135`); camera gets `WC_PickCameraChannel` (`EntityComp/Controls/TerminalHelpers.cs:141-145`); offensive combat block gets a read-only `WC_FixedWeapons` list (non-turret WC weapons) and its own weapon pickers hidden (`EntityComp/Controls/TerminalHelpers.cs:137-140`, `Session/SessionControls.cs:180-190`, `EntityComp/Controls/Control/ControlUi.cs:437-449`).

### Toolbar actions (weapon blocks)

Created for turret/fixed-gun/sorter types (`Session/SessionControls.cs:157-166`, `Session/SessionControls.cs:215-261`). Id, enabled-when helper (`EntityComp/Controls/CreateCustomActions.cs`):

| Action id | Effect | Enabled |
|---|---|---|
| WCShootMode | cycle shoot mode 0-3 `EntityComp/Controls/Weapon/WeaponActions.cs:242-252` | IsReady `EntityComp/Controls/CreateCustomActions.cs:65-70` |
| WCMouseToggle | toggle MouseControl/AiShoot `EntityComp/Controls/Weapon/WeaponActions.cs:267-276` | IsReady `EntityComp/Controls/CreateCustomActions.cs:79-84` |
| ActionFire | fire in KeyToggle/KeyFire modes `EntityComp/Controls/Weapon/WeaponActions.cs:126-142` | weapon, not armable `EntityComp/Controls/CreateCustomActions.cs:93-98` |
| ShootToggle, Shoot_On, Shoot_Off | WC shoot | sorter weapons only `EntityComp/Controls/CreateCustomActions.cs:178-212` |
| ControlModes | cycle Auto/Manual/Painter within valid mask `EntityComp/Controls/Weapon/WeaponActions.cs:152-215` | turret or guided `EntityComp/Controls/CreateCustomActions.cs:260-265` |
| ObjectiveMode, TrackingMode, SubSystems | cycle `EntityComp/Controls/Weapon/WeaponActions.cs:217-265` | TrackGrids / CanSetSubsystems `EntityComp/Controls/CreateCustomActions.cs:221-226` |
| WC_CycleAmmo, ForceReload | ammo `EntityComp/Controls/Weapon/WeaponActions.cs:552-557` | AmmoSelection / ForceReload `EntityComp/Controls/CreateCustomActions.cs:107-112`, `EntityComp/Controls/CreateCustomActions.cs:559-564` |
| Neutrals, Projectiles, SupportingPD, Biologicals, Meteors, Grids, Friendly, Unowned, LargeGrid, SmallGrid, FocusTargets, FocusSubSystem, WC_RepelMode | toggles | same helpers as controls `EntityComp/Controls/CreateCustomActions.cs:274-466`, `EntityComp/Controls/CreateCustomActions.cs:572-577` |
| MaxSize/MinSize Increase/Decrease | x2 or /2; MaxSize 1-16384, MinSize 0-128 `EntityComp/Controls/Weapon/WeaponActions.cs:420-466` | HasTracking |
| MaxRange Increase/Decrease | +/-10% of max range `EntityComp/Controls/Weapon/WeaponActions.cs:468-550` | HasTracking |
| WC_Increase/Decrease_CameraChannel, WC_Increase/Decrease_LeadGroup | 0-24, 0-5 `EntityComp/Controls/Weapon/WeaponActions.cs:579-625` | HasTracking / TargetLead |
| ActionFriend, ActionEnemy | drone tasks `EntityComp/Controls/CreateCustomActions.cs:134-162` | drone ammo |
| WCTargetClosest, WCEnableFireDistribution | toggles `EntityComp/Controls/CreateCustomActions.cs:1053-1077` | Allow* fields |
| Arm, Detonate, WCStartCountdown, WCStopCountdown | warhead `EntityComp/Controls/CreateCustomActions.cs:12-61` | CanBeArmed |
| WC_ROF_Increase/Decrease | ROF slider +/-0.1 `EntityComp/Controls/CreateCustomActions.cs:710-733` | ROF slider |
| WC_Overload_Toggle/_On/_Off | overload `EntityComp/Controls/CreateCustomActions.cs:648-683` | Ui.EnableOverload |

- quirk: `WC_{name}_Toggle_Off` calls the setter with `true`, so it turns the option on (`EntityComp/Controls/CreateCustomActions.cs:672-675`).
- CTC actions: WCShareFireControl, WCAiEnabled, SubSystems, ControlModes, target toggles, MaxSize/MinSize, TrackingMode, WC_RepelMode, LargeGrid/SmallGrid (`Session/SessionControls.cs:263-288`, `EntityComp/Controls/CreateCustomActions.cs:738-1037`). Camera: Next/Previous Camera Channel; decoy: Mask (`EntityComp/Controls/CreateCustomActions.cs:233-256`, `EntityComp/Controls/CreateCustomActions.cs:634-646`).

### Per-block saved settings (`ProtoWeapon.cs`)

Stored in block mod storage under GUID `75BBB4F5-4FB9-4230-BEEF-BB79C9811501` as base64 protobuf (`Session/SessionFields.cs:292`, `EntityComp/EntityData.cs:35`).

`ProtoWeaponSettings` (`Definitions/SerializedConfigs/Weapon/ProtoWeapon.cs:258-266`): ReportTarget=true, Overload=1 (2=on), RofModifier=1, Range=100 (new blocks set -1 then max MaxTargetDistance at init `EntityComp/Parts/Weapon/WeaponData.cs:127`, `EntityComp/Parts/Weapon/WeaponComp.cs:281-282`), Overrides.

`ProtoWeaponOverrides` (`Definitions/SerializedConfigs/Weapon/ProtoWeapon.cs:589-632`):

| Field | Default | Field | Default |
|---|---|---|---|
| Neutrals | false | Unowned | false |
| Friendly | false | FocusTargets | false |
| FocusSubSystem | false | MinSize | 0 |
| Control | Auto | SubSystem | Any |
| Meteors | true | Biologicals | true (new block: TrackCharacters) |
| Projectiles | true | MaxSize | 16384 |
| MoveMode | Any | Grids | true |
| ShareFireControl | false | Repel | false |
| Debug | false | Armed | false (CriticalReaction.PreArmed) |
| Override | false | BurstCount | 1 (ShotsInBurst if burst disabled) |
| BurstDelay | 0 | SequenceId | -1 |
| ArmedTimer | 0 (DefaultArmedTimer) | LeadGroup | 0 (structure default) |
| ShootMode | AiShoot | CameraChannel | 0 |
| WeaponGroupId | 0 | AiEnabled | true |
| LargeGrid / SmallGrid | true | SupportingPD | true |
| ObjectiveMode | Default | TargetClosest | true |
| EnableFireDistribution | false | TurnCost | 1000 |
| MinLockTime | 15 | EnableProjectileTagOverrides | false |
| UserProjectileTags | empty | UserPTagWhitelistSys | BlacklistOr |

New-block defaults from the definition: `EntityComp/Parts/Weapon/WeaponData.cs:92-121`. On load, state resets and target-type flags are forced off if the definition lacks that threat (`Definitions/SerializedConfigs/Weapon/ProtoWeapon.cs:25-55`); an invalid saved control mode is moved to a valid one (`EntityComp/Parts/Weapon/WeaponData.cs:149-175`). `ProtoWeaponState`: PlayerId=-1, Control=Ui, Trigger, CountingDown, CriticalReaction, ToggleCount, Tasks (`Definitions/SerializedConfigs/Weapon/ProtoWeapon.cs:314-332`).

## 5. Vanilla weapons

### Core parts (`Coreparts/Definitions/MasterConfig.cs:7-28`)

| Subtype(s) | PartName |
|---|---|
| LargeGatlingTurret; LargeGatlingTurretReskin | Large Gatling Turret `Coreparts/Definitions/Gatlings.cs:48`, `Coreparts/Definitions/Gatlings.cs:394` |
| SmallGatlingGun, SmallGatlingGunWarfare2 | Small Gatling Gun `Coreparts/Definitions/Gatlings.cs:136-174` |
| SmallGatlingTurret; SmallGatlingTurretReskin | Small Gatling Turret `Coreparts/Definitions/Gatlings.cs:277`, `Coreparts/Definitions/Gatlings.cs:507` |
| LargeMissileLauncher | Large Missile Launcher `Coreparts/Definitions/Missiles.cs:19-66` |
| LargeMissileTurret, LargeMissileTurretReskin | Large Missile Turret `Coreparts/Definitions/Missiles.cs:110-153` |
| SmallMissileLauncher, SmallMissileLauncherWarfare2 | Small Missile Launcher `Coreparts/Definitions/Missiles.cs:210-250` |
| SmallRocketLauncherReload | Reloadable Missile Launcher `Coreparts/Definitions/Missiles.cs:293-325` |
| SmallMissileTurret, SmallMissileTurretReskin | Small Missile Turret `Coreparts/Definitions/Missiles.cs:368-408` |
| LargeInteriorTurret | Interior Turret `Coreparts/Definitions/InteriorTurret.cs:19-49` |
| SmallBlockAutocannon; AutoCannonTurret | Autocannon; Autocannon Turret `Coreparts/Definitions/Autocannons.cs:19-48`, `Coreparts/Definitions/Autocannons.cs:115-143` |
| LargeBlockMediumCalibreTurret; SmallBlockMediumCalibreGun; SmallBlockMediumCalibreTurret | Large Assault Cannon Turret; Assault Cannon; Small Assault Cannon Turret `Coreparts/Definitions/Assault Cannons.cs:19-49`, `Coreparts/Definitions/Assault Cannons.cs:118-147`, `Coreparts/Definitions/Assault Cannons.cs:201-230` |
| LargeBlockLargeCalibreGun; LargeCalibreTurret | Artillery; Artillery Turret `Coreparts/Definitions/Artillery.cs:19-48`, `Coreparts/Definitions/Artillery.cs:103-133` |
| LargeRailgun; SmallRailgun | Large Railgun; Small Railgun `Coreparts/Definitions/Railguns.cs:18-53`, `Coreparts/Definitions/Railguns.cs:93-122` |
| LargeSearchlight; SmallSearchlight | Searchlight `Coreparts/Definitions/SearchLight.cs:18-55`, `Coreparts/Definitions/SearchLight.cs:97-128` |

Shared PartNames mean one WeaponOverride hits both (e.g. Large Gatling Turret and its reskin). Vanilla ids are also registered in `LoadVanillaData` (`Session/SessionSupport.cs:1634-1780`).

### How vanilla is replaced

- In `LoadData`, every `MyLargeTurretBaseDefinition` and searchlight gets `MaxRangeMeters = 0.1` (original kept in `TurretToRange`) so the game's own turret AI does nothing (`Session/SessionRun.cs:351-370`).
- Weapon defs from mods override a core part per (subtype, PartName, HardWare.Type) when `DefinitionPriority` is higher; equal or lower is skipped and logged to `debug.log` (`Session/SessionInit.cs:322-359`).
- A mod def that reuses a vanilla subtype with a different PartName or non-BlockWeapon type is split off and forced to the vanilla PartName and BlockWeapon (`Session/SessionModHandlers.cs:151-192`, `Session/SessionSupport.cs:1213-1219`).
- Vanilla weapon toolbar items in the controlled cockpit are cleared for WC/vanilla weapon ids (`Session/SessionSupport.cs:1120-1137`, `Session/SessionLocalPlayer.cs:63`).

### Non-WC weapons on grids

- A turret or `IMyUserControllableGun` that is neither a vanilla id nor a WC part, and not in `VanillaWeaponCompatible` (Large_SC_LaserDrillTurret, LargeFlareLauncher, SmallFlareLauncher, GrappleHookTurretLarge, SolarSailLauncherLarge), is scheduled for `RemoveIncompatibleBlock` (`Session/SessionEvents.cs:73-80`, `Session/SessionFields.cs:562-569`).
- Not UnsupportedMode: DS removes the block at once; SP/host removes it after 3600 ticks with red notices (`Session/SessionSupport.cs:909-927`, `Session/SessionSupport.cs:994-1013`). UnsupportedMode keeps it and only reports (`Session/SessionSupport.cs:942-992`).
- Blocks holding WC storage whose mod failed to compile are reported as orphaned, not removed (`Session/SessionSupport.cs:1015-1052`).
- quirk: `AutoCannonTurret` with a model path starting `Models` returns early, so it is neither initialised nor removed (`Session/SessionEvents.cs:67-69`).

### AutoConverter (modded vanilla-type weapons)

- Runs only when a mod name contains `VanillaToWCConverter` or Workshop 3763050326 is loaded (`Session/SessionSupport.cs:1196-1197`, `Session/SessionInit.cs:152-161`). `DisableVanillaConversion` is not read.
- Skips: vanilla subtypes, subtypes already in WC defs, `VanillaWeaponCompatible`, and mods with `Data/NoWeaponcoreConversions.txt` (`Coreparts/AutoConverter.cs:41-70`).
- Types: InteriorTurret, LargeGatlingTurret, LargeMissileTurret, SmallGatlingGun, SmallMissileLauncher(+Reload), Searchlight (`Coreparts/AutoConverter.cs:81-107`).
- HardPoint: `DefinitionPriority = int.MinValue`, PartName = block display name, DeviateShotAngle = vanilla deviation in degrees, AimingTolerance max(1, that), lead Advanced, turret rotate/elevate/limits from the turret def, IdlePower 0.002, MaxHeat 1000, ROF from ammo data (or capacitor charge), MagsToLoad from ShotsInBurst/capacity, ReloadTime from vanilla ms, inventory from the def (`Coreparts/AutoConverter.cs:726-778`).
- Ammo: BaseDamage = projectile mass damage x DamageMultiplier (missiles: health pool), Characters = health/mass damage, MaxTrajectory x RangeMultiplier, explosions become EndOfLife AOE with radius x1.25, Linear falloff (`Coreparts/AutoConverter.cs:223-224`, `Coreparts/AutoConverter.cs:287-373`, `Coreparts/AutoConverter.cs:387-442`, `Coreparts/AutoConverter.cs:490-524`). Capacitor weapons become hybrid with EnergyCost derived from recharge draw (`Coreparts/AutoConverter.cs:195-221`, `Coreparts/AutoConverter.cs:588-593`).
- Targeting: threats from turret `HiddenTargetingOptions`; fixed guns get Grids+Neutrals; MaxTargetDistance = min(ammo range, original turret range) (`Coreparts/AutoConverter.cs:809-865`).
- Block magazine replaced by `Energy` / `Energy_Missile`, description prefixed, `AutoGenerated = true` (info line "automatically converted") (`Coreparts/AutoConverter.cs:168-183`, `EntityComp/EntityEvents.cs:232-235`).

## 6. Integrations

| Mod | Detection | What WC does |
|---|---|---|
| Defense Shields | Workshop 1365616918, 2372872458, 3154379105, 3587786590, 3809704128 or local `Mods\DefenseShields` `Session/SessionSupport.cs:1184-1187` | `SApi.Load()` on channel 1365616918 `Session/SessionInit.cs:77-81`, `Support/Api/ShieldApi.cs:63`; shield hits with heat `Session/SessionDamageMgr.cs:288-321`; partial shield block protection `Session/SessionDamageMgr.cs:493`, `Session/SessionDamageMgr.cs:658`; fortified checks `Session/SessionDamageMgr.cs:359`, `Session/SessionEwar.cs:48`; LOS through shields `EntityComp/Parts/Weapon/WeaponTracking.cs:1485`; projectile shield detection `Projectiles/ProjectileHits.cs:109`, `Projectiles/ProjectileHits.cs:170-199`; target HUD shield info `Ui/Targeting/TargetUiDraw.cs:956-988`; registers attackers `Session/SessionCompMgr.cs:90-91`. A `Compromised` message makes WC suppress itself `Support/Api/ShieldApi.cs:73-74`, `Session/SessionRun.cs:67-68` |
| Water mod | Workshop 2200451495, 3283226082, 3824869788 `Session/SessionSupport.cs:1190-1191` | `WApi.Register()` handler id 50271 `Session/SessionInit.cs:83-87`, `Support/Api/WaterModAPI.cs:23`; water data refreshed every 3600 ticks `Session/SessionRun.cs:268-269`; weapons touching water disabled unless `CanShootSubmerged` `EntityComp/Parts/Weapon/WeaponComp.cs:494-500`; submerged targets skipped unless `CanTargetSubmerged`/ammo flags `Ai/AiTargeting.cs:140`; projectile water surface hits `Projectiles/ProjectileHits.cs:86-87`, `Projectiles/ProjectileHits.cs:308-310` |
| Nerd Shields | Workshop 3514216428 or local `Mods\NerdShieldsFramework` `Session/SessionSupport.cs:1192-1193` | message id 3514216898 `Support/Api/NerdShieldAPI.cs:18`; routes block and AOE damage through `ShieldDoDamage`/`ShieldDoDamageExplosion` `Session/SessionDamageMgr.cs:387-404`, `Session/SessionDamageMgr.cs:525-609` |
| ToolCore (TC API) | Workshop 3040438530 or local `Mods\ToolCore` `Session/SessionSupport.cs:1194-1195` | channel 2172757428 `Support/Api/TCApi.cs:44`; gets ToolCore def subtypes `Session/SessionInit.cs:95-100`; ToolCore sorter blocks go in the Utility subsystem, not Offense `Session/SessionJobs.cs:432-440` |

## 7. Logs

- Written with `WriteFileInLocalStorage(name + ".log", typeof(LogInstance))` (mod local storage); on init an existing `name.log` is renamed to `name_1.log` (one previous copy) (`Support/Log.cs:118-132`, `Support/Log.cs:181-214`).
- All opened once in `LoadData` (`Session/SessionRun.cs:372-393`). `debug` is the default target of `Log.Line` without a name (`Session/SessionRun.cs:379`, `Support/Log.cs:126`).

| File | Content |
|---|---|
| debug.log | general messages, def override/priority notes, incompatible blocks, exceptions `Support/Log.cs:29`, `Session/SessionInit.cs:341` |
| perf.log | CPU timings, client lag, AV scaler `Session/SessionSupport.cs:293`, `Session/SessionSupport.cs:346` |
| stats.log | counts of AIs, blocks, ray casts, draws `Session/SessionSupport.cs:294`, `AudioVisual/RunAv.cs:324` |
| net.log | bad packets and network info `Session/SessionNetwork.cs:286-288` |
| report.log | Ctrl+R problem report `Session/SessionTypes.cs:262` |
| combat.log | new threat lines (owner, faction, threat) `Session/SessionSupport.cs:1309` |
| ammostats.log, wepstats.log | tab tables of raw definition values at load `Session/SessionInit.cs:438-443`, `Support/Log.cs:133-141` |
| overrides.log | ammo override matching (MAPPED/UNMATCHED/SHADOWED) `Support/VersionControl.cs:298`, `Support/VersionControl.cs:324` |
| dmgstats.log | per weapon damage totals at unload `Session/SessionRun.cs:464-469` |
| griddmgstats.log | per grid damage totals `Ai/AiConstruct.cs:880` |
| shoot.log, shootgate.log, reloadsync.log, targetsync.log, cyclesync.log, input.log | shooting/sync diagnostics `EntityComp/Parts/Weapon/WeaponShoot.cs:47`, `Session/SessionUpdate.cs:846`, `Support/Log.cs:150-169` |

- Flood guard: outside `DebugMod`, the default log pauses for 7200 ticks after >180 lines per 120 ticks, and the player sees a "WeaponCore is crashing" notice on new exceptions (`Support/Log.cs:49-96`).
- Authors (hardcoded Steam id) can receive remote `[R-LOG]` copies (`Session/SessionFields.cs:132`, `Support/Log.cs:240-267`). The game log gets incompatible-block lists (`Session/SessionSupport.cs:958`).

## 8. Not confirmed

- Exact folder paths for world, global and local storage are decided by the game, not WC; check the game code.
- Whether `SApi.Load()` returns true on its single call at BeforeStart (it relies on Defense Shields answering synchronously); no retry was found (`Session/SessionInit.cs:77`).
- Whether any other mod or WC API path writes `ServerSettings` at runtime besides `SaveServerCfg` calls listed here.
- Full effect of `ServerSleepSupport` on targeting beyond the sleep condition.
- HUD handler restrictions (`HudHandlers`) come from the public API; not traced here.
- Which copy of WC runs when several are loaded is decided by `SUtils.ModActivate` (`Support/StaticUtils.cs:15`); not traced in full.
