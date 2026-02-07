# ServerShop Version History

## Semantic Versioning Scheme

**Format:** `MAJOR.MINOR.PATCH`

- **MAJOR** (1.x.x): Breaking changes, incompatible API changes
- **MINOR** (x.1.x): New features, backwards-compatible
- **PATCH** (x.x.1): Bug fixes only, backwards-compatible

---

## Version 1.1.0 (2026-02-07)

**Type:** Minor Release (New Features)

### New Features
- **Nickname reset command** - `/severshop nickname reset` to clear nickname
- **Auction limit tier system** - 5 tiers (Bronze → Diamond) with progressive limits
  - Purchase: `/severshop auction <tier>`
  - Info: `/severshop auction info`
  - Leaderboard: `/severshop auction top` (admin only)
- **Sethome leaderboard** - `/severshop sethome top` (admin only)
- **Help command** - `/severshop help` for full feature list
- **Command rename** - Primary command changed from `/buy` to `/severshop`
  - Aliases: `/ss`, `/buy` (backwards compatible)

### Bug Fixes
- Fixed nickname argument validation bug where admin subcommands (like `resetcooldown`) could be purchased as nicknames
- Added reserved word validation to prevent purchasing command names

### Enhancements
- Added version number to startup logs (`ServerShop v1.1.0 enabled!`)
- Improved console logging for nickname purchases (shows current nickname)
- Added reserved word list for nickname validation

### Technical Changes
- Added `getDescription().getVersion()` to onEnable() logging
- Updated `plugin.yml` to use `/severshop` as primary command
- Added new command handlers in `NicknameHandler` and `AuctionHandler`

---

## Version 1.0.0 (2026-01-31)

**Type:** Initial Release

### Core Features
- **Sethome slot purchases** - Buy additional /sethome slots using economy
  - Info: `/buy sethome info`
  - Purchase: `/buy sethome <tier>`
- **Item purchases** - Direct item purchases with automatic inventory management
  - Syntax: `/buy <item> [amount]`
- **Nickname shop** - Purchase custom nicknames with cooldown system
  - Info: `/buy nickname info`
  - Purchase: `/buy nickname <nickname>`
  - Reset cooldown (admin): `/buy nickname resetcooldown <player>`

### Integrations
- **Vault** - Economy system integration (required)
- **LuckPerms** - Permission management for sethome slots (required)
- **EssentialsX** - Nickname changes (optional, falls back to display name)

### Config System
- YAML configuration with validation
- Item shop definitions with price and display names
- Sethome tier definitions with prices and slot counts
- Nickname shop cooldown and price settings

### Admin Features
- Config validation on startup
- Detailed logging for all transactions
- Cooldown reset commands for admins

---

## Planned Features (Future)

### Version 1.2.0 (Potential)
- Web API integration for purchase history
- Discord webhook notifications for high-value purchases
- Seasonal sales and discount system
- Gift system (buy items/features for other players)

### Version 1.x.x (Potential)
- Refund system for recent purchases
- Purchase history command for players
- Economy statistics dashboard
- Bulk purchase discounts

---

## Deployment History

| Version | Build Date | Deploy Date | Status |
|---------|------------|-------------|--------|
| 1.0.0 | 2026-01-31 | 2026-01-31 | Released |
| 1.1.0 | 2026-02-07 | 2026-02-07 | **Current** |

---

## Breaking Changes Log

*No breaking changes yet - all updates have been backwards-compatible*

---

## Dependencies

| Dependency | Version | Required | Notes |
|------------|---------|----------|-------|
| Paper API | 1.21-R0.1-SNAPSHOT | Yes | Minecraft server platform |
| Vault API | 1.7.1 | Yes | Economy system |
| LuckPerms | 5.4 | Yes | Permission management |
| EssentialsX | 2.20.1 | No | Nickname changes (fallback available) |
| Java | 21 | Yes | Runtime requirement |

---

## File Size History

| Version | JAR Size | Notes |
|---------|----------|-------|
| 1.0.0 | 38 KB | Initial release |
| 1.1.0 | 58 KB | +20 KB due to new handlers and leaderboard system |
