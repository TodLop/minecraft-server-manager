# ServerShop - Sethome Slots Purchase Feature

## Overview

The ServerShop plugin now supports purchasing additional `/sethome` slots (EssentialsX homes) using the server economy. This extends the simple item-purchasing system to support permission-based products.

## Requirements

- **Paper MC**: 1.21.11 or higher
- **Java**: 21
- **Dependencies**:
  - Vault (economy integration)
  - LuckPerms (permission management)
  - EssentialsX (optional, for sethome functionality)

## Features

- Purchase additional sethome slots with in-game currency
- Configurable tier pricing system (default: 3-10 homes)
- Automatic LuckPerms permission granting
- OP/bypass permission for unlimited homes
- Info command to check current tier and next price
- Backward compatible with existing item purchases
- Full transaction rollback on errors

## Commands

### Purchase Next Sethome Tier
```
/buy sethome
```
Purchases the next available sethome slot tier for your player.

### Check Current Tier Info
```
/buy sethome info
```
Displays your current sethome tier and the price for the next tier.

### Existing Commands (Still Work)
```
/buy <item> [amount]  - Purchase items (e.g., /buy diamond 64)
/buy reload           - Reload config (admin only)
```

## Configuration

### ServerShop config.yml

The plugin's `config.yml` has been extended with a new `sethome_slots` section:

```yaml
sethome_slots:
  # Default number of homes everyone starts with
  default_homes: 3

  # Maximum number of homes a player can purchase
  max_homes: 10

  # Bypass permission (OP players also bypass automatically)
  bypass_permission: "servershop.sethome.bypass"

  # Price for each tier (tier number -> price in economy currency)
  # If a tier is missing or null, it cannot be purchased yet
  tier_prices:
    4: 10000
    5: 20000
    6: 30000
    7: 40000
    8: 50000
    9: 60000
    10: 70000

  # Permission node granted for each tier
  # MUST match your EssentialsX config.yml sethome-multiple section
  tier_permissions:
    3: "essentials.sethome.multiple.homes3"
    4: "essentials.sethome.multiple.homes4"
    5: "essentials.sethome.multiple.homes5"
    6: "essentials.sethome.multiple.homes6"
    7: "essentials.sethome.multiple.homes7"
    8: "essentials.sethome.multiple.homes8"
    9: "essentials.sethome.multiple.homes9"
    10: "essentials.sethome.multiple.homes10"

# New messages for sethome purchases
messages:
  # ... existing messages ...

  sethome-purchased: "&a추가 홈 슬롯을 구매했습니다! (&e%current_tier% &a-> &e%next_tier%&a) 잔액: &e%balance%원"
  sethome-max-reached: "&c이미 최대 홈 슬롯(&e%max_homes%개&c)을 보유하고 있습니다."
  sethome-op-unlimited: "&c당신은 OP 권한으로 무제한 홈을 사용할 수 있습니다."
  sethome-no-price: "&c이 홈 슬롯 티어는 아직 구매할 수 없습니다."
  sethome-current-tier: "&e현재 홈 슬롯: &a%current_tier%개 &7| &e다음 티어 가격: &a%next_price%원"
  sethome-console-error: "&cOnly players can purchase sethome slots."
```

### EssentialsX config.yml

You **MUST** configure EssentialsX to recognize the permission nodes. Add this to `plugins/Essentials/config.yml`:

```yaml
sethome-multiple:
  homes3: 3
  homes4: 4
  homes5: 5
  homes6: 6
  homes7: 7
  homes8: 8
  homes9: 9
  homes10: 10
```

The `homesX` keys must match the permission names in ServerShop's `tier_permissions`.

## How It Works

### Tier Detection

1. **Unlimited Status**: If player is OP or has `servershop.sethome.bypass`, they have unlimited homes and cannot purchase
2. **Permission Check**: Checks from highest to lowest tier (10 → 3) to find the player's current tier
3. **Default Tier**: If no permissions found, player has default tier (3 homes)

### Purchase Flow

1. Check if player has unlimited homes → reject if true
2. Check if player is at max tier → reject if true
3. Get next tier price from config → reject if null/missing
4. Check player balance → reject if insufficient
5. **Withdraw money** via Vault
6. **Grant permission** via LuckPerms
7. If permission grant fails → **refund money** automatically
8. Send success message to player
9. Log purchase to console

### Error Handling

The system includes automatic rollback:
- If LuckPerms permission grant fails after money withdrawal, the money is automatically refunded
- All errors are logged to console with details
- Players receive clear error messages

