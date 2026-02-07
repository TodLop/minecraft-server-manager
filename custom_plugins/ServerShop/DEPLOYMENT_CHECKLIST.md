# ServerShop Sethome Slots - Deployment Checklist

## ✅ Pre-Deployment Verification

### Plugin Compatibility
- [x] EssentialsX 2.21.2 - Compatible ✅
- [x] LuckPerms 5.5.17 - Compatible ✅
- [x] Vault 2.17.0 - Compatible ✅
- [x] Paper 1.21.11 - Compatible ✅
- [x] Java 21 - Compatible ✅

### Compatibility Fix Applied
- [x] Legacy permission detection added ✅
- [x] Config includes vip/staff/default mappings ✅
- [x] Plugin recompiled successfully ✅

---

## 📋 Deployment Steps

### Step 1: Backup Current Setup

```bash
# Backup LuckPerms data
/lp export backup-before-servershop-$(date +%Y%m%d)

# Backup EssentialsX config
cp plugins/Essentials/config.yml plugins/Essentials/config.yml.backup-$(date +%Y%m%d)

# Backup economy data (if using EssentialsX economy)
cp plugins/Essentials/userdata/*.yml plugins/Essentials/userdata-backup/
```

- [ ] LuckPerms data backed up
- [ ] EssentialsX config backed up
- [ ] Economy data backed up

### Step 2: Update EssentialsX Config

Edit `plugins/Essentials/config.yml` and find the `sethome-multiple` section:

**Current:**
```yaml
sethome-multiple:
  default: 3
  vip: 5
  staff: 10
```

**Add these lines (keep existing):**
```yaml
sethome-multiple:
  default: 3          # Keep existing
  vip: 5              # Keep existing
  staff: 10           # Keep existing
  homes3: 3           # ADD THIS
  homes4: 4           # ADD THIS
  homes5: 5           # ADD THIS
  homes6: 6           # ADD THIS
  homes7: 7           # ADD THIS
  homes8: 8           # ADD THIS
  homes9: 9           # ADD THIS
  homes10: 10         # ADD THIS
```

- [ ] EssentialsX config updated
- [ ] No tabs used (only spaces for indentation)
- [ ] Saved as UTF-8

### Step 3: Grant Base Permission

All players need the base permission for multiple homes:

```bash
# Grant to default group (all players)
/lp group default permission set essentials.sethome.multiple true

# Verify it was set
/lp group default permission info
```

- [ ] Base permission granted to default group
- [ ] Verified with `/lp group default permission info`

### Step 4: Stop Server

```bash
# Stop the server gracefully
/stop
```

Wait for "Done! Closed the server" message.

- [ ] Server stopped gracefully
- [ ] No errors in console

### Step 5: Deploy Plugin

```bash
# Copy new plugin to plugins folder
cp /path/to/ServerShop-1.0.0.jar /path/to/server/plugins/

# Verify file copied correctly
ls -lh plugins/ServerShop-1.0.0.jar
```

- [ ] Plugin JAR copied to plugins folder
- [ ] File size is ~21KB

### Step 6: Start Server

```bash
# Start the server
./start.sh  # or whatever your startup script is
```

Watch console for:
```
[ServerShop] ServerShop enabled! Economy: ...
[ServerShop] LuckPerms integration enabled for permission management
[ServerShop] Config validation passed: sethome_slots configuration is valid
```

- [ ] Server started successfully
- [ ] ServerShop loaded without errors
- [ ] LuckPerms integration confirmed
- [ ] Config validation passed

### Step 7: Reload EssentialsX

```bash
# Reload EssentialsX to apply config changes
/essentials reload
```

- [ ] EssentialsX reloaded successfully
- [ ] No errors in console

---

## 🧪 Post-Deployment Testing

### Test 1: Plugin Commands Available

```bash
/buy
/buy sethome
/buy sethome info
```

- [ ] Commands work without errors
- [ ] Tab completion shows "sethome" option

### Test 2: New Player (Default Tier)

```bash
# As a regular player with no special permissions
/buy sethome info
```

**Expected:** "현재 홈 슬롯: 3개 | 다음 티어 가격: 10000원"

- [ ] Shows tier 3 correctly
- [ ] Shows price 10000 correctly

### Test 3: VIP Player Detection

```bash
# Find a player with VIP permission
/lp user <vip-player> permission info | grep sethome

# Test as that player
/buy sethome info
```

**Expected:** "현재 홈 슬롯: 5개 | 다음 티어 가격: 30000원"

- [ ] Detects VIP tier 5 correctly
- [ ] Next tier is 6 (not 4)
- [ ] Price is 30000 (tier 6 price)

### Test 4: Staff Player Detection

```bash
# Find a player with staff permission
/lp user <staff-player> permission info | grep sethome

# Test as that player
/buy sethome info
```

**Expected:** "이미 최대 홈 슬롯(10개)을 보유하고 있습니다."

- [ ] Detects staff tier 10 correctly
- [ ] Shows max tier message

### Test 5: Actual Purchase Flow

```bash
# Give test player money
/eco give <player> 50000

# As player, check balance
/balance

# Purchase tier 4
/buy sethome

# Verify permission granted
/lp user <player> permission info | grep homes4

# Test setting home
/sethome home4
```

**Expected:**
- Money withdrawn correctly
- Permission granted: `essentials.sethome.multiple.homes4`
- Can set 4th home with `/sethome home4`
- Success message displayed

- [ ] Money withdrawn correctly
- [ ] Permission granted via LuckPerms
- [ ] Success message displayed in Korean
- [ ] Can set new home

### Test 6: Sequential Purchases

```bash
# As test player with tier 4
/buy sethome  # Should buy tier 5
/buy sethome  # Should buy tier 6
/buy sethome info  # Should show tier 6
```

