# M5-4 JPA 전환과 영속성 컨텍스트

> 가이드 수준: L2, 예상 시간: 6~8h, 선행: M5-3

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- Phase 1의 `Account`를 JPA 엔티티로 매핑하고 거래내역 엔티티 `AccountTransaction`을 추가해, `ddl-auto: validate`로 Flyway 스키마와 매핑이 일치함을 애플리케이션 시작으로 보여준다.
- 1차 캐시, 동일성 보장, 변경 감지, 쓰기 지연, flush 시점을 Hibernate `Statistics` 값(실행된 SQL 개수, UPDATE 횟수)으로 검증하는 테스트 13개(시나리오 1~13)를 작성한다.
- Hibernate 프록시가 섞여도 `Account.equals`가 맞게 동작함을 테스트로 보여주고, `getClass()` 비교로 바꾸면 실패하는 것을 기록한다.
- Phase 2 `TransferEngine`을 JPA로 구현한 `JpaTransferEngine`이 이체 한 번에 SQL 7개(SELECT 3, INSERT 2, UPDATE 2)를 실행함을 테스트로 고정하고, Phase 4 API를 이 엔진과 DB 저장소에 연결해 M4-2, M4-4, M4-5 API 테스트를 그대로 통과시킨다.

## 배경
M5-3의 `JdbcTemplate` 코드에는 아직 `UPDATE account SET balance = ?` 같은 SQL과 `RowMapper`가 있다. JPA는 "객체의 값을 바꾸면 커밋할 때 UPDATE가 나간다"는 모델로 이것을 없앤다.
그 대가로 SQL이 언제, 몇 개 나가는지 코드에서 보이지 않는다. 금융 시스템에서는 "출금 후 잔액 조회 SQL이 UPDATE보다 먼저 나갔다", "트랜잭션이 끝난 객체를 고쳤는데 저장이 안 됐다" 같은 일이 잔액 오류로 이어진다.
그래서 이 미션의 테스트는 결과 잔액뿐 아니라 **실행된 SQL 개수**를 검증한다. M5-3에서 Testcontainers로 만든 통합 테스트 환경을 그대로 쓴다.

## 요구사항
1. **의존성과 설정.** README의 M5-4 의존성 줄과 `application.yml`의 `spring.jpa` 부분을 추가한다. `ddl-auto`는 `validate`만 쓴다 (스키마는 Flyway가 만든다).
2. **`Account` 매핑** (`lab.bank.account.Account`에 직접 JPA 애너테이션을 붙인다: 이 미션의 규칙).
   - 테이블 `account`. `id`는 `@Id` + `GenerationType.IDENTITY`.
   - `AccountNumber`는 컬럼 `number` 하나에, `Money balance`는 컬럼 `balance`와 `currency`에 매핑한다. 방법(`AttributeConverter`, `@Embeddable`)은 직접 고르고, 고른 이유를 `docs/m5-4-mapping.md`에 2줄로 적는다.
   - `ownerName`, `ownerId`(M4-7)는 같은 이름의 snake_case 컬럼에 매핑한다. `AccountStatus`는 문자열(`ACTIVE`)로 저장한다.
   - JPA가 요구하는 기본 생성자는 `protected`로 둔다. setter는 여전히 만들지 않는다 (Phase 1 규칙).
   - 동등성은 `AccountNumber`만 비교한다 (Phase 1 규칙 유지). 프록시와 비교해도 맞아야 한다 (시나리오 11).
   - `@OneToMany(mappedBy = "account") List<AccountTransaction> transactions` 연관을 둔다 (M5-5에서 사용). 지연 로딩이 기본값이다.
3. **`lab.bank.ledger.AccountTransaction` 엔티티.** 테이블 `account_transaction`의 모든 컬럼을 매핑한다. `account`는 `@ManyToOne(fetch = FetchType.LAZY)` + `@JoinColumn(name = "account_id")`. Phase 1의 `Transaction`은 `record`라서 JPA 엔티티가 될 수 없으므로 그대로 두고, `AccountTransaction`에 `Transaction`으로 바꾸는 메서드(예: `toTransaction()`)와 `Transaction`으로부터 만드는 정적 팩토리를 둔다.
4. **리포지토리.**
   - `lab.bank.persistence.jpa.SpringDataAccountRepository extends JpaRepository<Account, Long>`: `Optional<Account> findByNumber(AccountNumber number)` 포함
   - `lab.bank.persistence.jpa.SpringDataAccountTransactionRepository extends JpaRepository<AccountTransaction, Long>`
   - `lab.bank.persistence.jpa.JpaAccountRepository implements AccountRepository`: 위 Spring Data 리포지토리에 위임. 이것을 기본 `AccountRepository` 빈으로 하고, M5-3의 `JdbcTemplateAccountRepository`와 `JdbcTemplateTransferService`에는 `@Profile("jdbc")`를 붙인다.
