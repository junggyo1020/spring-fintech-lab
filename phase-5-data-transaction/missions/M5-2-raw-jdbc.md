# M5-2 JDBC 맨손 구현과 수동 트랜잭션

> 가이드 수준: L2 · 예상 시간: 4~6h · 선행: M5-1

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- `Connection`, `PreparedStatement`, `ResultSet`과 try-with-resources만으로 `JdbcAccountRepository`를 구현하고, 테스트 12개로 저장·조회·이체를 검증한다.
- `setAutoCommit(false)` / `commit()` / `rollback()`으로 이체 하나를 한 트랜잭션으로 묶고, 네 번째 SQL 문이 실패해도 앞선 UPDATE 2개가 되돌려짐을 테스트로 보여준다.
- 트랜잭션 없이 같은 이체를 실행하면 잔액과 거래내역이 어긋나는 것을 테스트로 재현한다.
- `DriverManager`와 HikariCP 커넥션 풀의 조회 100회 소요 시간, 그리고 반복 코드 줄 수를 표로 기록한다 (M5-3과 비교할 기준값).

## 배경
Spring의 `JdbcTemplate`과 `@Transactional`은 이 미션에서 손으로 쓰는 코드를 대신 써 준다. 대신 써 주는 코드를 한 번도 써 보지 않으면 `@Transactional`이 무엇을 숨기는지 설명할 수 없고, M5-6의 함정에서 왜 롤백이 안 됐는지 찾지 못한다.
이체는 SQL 4문장(출금 UPDATE, 입금 UPDATE, 거래내역 INSERT 2개)이다. 이 중 하나만 실패해도 나머지가 커밋되면 "돈이 빠져나갔는데 입금은 안 된" 계좌가 생긴다.
M5-1에서 mysql CLI로 쳤던 `START TRANSACTION` / `ROLLBACK`을 이번에는 Java 코드로 한다.

## 요구사항
1. **저장소 인터페이스 (신규).** Phase 1~4에서는 `BankService`와 `TransferEngine`이 계좌를 내부 `Map`에 들고 있었고 저장소 인터페이스가 없었다. 이 미션에서 `lab.bank.account.AccountRepository`를 새로 만든다 (시그니처는 그대로 쓴다). Phase 4 API는 M5-4까지 기존 메모리 구현을 계속 쓴다.
   ```java
   public interface AccountRepository {
       Account save(Account account);                         // id == null 이면 INSERT, 아니면 UPDATE
       Optional<Account> findByNumber(AccountNumber number);
       List<Account> findAll();                               // number 오름차순
   }
   ```
2. **`Account`에 DB 식별자 추가.** `lab.bank.account.Account`에 `Long id` 필드를 추가한다. `Account.open(...)`(M4-7에서 `ownerId`를 받도록 바뀐 형태)으로 만든 계좌는 `id == null`이다. 저장 컬럼은 M5-1의 `account` 테이블 전체(`owner_id` 포함)다. DB에서 읽은 값으로 계좌를 다시 만드는 정적 팩토리(이름 자유, 예: `restore`)를 추가하되, 이 팩토리는 잔액·상태 검증 규칙(Phase 1)을 우회하지 않는다. 동등성은 Phase 1 규칙(`AccountNumber`만 비교)을 유지한다.
3. **`lab.bank.persistence.jdbc.JdbcAccountRepository implements AccountRepository`.**
   - 생성자는 `javax.sql.DataSource` 하나만 받는다. Spring 빈으로 등록하지 않고 테스트에서 직접 `new` 한다 (빈은 M5-3의 JdbcTemplate 버전부터).
   - `save`: `id == null`이면 INSERT 후 `Statement.RETURN_GENERATED_KEYS`로 받은 키를 `id`에 넣어 반환한다. `id != null`이면 `balance`, `status`만 UPDATE한다. UPDATE 결과가 0행이면 `AccountNotFoundException`.
   - `findByNumber`: 없으면 `Optional.empty()`. `null` 인자는 `NullPointerException` (Phase 1 관례).
   - 인터페이스 메서드는 호출마다 `DataSource`에서 커넥션을 얻고 try-with-resources로 닫는다 (autocommit 모드).
   - 이체에서 같은 커넥션을 써야 하는 메서드는 `Connection`을 첫 번째 파라미터로 받는 오버로드를 따로 둔다 (예: 계좌 조회, 잔액 UPDATE, 거래내역 INSERT). 이 오버로드는 커넥션을 닫지 않는다.
