# ServerShop 1.1.0 Deployment Verification

**Deployment Date:** 2026-02-07
**Version:** 1.0.0 → 1.1.0
**Build Status:** ✅ SUCCESS
**Deployed:** ✅ YES (58KB JAR copied to server)

---

## Phase 4: Server Restart (Manual Step)

You need to restart your Minecraft server to load the new plugin version.

**Steps:**
1. Stop the server gracefully (use your server management tool)
2. Start the server normally
3. Proceed to verification below

---

## Phase 5: Verification Checklist

### 5A. Check Startup Logs

Look for this line in the server console:
```
[ServerShop] ServerShop v1.1.0 enabled! Economy: Vault
```

**✅ Expected:** Shows `v1.1.0`
**❌ Problem:** If it shows `v1.0.0`, the old JAR is still active

You should also see:
```
[ServerShop] LuckPerms integration enabled for permission management
[ServerShop] EssentialsX integration enabled for nickname changes
[ServerShop] Config validation passed: sethome_slots configuration is valid
[ServerShop] Config validation passed: nickname_shop valid
[ServerShop] Config validation passed: auction_limits configuration is valid
```

---

### 5B. Test Primary Command and Aliases

All three commands should work identically:

```
/severshop help
/ss help
/buy help
```

**Expected:** Show the new help menu with all features listed

---

### 5C. Test New Commands (Features Added in 1.1.0)

#### Nickname Reset
```
/severshop nickname reset
```
**Expected:** Clear your nickname (respects cooldown)

#### Auction Limits Info
```
/severshop auction info
```
**Expected:** Show your current auction limit tier (Bronze/Silver/Gold/Platinum/Diamond)

#### Leaderboards (Admin Only)
```
/severshop sethome top
/severshop auction top
```
**Expected:** Paginated rankings of all players with their sethome slots / auction limits

---

### 5D. Test Nickname Bug Fix

Try this command **without** providing a player name:
```
/severshop nickname resetcooldown
```

**Expected (CORRECT):** Error message: "사용법: /severshop nickname resetcooldown <플레이어>"

**Old Bug Behavior (FIXED):** Would try to purchase nickname "resetcooldown"

---

### 5E. Test Existing Features (Regression Check)

Make sure old features still work:

```
/severshop sethome info
/severshop diamond 64
/severshop nickname info
```

**Expected:** All work as before

---

### 5F. Check Server Logs

Inspect `/data/minecraft_server_paper/logs/latest.log` for:
- ✅ No errors during plugin load
- ✅ No exceptions during command execution
- ✅ Version number appears in startup logs

---

## What Changed in 1.1.0

### New Features
- ✅ **Nickname reset command** (`/severshop nickname reset`)
- ✅ **Auction limit tier system** (purchase, info, leaderboard)
- ✅ **Leaderboards** for sethome and auction (`/severshop sethome top`, `/severshop auction top`)
- ✅ **Help command** (`/severshop help`)
- ✅ **Command rename** (primary: `/severshop`, aliases: `/buy`, `/ss`)

### Bug Fixes
- ✅ **Nickname argument validation** - Fixed bug where commands like `/severshop nickname resetcooldown` would try to purchase "resetcooldown" as a nickname
- ✅ **Reserved word validation** - Prevents purchasing admin commands as nicknames

### Enhancements
- ✅ **Improved console logging** - Shows current nickname when purchasing/resetting
- ✅ **Version logging** - Startup log now shows plugin version number

---

## Rollback Procedure (If Needed)

If something goes wrong, restore the old version:

```bash
cd /Users/jang/Coding/CORA-live/data/minecraft_server_paper/plugins
cp ServerShop-backup-20260207.jar ServerShop.jar
rm -f .paper-remapped/ServerShop.jar
# Restart server
```

---

## Future Version Bumping Workflow

**Every time you make changes:**

1. **Edit `pom.xml` version** (line 9) according to change type:
   - Bug fixes only → bump PATCH (1.1.0 → 1.1.1)
   - New features → bump MINOR (1.1.0 → 1.2.0)
   - Breaking changes → bump MAJOR (1.x.x → 2.0.0)

2. **Rebuild:**
   ```bash
   cd custom_plugins/ServerShop
   mvn clean package
   ```

3. **Deploy:**
   ```bash
   cp target/ServerShop-<version>.jar data/minecraft_server_paper/plugins/ServerShop.jar
   rm -f data/minecraft_server_paper/plugins/.paper-remapped/ServerShop.jar
   ```

4. **Restart server** and check logs for version number

5. **Verify** new features work

---

## Deployment Summary

| Step | Status | Details |
|------|--------|---------|
| Version bumped | ✅ | 1.0.0 → 1.1.0 |
| Code updated | ✅ | Added version logging |
| Build successful | ✅ | BUILD SUCCESS (1.452s) |
| Old JAR backed up | ✅ | ServerShop-backup-20260207.jar |
| New JAR deployed | ✅ | 58KB (was 38KB) |
| Cache cleared | ✅ | .paper-remapped/ cleaned |
| Server restart | ⏳ | **USER ACTION REQUIRED** |
| Verification | ⏳ | **USER ACTION REQUIRED** |