5. **`lab.bank.transfer.JpaTransferEngine implements TransferEngine`** (Phase 2 인터페이스 그대로). `transfer`는 `@Transactional` 안에서 두 계좌를 `findByNumber`로 읽고, M2-7의 검증 순서(상태 → 통화 → 잔액 → 1일 한도)를 지킨 뒤 도메인 메서드로 출금, 입금하고 거래내역 2건을 저장한다. 계좌에 대해 `save()`를 호출하지 않는다 (변경 감지로 UPDATE가 나가야 한다).
   - 1일 한도: M2-7 규칙(Asia/Seoul 기준 하루 `TRANSFER_OUT` 합계 5,000,000원 이하, 정확히 5,000,000원은 허용)을 `account_transaction`의 합계 조회 1번으로 확인한다. 날짜 경계는 생성자로 받은 `Clock`으로 `[오늘 00:00, 내일 00:00)`을 만든다. 이 미션에서는 동시에 들어온 두 이체가 함께 한도를 넘는 경우를 막지 않는다 (Phase 6 M6-4).
   - `requestId` 멱등성은 Phase 4 웹 계층의 `IdempotencyStore`가 계속 담당하고 이 엔진은 하지 않는다 (DB 멱등성은 Phase 6 M6-3). 계좌 락도 걸지 않는다 (M5-8, M5-9에서 다룬다).
   - `balanceOf`, `historyOf`는 DB에서 읽는다. `historyOf`는 `occurred_at`, `id` 오름차순이다.
6. **Phase 4 API 연결.** Phase 2의 메모리 `TransferEngine` 구현 빈에는 `@Profile("memory")`를 붙여 기본 실행에서 빼고, `JpaTransferEngine`이 유일한 `TransferEngine` 빈이 되게 한다 (M3-2의 "`TransferEngine` 빈은 정확히 1개" 테스트 유지). `BankService`의 계좌 개설, 입금, 출금, 조회와 거래내역 기록, 조회(M4-5 커서 조회 포함)는 내부 `Map`, `Ledger` 대신 `AccountRepository`와 `SpringDataAccountTransactionRepository`를 쓰게 바꾼다. 컨트롤러 코드는 바꾸지 않는다.
7. **측정 도구.** 테스트에서 `EntityManagerFactory`를 `SessionFactory`로 `unwrap`해 `Statistics`를 얻는다. 각 시나리오의 "실행" 직전에 `statistics.clear()`를 호출한다. 준비 데이터는 별도 트랜잭션(예: `TransactionTemplate`)에서 커밋해 두어, 측정하는 트랜잭션의 영속성 컨텍스트가 비어 있는 상태에서 시작한다.

