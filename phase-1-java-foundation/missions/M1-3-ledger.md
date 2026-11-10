# M1-3 거래내역과 `Ledger`

> 가이드 수준: L1 · 예상 시간: 5~7h · 선행: M1-2

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 입금·출금·이체·취소를 모두 거래내역(`Transaction`)으로 남기고, `Ledger.replayBalance`로 다시 계산한 잔액이 `Account.balance()`와 같다는 것을 테스트로 보여준다.
- 이체 대상 계좌가 `FROZEN`일 때 출금 계좌의 잔액과 거래내역이 하나도 바뀌지 않는 것을 테스트로 보여준다.
- 고정 `Clock`을 주입해 거래 시각이 정해진 값(`2026-01-15T19:00`)으로 기록되는 것을 테스트로 보여준다.
- `Collectors.groupingBy`로 거래 유형별 합계 맵을 만든다.

## 배경
은행에서 잔액은 거래의 결과이고, 원천 데이터는 거래내역(원장)이다. "잔액 = 모든 거래 금액의 부호 있는 합"이 항상 성립해야 하며, 일 마감 때 두 값을 비교하는 작업을 대사(reconciliation)라고 한다.
거래내역은 수정·삭제하지 않고 추가만 한다(append-only). 잘못된 거래는 지우지 않고 취소 거래(`REVERSAL`)를 추가해서 바로잡는다. 원거래를 지우면 "누가 언제 무엇을 바로잡았는가"를 감사 때 보여줄 수 없기 때문이다.
이체는 출금과 입금 두 건의 기록이 함께 성공하거나 함께 실패해야 한다. 출금만 기록되고 입금이 빠지면 고객 돈이 사라진다.
M1-2의 `Account`와 예외 계층을 그대로 쓰고, 거래 기록 생성은 새로 만드는 애플리케이션 서비스 `BankService`가 맡는다. 이 `BankService`는 M1-5에서 콘솔 UI와 연결되고, Phase 2에서 여러 스레드가 동시에 호출하는 대상이 된다.

## 요구사항

### 1. `TransactionType` (enum, 패키지 `lab.bank.ledger`)
| 상수 | `int sign()` | 의미 |
|---|---|---|
| `DEPOSIT` | `+1` | 입금 |
| `WITHDRAWAL` | `-1` | 출금 |
| `TRANSFER_IN` | `+1` | 이체 입금 |
| `TRANSFER_OUT` | `-1` | 이체 출금 |
| `REVERSAL` | `0` | 취소. 방향은 enum만으로 정할 수 없고, `reversalOf`가 가리키는 원거래 방향의 반대다 |

### 2. `Transaction` (불변, `record` 권장, 패키지 `lab.bank.ledger`)
| 필드 | 설명 |
|---|---|
| `String id` | 거래 ID (UUID 문자열) |
| `AccountNumber accountNumber` | 계좌 |
| `TransactionType type` | 유형 |
| `Money amount` | 금액. 항상 양수 |
| `Money balanceAfter` | 거래 직후 계좌 잔액 |
| `LocalDateTime occurredAt` | 거래 시각 |
| `String memo` | 적요 (예: `"급여"`, `"홍길동 이체"`). 빈 문자열 허용 |
| `String reversalOf` | `REVERSAL`이면 원거래 ID, 아니면 `null` |

compact constructor 검사 (위반 시 `IllegalArgumentException`. `Transaction`은 `BankService`만 만들므로 위반은 코드 버그다):
- `reversalOf`를 뺀 7개 필드는 `null`이 아니다.
- `amount`는 양수다.
- `type == REVERSAL`이면 `reversalOf != null`, 그 외 유형이면 `reversalOf == null`.

### 3. `Ledger` (패키지 `lab.bank.ledger`)
| 시그니처 | 동작 |
|---|---|
| `void append(Transaction tx)` | 끝에 추가한다. `null`이거나 같은 `id`가 이미 있으면 `IllegalArgumentException` |
| `List<Transaction> history(AccountNumber number)` | 해당 계좌 거래를 `occurredAt` 오름차순(같으면 추가 순서)으로 반환. 수정 불가능한 리스트. 거래가 없으면 빈 리스트 |
| `List<Transaction> history(AccountNumber number, LocalDate from, LocalDate to)` | `from` 날짜 0시 이상, `to` 다음 날 0시 미만인 거래. `from > to`면 `IllegalArgumentException` |
| `Money sumBy(AccountNumber number, TransactionType type, Currency currency)` | 해당 유형 `amount`의 합. 거래가 없으면 `Money.zero(currency)` |
| `Map<TransactionType, Money> summary(AccountNumber number)` | 유형별 `amount` 합계. 거래가 한 건도 없는 유형은 키가 없다 |
| `Money replayBalance(AccountNumber number, Currency currency)` | 거래내역만으로 잔액을 다시 계산 (아래 규칙) |
| `Optional<Transaction> findById(String id)` | ID로 조회 |
| `boolean isReversed(String originalId)` | `reversalOf == originalId`인 거래가 있으면 `true` |