4. **`SQLException` 처리.** checked 예외인 `SQLException`은 이 미션에서 새로 만드는 `lab.bank.persistence.jdbc.JdbcAccessException extends RuntimeException`으로 감싸고 원인(`cause`)을 보존한다. 도메인 예외(`BankException` 하위)는 감싸지 않고 그대로 던진다.
5. **`lab.bank.persistence.jdbc.JdbcTransferService`.** `TransferResult transfer(TransferCommand command)` (Phase 2 `TransferCommand`, `TransferResult` 재사용).
   - 실행 순서: 커넥션 획득 → `setAutoCommit(false)` → 두 계좌 조회 → 도메인 메서드로 출금·입금(Phase 1~2 규칙 그대로) → 잔액 UPDATE 2개 → `TRANSFER_OUT`, `TRANSFER_IN` 거래내역 INSERT 2개 → `commit()`.
   - 어떤 예외든 발생하면 `rollback()` 후 원래 예외를 다시 던진다. `rollback()` 자체가 실패하면 그 예외를 원래 예외의 `addSuppressed`로 붙인다.
   - `finally`에서 `setAutoCommit(true)`로 되돌린 뒤 커넥션을 닫는다.
   - 같은 계좌 이체(`SameAccountTransferException`), 금액 0 이하(`InvalidAmountException`)는 M2-7과 같은 순서로 **커넥션을 얻기 전에** 검증한다. 검증 순서(상태 → 통화 → 잔액)도 M2-7을 따른다. 1일 한도와 `requestId` 멱등성은 이 미션에서 다루지 않는다 (M5-4).
   - 거래내역의 `memo`는 `TransferCommand`의 memo를 그대로 쓴다. 도메인에서 memo 길이를 검증하지 않는다 (시나리오 9에서 DB 에러를 일으키는 데 쓴다).
6. **트랜잭션 없는 버전.** 테스트 코드 안에 `transfer`와 같은 순서로 SQL을 실행하되 `setAutoCommit(false)`를 하지 않는 메서드를 하나 둔다 (프로덕션 코드에는 두지 않는다). 시나리오 10에서만 쓴다.
7. **설정.** `application.yml`의 `spring.datasource`를 README대로 채운다. 테스트는 `bank-mysql` 컨테이너의 `bank` DB에 M5-1의 `01_schema.sql`을 실행한 상태를 전제로 하고, `@BeforeEach`에서 `account_transaction`, `account` 순서로 `DELETE` 한다. (M5-3에서 Testcontainers로 옮긴다.)

## 테스트 시나리오
계좌 A = `110-0000-0001`, B = `110-0000-0002`, 통화 KRW. "거래 행"은 `SELECT COUNT(*) FROM account_transaction` 값이다.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 빈 테이블 | `save(A 계좌)` — `Account.open`으로 만든 예금주 김하나, 소유자 `kim`, KRW 계좌 | 반환 계좌의 `id`가 `null`이 아님, `account` 1행, `balance = 0.00`, `status = 'ACTIVE'` |
| 2 | 1번 계좌 저장됨 | `findByNumber(A)` | 값이 있고 `number`, `ownerName`, `ownerId`, `balance`(0원), `status`가 저장한 값과 같다 |
| 3 | 빈 테이블 | `findByNumber(A)` / `findByNumber(null)` | `Optional.empty()` / `NullPointerException` |
| 4 | A 저장 후 10,000원 입금한 객체 | `save(그 객체)` | `UPDATE` 1행, DB의 `balance = 10000.00`, `account` 행 수 1 유지 |
| 5 | `id = 999`인 계좌 객체 (DB에 없음) | `save` | `AccountNotFoundException` |
| 6 | A = 100,000, B = 0 | `transfer(A → B, 30,000, "월세")` | A = 70000.00, B = 30000.00, 거래 행 2 (`TRANSFER_OUT` balance_after 70000.00, `TRANSFER_IN` balance_after 30000.00), A + B = 100000.00 |
| 7 | A = 100,000, B = 0 | `transfer(A → B, 100,001)` | `InsufficientBalanceException`, A = 100000.00, B = 0.00, 거래 행 0 |
| 8 | A = 100,000, B = 0 | `transfer` 금액 0 / −1 / A → A 30,000 | 0과 −1은 `InvalidAmountException`, A → A는 `SameAccountTransferException`. 세 경우 모두 잔액·거래 행 변화 없음 |
| 9 | A = 100,000, B = 0 | `transfer(A → B, 30,000, memo = "가" × 101자)` | `JdbcAccessException`, `getCause()`가 `SQLException`이고 `getErrorCode() == 1406`. A = 100000.00, B = 0.00, 거래 행 0 (이미 실행된 UPDATE 2개가 롤백됨) |
| 10 | A = 100,000, B = 0 | 요구사항 6의 트랜잭션 없는 버전으로 9번과 같은 입력 | 예외 발생, **A = 70000.00, B = 30000.00, 거래 행 0** (잔액은 바뀌었는데 거래내역이 없음 = 원장 불일치) |
| 11 | A = 100,000, B = `FROZEN` 상태 | `transfer(A → B, 30,000)` | `AccountNotActiveException`, A = 100000.00, 거래 행 0 |
| 12 | A = 100,000, B 없음 | `transfer(A → B, 30,000)` | `AccountNotFoundException`, A = 100000.00, 거래 행 0 |

### 측정 1: 커넥션 획득 방식별 조회 100회
같은 계좌를 `findByNumber`로 100회 연속 조회한다. 방식은 두 가지다.
- (가) 호출마다 `DriverManager.getConnection(url, user, password)`로 새 커넥션을 열고 닫는 `DataSource` (Spring의 `DriverManagerDataSource`를 써도 된다)
- (나) `HikariDataSource` (`maximumPoolSize = 10`)