## 테스트 시나리오
"SQL 수"는 `Statistics.getPrepareStatementCount()`, "UPDATE 수"는 `getEntityUpdateCount()`, "INSERT 수"는 `getEntityInsertCount()`이다. 계좌 A = `110-0000-0001`(잔액 100,000), B = `110-0000-0002`(잔액 0).

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | Flyway V1 적용된 컨테이너 | 컨텍스트 시작 (`ddl-auto: validate`) | 시작 성공. 실패했다면 에러 메시지와 고친 매핑을 `docs/m5-4-mapping.md`에 기록 |
| 2 | 빈 테이블, 트랜잭션 시작 | `save(Account.open(A, ...))` 직후 (커밋 전) SQL 수 확인 | SQL 수 1 (INSERT가 커밋 전에 이미 실행됨: `IDENTITY` 키를 얻기 위해) |
| 3 | A 저장됨, 새 트랜잭션 | `findById(id)` 2회 | SQL 수 1, 두 결과가 `==`로 같다 (1차 캐시) |
| 4 | A 저장됨, 새 트랜잭션 | `findByNumber(A)` 2회 | SQL 수 2 (JPQL 조회는 1차 캐시를 거치지 않고 DB에 감), 두 결과는 `==`로 같다 (동일성 보장) |
| 5 | A 저장됨, 새 트랜잭션 | `findByNumber(A)` → 10,000원 출금 → `save` 호출 없이 커밋 | UPDATE 수 1, 커밋 후 DB `balance = 90000.00` |
| 6 | A 저장됨, 새 트랜잭션 | 10,000원 출금 → 10,000원 입금 → 커밋 | UPDATE 수 0, DB `balance = 100000.00` (스냅샷과 같으면 UPDATE 안 함) |
| 7 | A 저장됨, 새 트랜잭션 | `findByNumber(A)` → 10,000원 출금 → (SQL 수 기록) → `findByNumber(A)` → (SQL 수 기록) | 출금 직후 SQL 수 1 (UPDATE 아직 안 나감), 두 번째 조회 직후 SQL 수 3 (조회 전에 UPDATE flush + SELECT). SQL 로그에서 UPDATE가 두 번째 SELECT보다 먼저 찍힌다 |
| 8 | A 저장됨 | 트랜잭션 1에서 `findByNumber(A)` 결과를 변수에 보관 → 트랜잭션 종료 → 그 객체에서 10,000원 출금 → 트랜잭션 2에서 아무 조회나 1회 후 커밋 | DB `balance = 100000.00` (준영속 객체의 변경은 반영되지 않음) |
| 9 | A와 거래내역 1건 저장됨 | 트랜잭션 안에서 거래내역 조회 → 트랜잭션 종료 후 `getAccount().getOwnerName()`(접근자 이름은 Phase 1 기준) | `org.hibernate.LazyInitializationException` |
| 10 | 저장 전 `Account` 객체를 `HashSet`에 추가 | `save` → 커밋 → `set.contains(그 객체)` | `true` (해시코드가 `id`가 아니라 `AccountNumber`에 기반) |
| 11 | A와 거래내역 1건 저장됨. 트랜잭션 1에서 읽은 A(준영속)를 보관 | 트랜잭션 2에서 거래내역 조회 → `getAccount()`로 얻은 객체 `p`에 대해 `Hibernate.isInitialized(p)` → `detachedA.equals(p)` → `p.equals(detachedA)` | `false` → `true` → `true`. `equals`를 `getClass() != o.getClass()` 비교로 바꾸면 두 번째가 `false`가 됨을 확인하고 원래대로 되돌린다 |
| 12 | A = 100,000, B = 0 | `JpaTransferEngine.transfer(A → B, 30,000)` | SQL 수 7, INSERT 수 2, UPDATE 수 2. A = 70000.00, B = 30000.00, 거래 행 2. `TransferResult.fromBalanceAfter()` = 70,000원 |
| 13 | A = 100,000, B = 0 | `transfer(A → B, 100,001)` / `transfer(A → B, 30,000, memo = "가" × 101자)` | `InsufficientBalanceException`, 거래 행 0, 잔액 그대로 / `DataAccessException` 하위 예외(구체 클래스 기록), 에러 코드 1406, 잔액 그대로, 거래 행 0. 두 번째 경우 SQL 로그에 UPDATE가 하나도 없다 (IDENTITY INSERT가 flush 전에 먼저 실패) |
| 14 | A = 10,000,000, B = 0, `Clock` = 2026-03-10 10:00 (Asia/Seoul) | 5,000,000원 이체 → 이어서 1원 이체 | 첫 건 성공, 두 번째 `DailyTransferLimitExceededException`, A = 5000000.00, 거래 행 2 |
| 15 | 14번 직후, `Clock`을 2026-03-11 00:00:00으로 이동 | 1원 이체 | 성공 (날짜가 바뀌어 합계 0부터), A = 4999999.00 |
| 16 | Phase 4 테스트 | `./gradlew test --tests "lab.bank.web.*"` (Testcontainers 설정을 가져다 쓰도록 M5-3에서 고친 상태) | M4-2, M4-4, M4-5의 `@SpringBootTest` API 테스트가 수정 없이 통과 (테스트 데이터 준비 코드만 DB용으로 바꾸는 것은 허용) |