`sumBy`, `replayBalance`가 `Currency`를 받는 이유: 거래가 0건이면 결과 `Money`의 통화를 거래내역에서 알 수 없다.

**`replayBalance` 규칙**
- `REVERSAL`이 아닌 거래: `type.sign() × amount`를 더한다.
- `REVERSAL` 거래: `findById(reversalOf)`로 원거래를 찾아 `-(원거래.type.sign()) × amount`를 더한다. 원거래가 없으면 `IllegalStateException`.

### 4. `BankService` (애플리케이션 서비스, 패키지 `lab.bank.application`)
`Account`는 M1-2 그대로 두고 수정하지 않는다. `Account.deposit`/`withdraw`는 잔액만 바꾸고, 거래 ID·거래 시각·`Transaction` 생성은 `BankService`가 한다.
`Clock`과 ID 생성을 엔티티가 아니라 서비스에 두는 이유: `Account`가 시계와 ID 생성기를 알면 엔티티 테스트마다 `Clock`을 준비해야 하고, Phase 5에서 JPA 엔티티로 바꿀 때 엔티티에 외부 의존성이 남는다.

| 시그니처 | 동작 |
|---|---|
| `BankService(Ledger ledger, Clock clock)` | 생성자 주입 |
| `void addAccount(Account account)` | 계좌 등록. `null`이거나 같은 계좌번호가 이미 있으면 `IllegalArgumentException` |
| `Account findAccount(AccountNumber number)` | 없으면 `AccountNotFoundException` |
| `Transaction deposit(AccountNumber number, Money amount, String memo)` | `Account.deposit` 후 `DEPOSIT` 거래를 기록하고 반환 |
| `Transaction withdraw(AccountNumber number, Money amount, String memo)` | `Account.withdraw` 후 `WITHDRAWAL` 거래를 기록하고 반환 |
| `List<Transaction> transfer(AccountNumber from, AccountNumber to, Money amount, String memo)` | `[TRANSFER_OUT 거래, TRANSFER_IN 거래]` 순서로 반환. 두 거래의 `occurredAt`과 `memo`는 같다 |
| `Transaction reverse(String transactionId)` | 원거래의 취소 거래를 기록하고 반환 |

- 거래 ID: `UUID.randomUUID().toString()`
- 거래 시각: `LocalDateTime.now(clock)`
- `balanceAfter`: `Account` 메서드 호출 직후의 `account.balance()`
- `memo`가 `null`이면 `IllegalArgumentException`

**`transfer` 검사 순서** (하나라도 실패하면 두 계좌의 잔액과 `Ledger`는 호출 전과 같다)
1. 인자가 `null` → `IllegalArgumentException`
2. `from.equals(to)` → `SameAccountTransferException`
3. `from` 계좌 조회, `to` 계좌 조회 → 없으면 `AccountNotFoundException`
4. `from` 계좌에 대해 M1-2 `withdraw` 검사 1~5, `to` 계좌에 대해 M1-2 `deposit` 검사 1~4. 실패 시 M1-2와 같은 예외

**`reverse` 규칙**
1. `transactionId`의 거래가 없으면 → `TransactionNotFoundException`
2. 원거래 유형이 `DEPOSIT`, `WITHDRAWAL`이 아니면 → `InvalidReversalException` (이 미션의 규칙: 이체 한쪽만 취소하면 두 계좌 기록이 어긋나므로 이체 취소는 다루지 않고, 취소 거래의 재취소도 허용하지 않는다)
3. 이미 취소된 거래면(`ledger.isReversed`) → `TransactionAlreadyReversedException`
4. `DEPOSIT` 취소는 `account.withdraw(원거래 금액)`, `WITHDRAWAL` 취소는 `account.deposit(원거래 금액)`. 여기서 나는 예외(`InsufficientBalanceException`, `AccountNotActiveException`)는 그대로 던지고 `REVERSAL`을 기록하지 않는다.
5. `REVERSAL` 거래: `amount` = 원거래 금액, `reversalOf` = 원거래 ID, `memo` = `"취소: " + 원거래 memo`

**추가 예외** (패키지 `lab.bank.application`, 모두 `BankException` 상속, M1-2의 `ErrorCode`에 4개 추가)