## Permissions

- `servershop.buy` (default: true) - Allows using /buy command
- `servershop.admin` (default: op) - Allows reloading config
- `servershop.sethome.bypass` (default: op) - Gives unlimited sethome slots

## Examples

### Example 1: Normal Purchase Flow

```
Player: /buy sethome info
Server: [서버상점] 현재 홈 슬롯: 3개 | 다음 티어 가격: 10000원

Player: /buy sethome
Server: [서버상점] 추가 홈 슬롯을 구매했습니다! (3 -> 4) 잔액: 90000원

Player: /sethome home4
Server: [Essentials] Home home4 set.
```

### Example 2: Insufficient Funds

```
Player: /buy sethome
Server: [서버상점] 돈이 부족합니다! (필요: 20000원, 보유: 15000원)
```

### Example 3: Max Tier Reached

```
Player: /buy sethome
Server: [서버상점] 이미 최대 홈 슬롯(10개)을 보유하고 있습니다.
```

### Example 4: OP Player

```
Player: /buy sethome
Server: [서버상점] 당신은 OP 권한으로 무제한 홈을 사용할 수 있습니다.
```

## Architecture

### New Classes

1. **LuckPermsIntegration.java**
   - Wraps LuckPerms API
   - Handles permission granting and checking
   - Thread-safe user loading

2. **TierCalculator.java**
   - Determines player's current tier
   - Checks unlimited status
   - Calculates next tier pricing

3. **SetHomeSlotPurchaseHandler.java**
   - Implements purchase flow
   - Handles Vault transactions
   - Manages rollback on errors

4. **ConfigValidator.java**
   - Validates config structure
   - Checks tier consistency
   - Provides helpful error messages

### Modified Classes

1. **ServerShop.java**
   - Initialize LuckPerms integration
   - Validate config on startup
   - Expose LuckPerms integration to commands

2. **BuyCommand.java**
   - Route `/buy sethome` to handler
   - Enhanced tab completion
   - Config validation on reload

## Backward Compatibility

All existing functionality is preserved:
- `/buy diamond` still works for item purchases
- `/buy diamond 64` still works with amounts
- `/buy reload` still works for admins
- Existing config sections are unchanged
- No breaking changes to API or behavior

## Testing Checklist

- [ ] Default tier detection (3 homes for new players)
- [ ] Normal purchase flow (money withdrawal + permission grant)
- [ ] Insufficient funds error message
- [ ] Max tier reached message
- [ ] OP/bypass unlimited homes message
- [ ] Missing tier price handling
- [ ] Config reload applies changes
- [ ] Sequential purchases (3→4→5)
- [ ] Backward compatibility (item purchases still work)
- [ ] Console/RCON command handling
- [ ] Permission persistence across restarts
- [ ] Transaction rollback on LuckPerms failure

## Troubleshooting

### "LuckPerms not found! Disabling plugin..."

**Solution**: Install LuckPerms on your server. Download from: https://luckperms.net/

### "/sethome doesn't recognize my purchased slots"

**Solution**: Make sure your EssentialsX `config.yml` has the `sethome-multiple` section configured correctly. The permission names must match ServerShop's `tier_permissions`.

### "Config validation failed"

**Solution**: Check your `config.yml` for:
- `default_homes` and `max_homes` are present and valid
- `max_homes` > `default_homes`
- `tier_prices` section exists
- `tier_permissions` section exists with all tier mappings

### Purchases not persisting after restart

**Solution**: Make sure LuckPerms is saving data correctly. Check LuckPerms storage configuration.

## Console Logging

The plugin logs all sethome slot purchases:

```
[ServerShop] PlayerName purchased sethome slot tier 3->4 for 10000 (permission: essentials.sethome.multiple.homes4)
```

This helps with:
- Tracking economy flow
- Debugging permission issues
- Auditing player purchases

## Future Extensibility

This design can be easily extended to support other permission-based products:

```yaml
# Example: PlayerAuctions listing slots
playerauctions_slots:
  default_slots: 3
  max_slots: 10
  tier_prices:
    4: 50000
    5: 100000
  tier_permissions:
    3: "playerauctions.listings.3"
    4: "playerauctions.listings.4"
```

Just create a new handler class following the same pattern as `SetHomeSlotPurchaseHandler`.

## Credits

- Built for Near Outpost Minecraft Server
- Paper MC 1.21.11 | Java 21
- Integrates with Vault, LuckPerms, and EssentialsX