측정 규칙: 100회 조회를 1회 실행으로 보고 워밍업 3회 후 5회 측정, 중앙값을 기록한다. 표 위에 JDK 버전, CPU 코어 수, OS, MySQL 버전(`SELECT VERSION()`)을 적는다.

| 방식 | 100회 소요 시간 중앙값(ms) | 1회 평균(ms) | 5회 측정값(ms) |
|---|---|---|---|
| DriverManager | | | |
| HikariCP | | | |

### 측정 2: 반복 코드 줄 수 (M5-3에서 같은 표에 열을 추가한다)

| 항목 | JDBC (M5-2) |
|---|---|
| `JdbcTransferService.transfer` 흐름 전체 줄 수 (빈 줄·주석·import 제외, 호출하는 저장소 오버로드 포함) | |
| try 블록 개수 | |
| `SQLException`을 잡는 catch 개수 | |
| `Connection`을 파라미터로 받는 메서드 개수 | |
| `ResultSet` → `Account` 변환 코드 위치 개수 (같은 변환을 몇 군데에 썼는가) | |

## 제약
- `JdbcTemplate`, `@Transactional`, `TransactionTemplate`, JPA 사용 금지 — 이 미션은 그것들이 대신하는 코드를 직접 쓰는 것이 목적이다.
- SQL에 값을 문자열 연결(`"... WHERE number = '" + number + "'"`)로 넣지 않는다. 항상 `PreparedStatement`의 `?` 바인딩을 쓴다 — SQL 인젝션, 그리고 따옴표가 들어간 예금주 이름(`O'Brien`)에서 문법 오류가 난다.
- 금액은 `ResultSet.getBigDecimal` / `PreparedStatement.setBigDecimal`로만 주고받는다. `getDouble` 금지.
- `Connection`, `PreparedStatement`, `ResultSet`은 모두 try-with-resources로 닫는다. 이체용 오버로드에 넘어온 `Connection`만 예외다.
- 테스트끼리 데이터를 공유하지 않는다. 테스트 실행 순서를 바꿔도(`@TestMethodOrder` 없이) 모두 통과해야 한다.

## 힌트
<details>
<summary>힌트 1: rollback과 원래 예외</summary>

`catch` 블록 안에서 `rollback()`을 부르고 원래 예외를 다시 던질 때, `rollback()`도 `SQLException`을 던질 수 있다. 원래 예외를 잃어버리면 장애 원인을 찾을 수 없다.
`Throwable.addSuppressed` Javadoc을 읽고, try-with-resources가 `close()` 예외를 어떻게 suppressed로 붙이는지와 비교한다.
도메인 예외(`InsufficientBalanceException`)도 rollback 대상인지, rollback 후 감싸지 않고 그대로 던지는지 확인한다.
</details>

<details>
<summary>힌트 2: 풀이 autocommit을 되돌려 주는가</summary>

HikariCP는 커넥션을 풀에 돌려받을 때 `autoCommit`, 격리 수준, `readOnly`가 바뀌어 있으면 원래 값으로 되돌린다. 그래도 `finally`에서 직접 `setAutoCommit(true)`를 하라고 요구하는 이유를 (가) 방식(`DriverManager`)과 Phase 6 이후 다른 풀을 쓸 가능성으로 설명해 본다.
HikariCP README의 "autoCommit" 설정 항목과 "Statement Cache" 절을 읽는다.
</details>

## 완료 기준
- [ ] `bank-mysql` 컨테이너가 켜진 상태에서 `./gradlew test --tests "lab.bank.persistence.jdbc.*"`가 시나리오 1~12 테스트 12개(이상)를 통과한다
- [ ] 테스트 클래스를 두 번 연속 실행해도 통과한다 (테스트 간 데이터 공유 없음)
- [ ] `docs/m5-2-measurements.md`에 측정 1 표(환경 정보 포함)와 측정 2 표가 채워져 있다
- [ ] `docs/m5-2-measurements.md`에 시나리오 10이 왜 원장 불일치인지 M5-1 질의 6의 결과(`balance` vs `ledger_balance`)로 2~3줄 설명했다

## 생각해볼 질문
1. 이체용 오버로드에 `Connection`을 파라미터로 넘겨야 했던 이유는 무엇인가? 저장소 메서드가 10개, 서비스가 5개로 늘면 이 방식에서 어떤 실수가 생길 수 있나? Spring은 이 문제를 어디에 커넥션을 보관해서 해결할까? (README 4절과 비교)
2. 측정 1에서 두 방식의 차이는 어디서 오는가? TCP 연결, TLS 핸드셰이크, MySQL 인증 중 무엇이 매번 반복되는지 적어 본다.
3. 시나리오 10처럼 거래내역 없이 잔액만 바뀐 계좌를 운영 중에 발견했다면, 어떻게 찾아내고 어떻게 바로잡아야 할까? Phase 6 M6-6(일 마감과 대사)에서 이 문제를 배치 작업으로 다룬다.