- [ ] Sequential purchases work
- [ ] Each purchase grants correct tier
- [ ] Tier detection updates correctly

### Test 7: Insufficient Funds

```bash
# Remove player's money
/eco take <player> 999999

# Try to purchase
/buy sethome
```

**Expected:** "돈이 부족합니다! (필요: 10000원, 보유: 0원)"

- [ ] Shows insufficient funds message
- [ ] No permission granted
- [ ] No money withdrawn

### Test 8: OP Player

```bash
# As OP player
/buy sethome
```

**Expected:** "당신은 OP 권한으로 무제한 홈을 사용할 수 있습니다."

- [ ] Shows unlimited message
- [ ] Cannot purchase

### Test 9: Backward Compatibility

```bash
# Test existing item purchases still work
/buy diamond
/buy diamond 64
```

- [ ] Diamond purchase works
- [ ] Amount parameter works
- [ ] Inventory receives items

### Test 10: Config Reload

```bash
# Change a price in config.yml
# tier_prices.4: 10000 -> 5000

# Reload config
/buy reload

# Test new price
/buy sethome info
```

- [ ] Config reloads successfully
- [ ] New prices applied
- [ ] No errors in console

### Test 11: Server Restart Persistence

```bash
# Purchase a tier
/buy sethome

# Restart server
/stop
# Start server

# Check permission persists
/lp user <player> permission info | grep homes
```

- [ ] Permission persists after restart
- [ ] LuckPerms saved data correctly
- [ ] Player still has purchased tier

### Test 12: EssentialsX Integration

```bash
# After purchasing tier 4
/sethome home1
/sethome home2
/sethome home3
/sethome home4
/sethome home5  # Should fail - only have 4 homes
```

**Expected:**
- homes1-4 work
- home5 fails with "You may only set 4 homes"

- [ ] EssentialsX respects purchased tier
- [ ] Can set correct number of homes
- [ ] Cannot exceed purchased limit

---

## 📊 Monitoring

### Console Logs to Watch

**Successful purchase:**
```
[ServerShop] PlayerName purchased sethome slot tier 3->4 for 10000 (permission: essentials.sethome.multiple.homes4)
```

**Permission grant:**
```
[LuckPerms] Granted permission essentials.sethome.multiple.homes4 to player UUID
```

**Config validation:**
```
[ServerShop] Config validation passed: sethome_slots configuration is valid
```

### Error Logs to Watch For

**LuckPerms not found:**
```
[ServerShop] LuckPerms not found! Disabling plugin...
```
→ Ensure LuckPerms is installed

**Config validation failed:**
```
[ServerShop] Config validation failed: ...
```
→ Check config.yml syntax

**Permission grant failed:**
```
[ServerShop] Failed to grant permission to PlayerName! Purchase cancelled and refunded.
```
→ Check LuckPerms is functioning, money should be auto-refunded

---

## 🔧 Troubleshooting

### Issue: "LuckPerms not found"

**Cause:** LuckPerms not installed or not loaded

**Fix:**
```bash
# Check if LuckPerms is loaded
/plugins | grep LuckPerms

# If not, install LuckPerms
# Download from https://luckperms.net/
```

### Issue: "/sethome doesn't work after purchase"

**Cause:** Player doesn't have base permission

**Fix:**
```bash
# Grant base permission
/lp user <player> permission set essentials.sethome.multiple true
```

### Issue: "VIP players can re-buy tier 4 and 5"

**Cause:** `legacy_permissions` not configured correctly

**Fix:**
- Check `config.yml` has `legacy_permissions.vip: 5`
- Reload config: `/buy reload`
- Test again: `/buy sethome info`

### Issue: "Config validation failed"

**Cause:** Config syntax error

**Fix:**
- Check YAML syntax (no tabs, proper indentation)
- Ensure all tier_permissions have values
- Reload: `/buy reload`

### Issue: "Players lose money but don't get permission"

**Cause:** LuckPerms permission grant failed

**Fix:**
- Check LuckPerms is functioning: `/lp`
- Check console for errors
- **Money should auto-refund** - if not, manually refund:
  ```bash
  /eco give <player> <amount>
  ```

---

## 📈 Success Metrics

After 24 hours of deployment, verify:

- [ ] No console errors related to ServerShop
- [ ] Players successfully purchasing sethome slots
- [ ] No complaints about lost money
- [ ] No complaints about permissions not working
- [ ] EssentialsX `/sethome` respecting purchased tiers
- [ ] Existing VIP/staff players detected correctly

---

## 🎯 Deployment Decision

### Ready to Deploy? Check All:

- [ ] All backups completed
- [ ] EssentialsX config updated with homes3-homes10
- [ ] Base permission granted to default group
- [ ] ServerShop-1.0.0.jar ready
- [ ] Test environment validated (if available)
- [ ] Rollback plan understood

### If All Checked: ✅ DEPLOY

### If Any Issues: ⚠️ INVESTIGATE FIRST

---

## 📞 Support References

**Documentation:**
- `SETHOME_FEATURE.md` - Feature documentation
- `COMPATIBILITY_REPORT.md` - Full compatibility analysis
- `COMPATIBILITY_FIX_APPLIED.md` - Details on legacy permission fix
- `IMPLEMENTATION_SUMMARY.md` - Technical implementation details

**External Resources:**
- [EssentialsX Multihome Wiki](https://wiki.mc-ess.net/wiki/Multihome)
- [LuckPerms Documentation](https://luckperms.net/wiki/)
- [Paper MC Documentation](https://docs.papermc.io/)

---

**Deployment Checklist Version:** 1.0
**Last Updated:** 2026-01-31
**Plugin Version:** ServerShop 1.0.0
**Status:** Ready for Production Deployment ✅