| 예외 | `ErrorCode` | 메시지에 넣을 정보 |
|---|---|---|
| `SameAccountTransferException` | `SAME_ACCOUNT_TRANSFER` | 마스킹 계좌번호 |
| `TransactionNotFoundException` | `TRANSACTION_NOT_FOUND` | 거래 ID |
| `TransactionAlreadyReversedException` | `TRANSACTION_ALREADY_REVERSED` | 원거래 ID |
| `InvalidReversalException` | `INVALID_REVERSAL` | 거래 ID, 원거래 유형 |

## 테스트 시나리오

공통 준비: 계좌 `A`(`110-0000-0001`), `B`(`110-0000-0002`)를 KRW로 개설해 `addAccount`로 등록. 금액은 모두 원.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | `A`에 입금 10,000 / 20,000 / 30,000, 출금 5,000 / 15,000 | `replayBalance(A, KRW)` | `Money.won(40000)`, `findAccount(A).balance()`와 같음 |
| 2 | 1의 상태 | `history(A).add(아무 거래)` | `UnsupportedOperationException` |
| 3 | 시각을 바꿀 수 있는 테스트용 `Clock`으로 `A`에 2026-01-01T00:00, 2026-01-15T12:00, 2026-01-31T23:59:59, 2026-02-01T00:00 입금 | `history(A, 2026-01-01, 2026-01-31)` | 3건 (2/1 0시 거래 제외) |
| 4 | 3의 상태 | `history(A, 2026-02-01, 2026-02-01)` | 1건 |
| 5 | 1의 상태 | `summary(A)` | 키 2개: `DEPOSIT=KRW 60,000`, `WITHDRAWAL=KRW 20,000` |
| 6 | 1의 상태 | `sumBy(A, TRANSFER_IN, KRW)` | `Money.won(0)` |
| 7 | `A` 잔액 50,000, `B` 잔액 0 | `transfer(A, B, 10000원, "용돈")` | `A` 40,000, `B` 10,000, 반환 리스트 2건(`TRANSFER_OUT` `balanceAfter` 40,000 / `TRANSFER_IN` `balanceAfter` 10,000), `A`+`B` = 50,000 |
| 8 | `A` 잔액 5,000 | `transfer(A, B, 10000원, "")` | `InsufficientBalanceException`, `A` 5,000·`B` 0, `history(A)`·`history(B)` 건수 변화 없음 |
| 9 | `A` 잔액 50,000, `B`를 `freeze()` | `transfer(A, B, 10000원, "")` | `AccountNotActiveException`, `A` 50,000 그대로, `history(A)`에 `TRANSFER_OUT` 없음 |
| 10 | `A` 잔액 50,000 | `transfer(A, 없는 계좌 110-9999-9999, 10000원, "")` | `AccountNotFoundException`, `A` 50,000 그대로 |
| 11 | - | `transfer(A, A, 10000원, "")` | `SameAccountTransferException` |
| 12 | `A`에 10,000 입금(거래 `d`) | `reverse(d.id())` | 잔액 0, 반환 거래 `type == REVERSAL`, `reversalOf == d.id()`, `memo == "취소: " + d.memo()`, `findById(d.id())`가 원거래를 그대로 반환, `history(A)` 2건 |
| 13 | 12의 상태 | `reverse(d.id())` 다시 호출 | `TransactionAlreadyReversedException` |
| 14 | `A`에 10,000 입금(`d`) → 8,000 출금 | `reverse(d.id())` | `InsufficientBalanceException`, 잔액 2,000, `REVERSAL` 거래 없음 |
| 15 | `A`에 10,000 입금 → 3,000 출금(거래 `w`) | `reverse(w.id())` 후 `replayBalance(A, KRW)` | 잔액 10,000, `replayBalance`도 `Money.won(10000)` (`REVERSAL` 방향을 원거래 `WITHDRAWAL`에서 가져옴) |
| 16 | 7의 이체 결과 `TRANSFER_OUT` 거래 `t` | `reverse(t.id())` | `InvalidReversalException` |
| 17 | - | `reverse("없는-id")` | `TransactionNotFoundException` |
| 18 | `Clock.fixed(Instant.parse("2026-01-15T10:00:00Z"), ZoneId.of("Asia/Seoul"))`로 만든 `BankService` | `deposit(A, 1000원, "")`의 `occurredAt()` | `LocalDateTime.of(2026, 1, 15, 19, 0)` (UTC 10:00 = 서울 19:00) |
| 19 | - | `Transaction` 생성 시 `amount`가 `Money.won(0)` / `type == REVERSAL`인데 `reversalOf == null` | 각각 `IllegalArgumentException` |

