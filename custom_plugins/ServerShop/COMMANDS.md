# ServerShop Commands

Primary command: `/severshop` (aliases: `/buy`, `/ss`)

---

## Player Commands

| Command | Description |
|---------|-------------|
| `/severshop help` | 전체 명령어 목록 표시 |
| `/severshop <아이템> [수량]` | 아이템 구매 (예: `/severshop diamond 64`) |
| `/severshop sethome` | 다음 홈 슬롯 구매 |
| `/severshop sethome info` | 현재 홈 슬롯 정보 확인 |
| `/severshop nickname <닉네임>` | 닉네임 변경 구매 |
| `/severshop nickname info` | 닉네임 및 쿨다운 정보 확인 |
| `/severshop nickname reset` | 닉네임을 기본값으로 초기화 (쿨다운 적용) |
| `/severshop anvil` | 대장간 사용 권한 구매 |
| `/severshop anvil info` | 대장간 권한 가격 확인 |
| `/severshop craft` | 작업대 사용 권한 구매 |
| `/severshop craft info` | 작업대 권한 가격 확인 |
| `/severshop auction` | 경매 한도 추가 구매 |
| `/severshop auction info` | 경매 한도 정보 확인 |

## Admin Commands

| Command | Permission | Description |
|---------|-----------|-------------|
| `/severshop reload` | `servershop.admin` | 설정 다시 로드 |
| `/severshop sethome info <플레이어>` | OP | 다른 플레이어 홈 슬롯 확인 |
| `/severshop sethome top [페이지]` | `servershop.admin` | 홈 슬롯 순위 (전체 플레이어) |
| `/severshop nickname set <플레이어> <닉네임>` | `servershop.nickname.admin` | 관리자 닉네임 설정 |
| `/severshop nickname resetcooldown <플레이어>` | `servershop.nickname.admin` | 닉네임 쿨다운 초기화 |
| `/severshop nickname reset <플레이어>` | `servershop.nickname.admin` | 플레이어 닉네임 초기화 |
| `/severshop auction info <플레이어>` | `servershop.admin` | 다른 플레이어 경매 한도 확인 |
| `/severshop auction top [페이지]` | `servershop.admin` | 경매 한도 순위 (전체 플레이어) |

## Permissions

| Permission | Default | Description |
|-----------|---------|-------------|
| `servershop.buy` | true | 서버 상점 사용 |
| `servershop.admin` | op | 관리자 명령어 (reload, leaderboards) |
| `servershop.sethome.bypass` | op | 무제한 홈 슬롯 |
| `servershop.nickname.admin` | op | 닉네임 관리자 명령어 |
| `servershop.anvil.use` | false | 대장간 사용 (구매 필요) |
| `servershop.craft.use` | false | 작업대 사용 (구매 필요) |

## Configuration

Key config sections in `config.yml`:

- **prices** — 아이템별 구매 가격
- **sethome_slots** — 홈 슬롯 티어 가격 및 권한 매핑
- **nickname_shop** — 닉네임 가격, 쿨다운, 규칙, 예약어
- **anvil_access** — 대장간 권한 구매 가격
- **craft_access** — 작업대 권한 구매 가격
- **auction_limits** — 경매 한도 티어 가격 및 PA 권한 매핑
- **messages** — 모든 메시지 커스터마이징

## Pricing

| Item | Price |
|------|-------|
| Diamond | 300원 |
| Diamond Block | 2,700원 |
| Sethome Slot 4-10 | 10,000원 ~ 70,000원 |
| Nickname Change | 10,000원 (7일 쿨다운) |
| Anvil Access | 500,000원 |
| Craft Access | 1,000,000원 |
| Auction Limit 4-10 | 50,000원 ~ 3,200,000원 (지수적 증가) |

## Dependencies

- Vault (required)
- LuckPerms (required)
- EssentialsX (optional — required for nickname features)