계산식 (12번): SELECT 3(계좌 2개 조회 + 1일 한도 합계 조회 1) + INSERT 2(거래내역, IDENTITY라 즉시 실행) + UPDATE 2(커밋 시 flush) = 7.

## 제약
- `spring.jpa.hibernate.ddl-auto`를 `create`, `create-drop`, `update`로 바꾸지 않는다: 스키마의 원천은 Flyway 하나다.
- 모든 `@ManyToOne`은 `FetchType.LAZY`로 둔다 (JPA 기본값은 `EAGER`). M5-5에서 `EAGER`가 만드는 N+1을 따로 관찰한다.
- 엔티티를 Phase 4 API 응답으로 직접 반환하지 않는다 (Phase 4 규칙). 시나리오 9의 예외가 컨트롤러에서 직렬화 중에 터진다.
- `spring.jpa.open-in-view`는 `false`로 둔다. `true`(Spring Boot 기본값)면 HTTP 요청이 끝날 때까지 영속성 컨텍스트가 열려 있어 시나리오 9가 웹 요청 안에서는 재현되지 않는다.
- `equals`/`hashCode`에 `id`, `balance`, `status`를 쓰지 않는다.

## 힌트
<details>
<summary>힌트 1: validate가 타입 불일치로 실패할 때</summary>

Hibernate 6.2 이후 MySQL에서는 `@Enumerated(EnumType.STRING)` 필드가 MySQL의 `enum(...)` 타입으로 해석되어, `VARCHAR(10)` 컬럼과 `validate`에서 불일치로 보고될 수 있다. 에러 메시지에 `found [varchar ...], but expecting [enum ...]`이 보이면 Hibernate의 `@JdbcTypeCode`와 `org.hibernate.type.SqlTypes` 상수를 찾아본다.
`BigDecimal` 금액은 `@Column(precision = 19, scale = 2)`가 스키마와 같은지 확인한다. DB에서 읽은 `100000.00`(scale 2)과 테스트의 `Money` 기대값이 Phase 1 `Money`의 동등성 규칙으로 같은지도 확인한다. `BigDecimal.equals`는 scale까지 비교한다.
</details>

<details>
<summary>힌트 2: 프록시 객체에서 필드를 직접 읽으면</summary>

지연 로딩 프록시는 엔티티 클래스를 상속한 하위 클래스이고, 프록시 자신의 필드는 초기화되지 않은 기본값(`null`)이다.
`equals` 안에서 상대 객체의 필드에 직접 접근(`other.number`)하는 것과 접근자 메서드(`other.number()` 또는 `other.getNumber()`)를 호출하는 것이 프록시에서 어떻게 다른지 디버거로 확인한다. `instanceof` 패턴 매칭과 `getClass()` 비교의 차이도 같은 관점에서 본다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 이 미션의 시나리오 1~16 테스트가 통과하고, M5-3 테스트도 깨지지 않는다 (`jdbc` 프로파일 테스트는 해당 프로파일로 실행)
- [ ] `./gradlew bootRun` 후 Phase 4의 계좌 개설, 이체 API를 curl로 호출하고, 애플리케이션을 재시작한 뒤 잔액 조회 API가 같은 잔액을 돌려준다
- [ ] `docs/m5-4-mapping.md`에 매핑 방법 선택 이유, 시나리오 1에서 만난 에러(없으면 "없음"), 시나리오 7의 SQL 로그 발췌가 있다
- [ ] `docs/m5-2-measurements.md` 줄 수 표에 JPA 열이 추가되어 있다

## 생각해볼 질문
1. 시나리오 2에서 `IDENTITY` 전략이 쓰기 지연을 깨는 이유는 무엇인가? `SEQUENCE`를 지원하지 않는 MySQL에서 INSERT를 모아 보내려면 어떤 키 생성 방식을 쓸 수 있을까?
2. 시나리오 8처럼 준영속 객체를 고친 코드가 컴파일도 되고 예외도 없이 지나간다. 이런 실수를 코드 리뷰에서 찾으려면 무엇을 보면 되나?
3. 도메인 `Account`에 JPA 애너테이션을 직접 붙이는 방식과, 별도의 `AccountEntity`를 두고 도메인 객체로 변환하는 방식의 장단점을 표로 비교한다. Phase 6에서 `lab.corebank`를 새로 만들 때 어느 쪽을 고를지 근거와 함께 적는다.