## 제약
- `Ledger`에는 수정·삭제 메서드를 만들지 않는다. `history`가 반환한 리스트로 내부 리스트를 바꿀 수 없어야 한다 (시나리오 2).
- `LocalDateTime.now()`(인자 없는 버전)를 운영 코드에 쓰지 않는다. 시각은 주입받은 `Clock`으로만 만든다.
- `Account`에 `Clock`, `Ledger`, `Transaction` 의존을 추가하지 않는다.
- 이체 실패 시 출금 계좌만 바뀐 상태로 끝나면 안 된다 (시나리오 8~10). 모든 검사를 끝낸 뒤에 두 계좌를 바꾼다.

## 힌트
<details>
<summary>힌트 1: Clock 주입과 시간대</summary>

`Clock.fixed(Instant.parse("2026-01-15T10:00:00Z"), ZoneId.of("Asia/Seoul"))`의 `Instant`는 UTC 10:00이고, `LocalDateTime.now(clock)`은 시계의 `ZoneId`(서울, UTC+9) 기준으로 바꾼 `2026-01-15T19:00`을 반환한다. 시나리오 18의 기대값이 10:00이 아닌 이유다.
시나리오 3처럼 테스트 중에 시각을 바꾸려면 `java.time.Clock`을 상속한 테스트용 클래스를 `src/test`에 만든다. 구현할 추상 메서드는 `getZone()`, `withZone(ZoneId)`, `instant()` 3개다. `Clock` Javadoc의 "Implementation Requirements" 절을 읽는다.
</details>

<details>
<summary>힌트 2: 이체를 검사 → 변경 순서로 만들기</summary>

`from.withdraw()`를 먼저 호출하고 `to.deposit()`에서 예외가 나면 `from`의 잔액은 이미 줄어 있다. 두 계좌의 검사를 모두 끝낸 뒤 변경을 시작해야 한다.
`Account`에 "이 금액을 입금/출금할 수 있는가"만 검사하고 상태는 바꾸지 않는 메서드를 추가할지, 검사 로직을 `BankService`에 둘지 비교한다. 검사 로직이 두 곳에 있으면 M1-2의 검사 순서와 어긋날 수 있다.
이 문제는 Phase 5의 `@Transactional` 롤백, Phase 8의 Saga 보상 트랜잭션으로 이어진다.
</details>

<details>
<summary>힌트 3: 기간 조회와 스트림</summary>

`LocalDate`를 `LocalDateTime`과 비교하려면 반열린 구간 `[from.atStartOfDay(), to.plusDays(1).atStartOfDay())`를 쓴다. 시작 시각은 `!isBefore`, 끝 시각은 `isBefore`로 비교한다. `to`에 `23:59:59.999...`를 붙이면 나노초 단위 거래를 놓칠 수 있다.
`sumBy`: `filter` → `map(Transaction::amount)` → `reduce(Money.zero(currency), Money::plus)`
`summary`: `Collectors.groupingBy(Transaction::type, Collectors.reducing(...))`. `reducing`의 항등값으로 어떤 통화의 0원을 넣어야 하는지 생각해본다. `Collectors.toMap(키, 값, Money::plus)`도 같은 결과를 낸다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 시나리오 1~19에 해당하는 테스트와 M1-1, M1-2 테스트가 모두 PASSED로 출력된다
- [ ] `src/main`에서 `LocalDateTime.now()`(인자 없음)를 검색하면 결과가 0건이다
- [ ] `Account.java`가 M1-2 완료 시점과 비교해 바뀌지 않았거나, 바뀌었다면 PR 본문에 이유가 적혀 있다
- [ ] `git log --oneline`에서 테스트 커밋이 구현 커밋보다 먼저 있다

## 생각해볼 질문
1. 거래내역을 수정·삭제하지 않고 취소 거래로 바로잡는 이유를 감사(누가 언제 바꿨는가), 대사(원장 합계와 잔액 비교) 두 관점에서 설명한다.
2. `Account.balance()`와 `Ledger.replayBalance()`가 다르면 어느 쪽을 믿어야 하는가? 잔액을 매번 거래내역에서 계산하지 않고 `Account`에 따로 저장하는 이유를 거래 100만 건인 계좌의 잔액 조회 비용으로 설명한다.
3. `REVERSAL`의 방향을 `TransactionType`만으로 정할 수 없게 만든 설계와, `DEPOSIT_REVERSAL`·`WITHDRAWAL_REVERSAL` 두 상수로 나누는 설계를 비교한다. `replayBalance`가 원거래를 조회해야 하는지가 어떻게 달라지는가?
4. 시나리오 7의 "`A`+`B` 총액 불변"은 Phase 2 동시성 테스트에서 스레드 1,000개가 무작위로 이체한 뒤 검사하는 조건이 된다. 락이 없으면 이 조건이 어떤 순서로 실행될 때 깨지는가?
