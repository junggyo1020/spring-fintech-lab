# M1-2 `Account` 엔티티와 도메인 예외

## 배경
계좌는 은행의 핵심 엔티티다. 잔액은 **오직 계좌 자신의 메서드**로만 바뀌어야 하고,
"잔액은 음수가 될 수 없다", "해지된 계좌는 거래할 수 없다" 같은 규칙을 계좌가 스스로 지켜야 한다.

## 요구사항

### `AccountNumber` (값 객체)
- 형식: `XXX-XXXX-XXXX` (숫자 3-4-4), 예: `110-1234-5678`
- 형식이 틀리면 `IllegalArgumentException`
- `masked()`: `"110-****-5678"` (로그/예외 메시지용)
- `record` 사용 권장

### `AccountStatus` (enum)
- `ACTIVE`(정상), `FROZEN`(정지), `CLOSED`(해지)
- 상태 전이 규칙을 enum 안에 둔다:
  - `ACTIVE → FROZEN`, `ACTIVE → CLOSED`, `FROZEN → ACTIVE`, `FROZEN → CLOSED`
  - `CLOSED`에서는 어디로도 갈 수 없음
  - `boolean canTransitTo(AccountStatus next)`

### `Account` (엔티티)
| 필드 | 설명 |
|---|---|
| `AccountNumber number` | 식별자, 불변 |
| `String ownerName` | 예금주 |
| `Money balance` | 잔액 |
| `AccountStatus status` | 상태 |

- **생성:** `Account.open(AccountNumber, String ownerName, Currency)` → 잔액 0, `ACTIVE`
- **입금:** `deposit(Money amount)`
  - 금액은 0보다 커야 함 → 아니면 `InvalidAmountException`
  - 통화가 계좌와 달라야 하면 → `CurrencyMismatchException`
  - `ACTIVE`가 아니면 → `AccountNotActiveException`
- **출금:** `withdraw(Money amount)`
  - 입금 규칙 + 잔액 부족 시 `InsufficientBalanceException`
- **상태 변경:** `freeze()`, `unfreeze()`, `close()`
  - 허용되지 않은 전이면 `IllegalAccountStateTransitionException`
  - `close()`는 잔액이 0일 때만 가능 → 아니면 `AccountHasBalanceException`
- **동등성:** `AccountNumber`만으로 판단
- **잔액 조회:** `balance()` (Money는 불변이므로 그대로 반환해도 안전 — 왜 안전한지 TIL에 설명)
- **setter 금지**

### 예외 계층
```
BankException (abstract, extends RuntimeException)
├── InvalidAmountException
├── InsufficientBalanceException      // 계좌번호(마스킹), 요청 금액, 현재 잔액 포함
├── AccountNotActiveException         // 계좌번호(마스킹), 현재 상태 포함
├── IllegalAccountStateTransitionException  // 현재 상태, 요청 상태 포함
└── AccountHasBalanceException
```
- `BankException`에 `ErrorCode` enum(예: `INSUFFICIENT_BALANCE`)을 두면 Phase 4에서 API 에러 응답 만들 때 그대로 쓸 수 있다.

## 테스트 시나리오

| # | 시나리오 | 기대 결과 |
|---|---|---|
| 1 | 계좌 개설 | 잔액 0, 상태 ACTIVE |
| 2 | 10,000원 입금 | 잔액 10,000 |
| 3 | 0원 / -1원 입금 | `InvalidAmountException` |
| 4 | 10,000원 있을 때 10,000원 출금 | 잔액 0 (경계값) |
| 5 | 10,000원 있을 때 10,001원 출금 | `InsufficientBalanceException`, **잔액은 그대로 10,000** |
| 6 | 원화 계좌에 USD 입금 | `CurrencyMismatchException` |
| 7 | FROZEN 계좌에 입금/출금 | `AccountNotActiveException` |
| 8 | FROZEN → unfreeze → 입금 | 성공 |
| 9 | 잔액 있는 계좌 close | `AccountHasBalanceException` |
| 10 | CLOSED 계좌 freeze | `IllegalAccountStateTransitionException` |
| 11 | `AccountStatus` 모든 전이 조합(3×3) | `@ParameterizedTest` + `@CsvSource`로 9개 케이스 검증 |
| 12 | 예외 메시지 | 전체 계좌번호가 아니라 마스킹된 번호를 포함 |
| 13 | 계좌번호 형식 오류 (`"1101234"`, `"abc-defg-hijk"`, `null`) | 예외 |
| 14 | 같은 계좌번호, 다른 잔액의 두 Account | `equals == true` |

## 제약
- `Account`의 잔액을 외부에서 바꿀 방법이 없어야 한다 (리플렉션 제외)
- 예외 발생 시 **상태가 변경되지 않아야 한다** (시나리오 5) — 검증을 먼저, 변경은 나중에

## 힌트

<details>
<summary>힌트 1: 검증 순서</summary>

`withdraw`에서 검증 순서는 어떻게 하는 게 좋을까? 상태 확인 → 금액 유효성 → 통화 → 잔액.
순서에 따라 어떤 예외가 먼저 나가는지가 달라지고, 그게 곧 API 응답이 된다.
</details>

<details>
<summary>힌트 2: enum에 전이 규칙 넣기</summary>

각 enum 상수가 `Set<AccountStatus>`를 갖게 하려면 enum 생성자에서 자기 자신보다 뒤에 선언된 상수를 참조할 수 없는 문제가 생긴다.
`switch` 표현식으로 `canTransitTo`를 구현하는 방법도 있다.
</details>

## 생각해볼 질문
1. `Account`에 `setBalance()`가 있으면 어떤 일이 생길 수 있나? "빈약한 도메인 모델(Anemic Domain Model)"이란?
2. 잔액 부족을 예외로 처리하는 것과 `boolean`/`Result` 타입을 반환하는 것의 장단점은?
3. 엔티티의 `equals`를 ID로만 비교하는 이유는? `hashCode`에 가변 필드를 넣으면 무슨 문제가 생기나?
4. 이 `Account`를 두 스레드가 동시에 `withdraw` 하면 어떻게 될까? (Phase 2 예고 — 지금은 예측만 적어두기)
