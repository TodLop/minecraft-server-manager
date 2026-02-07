# ServerShop Sethome Slots - Compatibility Report

## ✅ Plugin Compatibility Status

### Installed Versions on Your Server

- **EssentialsX**: 2.21.2 ✅
- **LuckPerms**: 5.5.17 (Bukkit) ✅
- **Vault**: VaultUnlocked 2.17.0 ✅
- **Paper**: 1.21.11 ✅

### API Versions Used in Implementation

- **LuckPerms API**: 5.4 (provided scope)
- **Vault API**: 1.7.1 (provided scope)
- **Paper API**: 1.21 (provided scope)

---

## ✅ LuckPerms Compatibility

### Your Server Version
- **LuckPerms-Bukkit 5.5.17** (installed)

### Implementation Uses
- **LuckPerms API 5.4** (in pom.xml)

### Compatibility Assessment: ✅ FULLY COMPATIBLE

According to [LuckPerms semantic versioning](https://github.com/LuckPerms/LuckPerms/wiki/Developer-API):
> The API uses Semantic Versioning, meaning whenever a non-backwards compatible change is made, the major version will increment.

Since both versions share **major version 5**, API 5.4 code is **backward compatible** with LuckPerms 5.5.17. The plugin will work without any issues.

**Methods used:**
- `LuckPerms.getUserManager().loadUser(uuid)` ✅
- `User.data().add(node)` ✅
- `LuckPerms.getUserManager().saveUser(user)` ✅
- `User.getCachedData().getPermissionData().checkPermission()` ✅

All these methods are stable and available in both 5.4 and 5.5.17.

---

## ⚠️ EssentialsX Compatibility - ACTION REQUIRED

### Your Current EssentialsX Config

```yaml
sethome-multiple:
  default: 3
  vip: 5
  staff: 10
```

### What ServerShop Expects

```yaml
sethome-multiple:
  default: 3           # Keep your existing
  vip: 5              # Keep your existing
  staff: 10           # Keep your existing
  homes3: 3           # ADD THIS
  homes4: 4           # ADD THIS
  homes5: 5           # ADD THIS
  homes6: 6           # ADD THIS
  homes7: 7           # ADD THIS
  homes8: 8           # ADD THIS
  homes9: 9           # ADD THIS
  homes10: 10         # ADD THIS
```

### ✅ Configuration Update Required

You need to **ADD** the new entries to your existing EssentialsX config. The existing `default`, `vip`, and `staff` entries will continue to work and won't conflict.

According to [EssentialsX Multihome documentation](https://wiki.mc-ess.net/wiki/Multihome):
> Players with `essentials.sethome.multiple` and `essentials.sethome.multiple.vip` will have 5 homes. Remember, they must have BOTH permission nodes.

### Permission Format: ✅ CORRECT

ServerShop will grant permissions in the format:
- `essentials.sethome.multiple.homes3`
- `essentials.sethome.multiple.homes4`
- `essentials.sethome.multiple.homes5`
- etc.

This format is **correct** and matches EssentialsX's expected permission format.

### ⚠️ IMPORTANT: Base Permission Required

Players **MUST** also have the base permission:
- `essentials.sethome.multiple`

Without this base permission, the tier-specific permissions won't work.

**Recommendation:** Grant `essentials.sethome.multiple` to your default group in LuckPerms:
```
/lp group default permission set essentials.sethome.multiple true
```

This allows all players to use the multiple homes system, and ServerShop will manage the tier limits.

---

## ✅ Vault Compatibility

### Your Server Version
- **VaultUnlocked 2.17.0** (installed)

### Implementation Uses
- **Vault API 1.7.1** (standard version)

### Compatibility Assessment: ✅ FULLY COMPATIBLE

VaultUnlocked is a fork of Vault that continues development. It maintains full backward compatibility with the standard Vault API 1.7.1.

**Methods used:**
- `Economy.getBalance(player)` ✅
- `Economy.withdrawPlayer(player, amount)` ✅
- `Economy.depositPlayer(player, amount)` ✅
- `EconomyResponse.transactionSuccess()` ✅

All standard Vault economy methods work with VaultUnlocked.

---

## 🔍 Potential Conflicts Check

### Existing Permissions System

Let me check if there are any conflicting permission setups:

#### Current sethome-multiple Groups
- `default: 3` → grants `essentials.sethome.multiple.default`
- `vip: 5` → grants `essentials.sethome.multiple.vip`
- `staff: 10` → grants `essentials.sethome.multiple.staff`

#### New ServerShop Tiers
- `homes3: 3` → grants `essentials.sethome.multiple.homes3`
- `homes4: 4` → grants `essentials.sethome.multiple.homes4`
- etc.

### ✅ No Conflicts

These are **separate permission nodes** and will not conflict. Players can even have multiple permissions, and EssentialsX will use the **highest value**.

**Example:**
- Player has `essentials.sethome.multiple.vip` (5 homes)
- Player purchases and gets `essentials.sethome.multiple.homes7` (7 homes)
- Result: Player has **7 homes** (highest value wins)

---

## 📊 Migration Path for Existing Players

### ✅ Automatic Legacy Permission Detection

**ServerShop includes automatic detection of existing permission groups!**

The plugin includes a `legacy_permissions` section in config.yml that automatically detects players with existing vip/staff permissions:

```yaml
sethome_slots:
  legacy_permissions:
    vip: 5      # essentials.sethome.multiple.vip
    staff: 10   # essentials.sethome.multiple.staff
    default: 3  # essentials.sethome.multiple.default
```

This is **already configured** in the default config and matches your server's existing EssentialsX setup!

### Scenario 1: Players with "vip" Permission

**Current state:**
- Player has `essentials.sethome.multiple.vip` (5 homes)

**After ServerShop deployment:**
- ✅ TierCalculator automatically detects tier 5 via `legacy_permissions`
- Player can purchase tier 6 (next tier above their current 5)
- No duplicate purchases allowed

**Action needed:** ✅ None - works automatically

### Scenario 2: Players with "default" Permission

**Current state:**
- Player has `essentials.sethome.multiple.default` (3 homes)

**After ServerShop deployment:**
- Player has 3 homes from `default` permission
- Player can purchase tier 4 (next tier above 3)
- ServerShop will grant `essentials.sethome.multiple.homes4`

**Action needed:** ✅ None - works automatically

### Scenario 3: Players with "staff" Permission

**Current state:**
- Player has `essentials.sethome.multiple.staff` (10 homes)

**After ServerShop deployment:**
- Player has 10 homes (already at max)
- ServerShop will show "already at maximum" message
- No purchase needed

**Action needed:** ✅ None - works automatically

---

## ⚠️ Configuration Issues to Address

### Issue 1: Base Permission Not Granted

**Problem:** If players don't have `essentials.sethome.multiple`, the tier permissions won't work.

**Solution:**
```bash
/lp group default permission set essentials.sethome.multiple true
```

### Issue 2: EssentialsX Config Missing New Tiers

**Problem:** Without the `homes3` through `homes10` entries in EssentialsX config, the permissions will be ignored.

**Solution:** Add to `plugins/Essentials/config.yml`:
```yaml
sethome-multiple:
  default: 3           # existing
  vip: 5              # existing
  staff: 10           # existing
  homes3: 3           # ADD
  homes4: 4           # ADD
  homes5: 5           # ADD
  homes6: 6           # ADD
  homes7: 7           # ADD
  homes8: 8           # ADD
  homes9: 9           # ADD
  homes10: 10         # ADD
```

Then reload:
```bash
/essentials reload
```

### Issue 3: ServerShop Config Permission Mismatch

**Problem:** If ServerShop's `tier_permissions` don't match EssentialsX's config keys, homes won't work.

**Solution:** Already correct! The default config uses:
```yaml
tier_permissions:
  3: "essentials.sethome.multiple.homes3"
  4: "essentials.sethome.multiple.homes4"
  # etc.
```

These match the EssentialsX config keys.

---

## 🧪 Testing Recommendations

### Pre-Deployment Tests

1. **Backup LuckPerms data:**
   ```bash
   /lp export backup-before-servershop
   ```

2. **Backup EssentialsX config:**
   ```bash
   cp plugins/Essentials/config.yml plugins/Essentials/config.yml.backup
   ```

3. **Test on a staging/test player:**
   - Create a test player account
   - Give them money: `/eco give testplayer 100000`
   - Test purchase: `/buy sethome`
   - Verify permission: `/lp user testplayer permission info`
   - Test setting home: `/sethome test4`

### Post-Deployment Checks

1. **Check plugin loaded:**
   ```
   [ServerShop] ServerShop enabled! Economy: ...
   [ServerShop] LuckPerms integration enabled for permission management
   ```

2. **Verify no errors in console** related to:
   - LuckPerms API initialization
   - Config validation
   - Permission granting

3. **Test each scenario:**
   - New player (should start at tier 3)
   - Player with existing VIP (should detect tier 5)
   - OP player (should show unlimited message)

---

## 🛡️ Error Handling & Rollback

### Transaction Rollback

ServerShop includes automatic rollback:

```java
// If LuckPerms grant fails after Vault withdrawal
economy.depositPlayer(player, price);  // Refund
player.sendMessage("Purchase failed, money refunded");
```

This prevents money loss if permission granting fails.

### Manual Rollback (if needed)

If you need to manually refund a player:

1. **Check console logs** for the purchase:
   ```
   [ServerShop] PlayerName purchased sethome slot tier 3->4 for 10000 (permission: essentials.sethome.multiple.homes4)
   ```

2. **Refund money:**
   ```
   /eco give PlayerName 10000
   ```

3. **Remove permission:**
   ```
   /lp user PlayerName permission unset essentials.sethome.multiple.homes4
   ```

---

## 📋 Deployment Checklist

Before deploying ServerShop:

- [ ] Back up LuckPerms data (`/lp export`)
- [ ] Back up EssentialsX config
- [ ] Stop the server
- [ ] Add `homes3` through `homes10` to EssentialsX config
- [ ] Grant `essentials.sethome.multiple` to default group
- [ ] Copy `ServerShop-1.0.0.jar` to plugins folder
- [ ] Start the server
- [ ] Check console for successful load
- [ ] Test with `/buy sethome info` on yourself
- [ ] Test purchase with a test account
- [ ] Verify homes work with `/sethome home4`

---

## ✅ Final Compatibility Summary

| Component | Your Version | Required | Status |
|-----------|--------------|----------|--------|
| EssentialsX | 2.21.2 | 2.x | ✅ Compatible |
| LuckPerms | 5.5.17 | 5.4+ | ✅ Compatible |
| Vault | 2.17.0 | 1.7+ | ✅ Compatible |
| Paper | 1.21.11 | 1.21+ | ✅ Compatible |
| Java | 21 | 21 | ✅ Compatible |

**Overall Status: ✅ FULLY COMPATIBLE**

Only requirement: Add the `homes3` through `homes10` entries to your EssentialsX config.

---

## 📚 References

- [EssentialsX Multihome Documentation](https://wiki.mc-ess.net/wiki/Multihome)
- [LuckPerms Developer API](https://github.com/LuckPerms/LuckPerms/wiki/Developer-API)
- [LuckPerms Semantic Versioning](https://luckperms.net/wiki/Developer-API)
- [EssentialsX Permissions](https://essinfo.xeya.me/permissions.html)

---

**Report Generated:** 2026-01-31
**Plugin Version:** ServerShop 1.0.0
**Compatibility Check:** PASSED ✅
