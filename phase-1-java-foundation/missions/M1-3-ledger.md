# M1-3 거래내역과 `Ledger`

## 배경
은행에서 잔액은 "결과"일 뿐이고, 진짜 원천 데이터는 **거래내역(원장)**이다.
"잔액 = 모든 거래의 합"이 항상 성립해야 하며, 거래내역은 **절대 수정·삭제하지 않고 추가만** 한다(append-only).
잘못된 거래는 지우는 게 아니라 **반대 거래(취소 거래)**를 추가해서 바로잡는다.

## 요구사항

### `TransactionType` (enum)
- `DEPOSIT`, `WITHDRAWAL`, `TRANSFER_IN`, `TRANSFER_OUT`, `REVERSAL`(취소)
- 각 타입은 잔액에 미치는 방향(+1 / -1)을 안다. `REVERSAL`은 원거래의 반대 방향.

### `Transaction` (불변, `record` 권장)
| 필드 | 설명 |
|---|---|
| `String id` | 거래 ID (UUID) |
| `AccountNumber accountNumber` | 계좌 |
| `TransactionType type` | 유형 |
| `Money amount` | 금액 (항상 양수) |
| `Money balanceAfter` | 거래 후 잔액 |
| `LocalDateTime occurredAt` | 거래 시각 |
| `String memo` | 적요 (예: "급여", "홍길동 이체") |
| `String reversalOf` | 취소 거래라면 원거래 ID, 아니면 null |

- compact constructor에서 검증: amount는 양수, 필수값 null 금지

### `Ledger`
- `append(Transaction)` — 추가만 가능
- `List<Transaction> history(AccountNumber)` — 시간순, **수정 불가능한 리스트** 반환
- `List<Transaction> history(AccountNumber, LocalDate from, LocalDate to)` — 기간 조회 (양 끝 포함)
- `Money sumBy(AccountNumber, TransactionType)` — 유형별 합계
- `Map<TransactionType, Money> summary(AccountNumber)` — 유형별 합계 맵
- `Money replayBalance(AccountNumber)` — 거래내역만으로 잔액을 다시 계산
- `Optional<Transaction> findById(String id)`

### `Account` 확장 (M1-2 코드 수정)
- 입금/출금 시 `Transaction`을 생성해서 반환하도록 변경: `Transaction deposit(Money, String memo)`
- 시각을 직접 `LocalDateTime.now()`로 만들지 말고 **`Clock`을 주입**받아 사용 (테스트에서 시간 고정)

### `BankService` (애플리케이션 서비스)
- 여러 `Account`와 하나의 `Ledger`를 가진다 (`Map<AccountNumber, Account>`)
- `deposit(AccountNumber, Money, memo)`, `withdraw(...)`, `transfer(from, to, Money, memo)`
- 이체는 출금 계좌에 `TRANSFER_OUT`, 입금 계좌에 `TRANSFER_IN` 두 건이 기록된다
- `reverse(String transactionId)` — 원거래의 반대 거래를 기록하고 잔액을 원복
  - 이미 취소된 거래를 다시 취소하면 예외
  - 취소 결과 잔액이 음수가 되면 예외 (입금 후 이미 출금해버린 경우)

## 테스트 시나리오

| # | 시나리오 | 기대 결과 |
|---|---|---|
| 1 | 입금 3회, 출금 2회 후 `replayBalance` | `account.balance()`와 같음 |
| 2 | `history()`가 반환한 리스트에 `add` | `UnsupportedOperationException` |
| 3 | 고정 `Clock`으로 1/1, 1/15, 1/31, 2/1에 거래 → 1/1~1/31 조회 | 3건 |
| 4 | `summary()` | 유형별 합계가 정확 |
| 5 | A→B 10,000원 이체 | A -10,000, B +10,000, 거래 2건, **A+B 총액 불변** |
| 6 | 잔액 부족 이체 | 예외, A/B 잔액·거래내역 모두 변화 없음 |
| 7 | 입금 취소 | 잔액 원복, `REVERSAL` 거래 추가, 원거래는 그대로 남아 있음 |
| 8 | 같은 거래 두 번 취소 | 예외 |
| 9 | 10,000 입금 → 8,000 출금 → 입금 취소 | 예외 (잔액 부족) |
| 10 | 존재하지 않는 계좌로 이체 | `AccountNotFoundException` |

## 스트림 연습 포인트
- `sumBy`: `filter` → `map` → `reduce(Money.zero(...), Money::plus)`
- `summary`: `Collectors.groupingBy(Transaction::type, Collectors.reducing(...))`
- `history(from, to)`: `LocalDate` ↔ `LocalDateTime` 비교 주의 (to 날짜의 23:59:59.999...)

## 힌트

<details>
<summary>힌트 1: Clock 주입</summary>

```java
Clock fixed = Clock.fixed(Instant.parse("2026-01-15T10:00:00Z"), ZoneId.of("Asia/Seoul"));
LocalDateTime.now(fixed);
```
테스트에서 시간을 바꿔가며 거래를 만들려면 가변 Clock을 직접 만들어도 된다 (`Clock`을 상속한 테스트용 클래스).
</details>

<details>
<summary>힌트 2: 이체 시 원자성</summary>

출금 성공 → 입금 실패(예: B 계좌가 FROZEN)하면? 지금은 단일 스레드지만, **모든 검증을 먼저 끝낸 후 변경**하는 순서를 고민해보자.
이 문제는 Phase 5의 `@Transactional`, Phase 8의 Saga로 이어진다.
</details>

## 생각해볼 질문
1. 거래내역을 수정/삭제하지 않고 반대 거래로 바로잡는 이유는? (감사, 규제, 대사)
2. `Account.balance`와 `Ledger.replayBalance`가 다르다면 무엇을 믿어야 하나? 이 둘을 따로 두는 이유는?
3. `LocalDateTime.now()`를 코드 곳곳에서 직접 호출하면 테스트가 어려운 이유는?
4. 시나리오 5의 "총액 불변"은 Phase 2에서 동시성 테스트의 핵심 검증 조건이 된다. 왜일까?
