# M5-8 DB 동시성 제어 3종 비교

> 가이드 수준: L2, 예상 시간: 6~8h, 선행: M5-6

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- `@Transactional`만 붙인 출금 서비스에 100건 동시 출금을 보내 lost update(최종 잔액 > 0, 거래 행 100개)를 재현한다.
- 같은 100건을 비관적 락(`SELECT ... FOR UPDATE`), 낙관적 락(`@Version` + 재시도), 조건부 UPDATE로 각각 통과시키고 불변식 3개(잔액 = 초기 − 성공 × 금액, 거래 행 = 성공 수, 잔액 ≥ 0)를 테스트로 검증한다.
- 잔액보다 많은 출금 요청(100,000원 계좌에 3,000원 × 50건)에서 세 방식 모두 성공 33건, 잔액 부족 17건, 최종 잔액 1,000원이 되는 것을 보여준다.
- 세 방식의 처리량, 실패 수, 재시도 수를 같은 측정 규칙으로 재서 비교표를 만들고, 방식별 선택 기준을 표 아래에 적는다.

## 배경
Phase 2 M2-1에서 두 스레드가 같은 잔액을 읽고 각자 빼서 덮어쓰면 출금 하나가 사라지는 것을 메모리에서 재현했다. 서버가 여러 대이고 잔액이 DB에 있으면 `synchronized`로는 막을 수 없다. 서버 A의 스레드와 서버 B의 스레드는 같은 JVM의 락을 공유하지 않기 때문이다.
M5-7 실험 6에서 MySQL REPEATABLE READ도 이 문제를 막지 않는다는 것을 확인했다. 이 미션은 그 문제를 애플리케이션 코드로 재현하고, DB가 제공하는 세 가지 도구로 해결한 뒤 비용을 측정한다.
M5-6에서 확인한 "트랜잭션 경계 = 커넥션 점유 구간"이 측정 결과에 그대로 나타난다.

## 요구사항
1. **스키마 변경.** `src/main/resources/db/migration/V2__add_account_version.sql`로 `account`에 `version BIGINT NOT NULL DEFAULT 0` 컬럼을 추가한다. V1은 수정하지 않는다.
2. **핵심 인터페이스** (`lab.bank.dblock`: Phase 2의 `lab.bank.concurrency`와 섞지 않는다).
   ```java
   public interface WithdrawService {
       void withdraw(AccountNumber number, Money amount);   // 성공 시 반환, 실패 시 예외
   }
   ```
   모든 구현은 출금 1건마다 `account_transaction`에 `WITHDRAWAL` 행 1개를 같은 트랜잭션에서 INSERT한다. 잔액 부족은 `InsufficientBalanceException`(Phase 1), 금액 0 이하는 `InvalidAmountException`, 없는 계좌는 `AccountNotFoundException`이다.
3. **구현 4개.** 모두 `WithdrawService`를 구현하는 빈이다. 이름은 아래를 쓴다.
   - `NaiveWithdrawService`: `@Transactional` 안에서 `JdbcTemplate`으로 `SELECT balance ... WHERE number = ?` → 애플리케이션에서 잔액 확인, 차감 계산 → `UPDATE account SET balance = ? WHERE number = ?`(계산된 값). 락도 version 비교도 없음 (lost update 재현용). JPA 변경 감지를 쓰지 않는 이유: 아래 `@Version`을 붙이면 JPA 버전은 덮어쓰기 대신 충돌 예외를 내서 lost update가 재현되지 않는다
   - `PessimisticWithdrawService`: `@Lock(LockModeType.PESSIMISTIC_WRITE)`가 붙은 리포지토리 조회 메서드로 계좌를 읽는다 (실행 SQL에 `for update`가 붙는지 로그로 확인)
   - `OptimisticWithdrawService`: `Account`의 `version` 필드에 `@Version`. 충돌(`OptimisticLockingFailureException` 하위 예외)이 나면 **새 트랜잭션으로** 처음부터 다시 실행한다. 최대 시도 횟수(첫 시도 포함)는 생성자나 설정으로 받는다. 최대 시도 후에도 충돌이면 이 미션에서 새로 만드는 `OptimisticRetryExhaustedException`을 던진다. 재시도 사이 대기는 없다 (이 미션의 규칙). 누적 재시도 횟수를 테스트에서 읽을 수 있게 노출한다
   - `AtomicUpdateWithdrawService`: `UPDATE account SET balance = balance - ? WHERE number = ? AND balance >= ?`를 실행하고 수정된 행 수가 0이면 잔액 부족(계좌가 없는 경우와 구분해야 한다). 거래내역의 `balance_after`는 UPDATE 직후 같은 트랜잭션에서 다시 읽은 잔액으로 채운다
4. **동시 실행 테스트 틀.** Phase 2 README 5절의 `CountDownLatch` 틀을 쓴다. `ExecutorService`는 고정 32 스레드, HikariCP `maximum-pool-size`는 기본값 10. 각 작업의 결과를 성공 / `InsufficientBalanceException` / `OptimisticRetryExhaustedException` / 기타 예외로 분류해 센다. 기타 예외가 1건이라도 있으면 테스트 실패다.
5. **데이터 준비와 정리.** 계좌는 테스트 시작 전에 별도 트랜잭션으로 커밋해 둔다. 테스트 메서드, 클래스에 `@Transactional`을 붙이지 않는다 (작업 스레드는 테스트 스레드의 트랜잭션을 공유하지 않는다: README 4절). `@AfterEach`에서 두 테이블을 비운다.

## 테스트 시나리오
"불변식"은 (1) 최종 잔액 = 초기 잔액 − 출금액 × 성공 수, (2) `WITHDRAWAL` 거래 행 수 = 성공 수, (3) 최종 잔액 ≥ 0 세 가지다.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 잔액 1,000,000 | `NaiveWithdrawService`로 10,000원 × 100건 동시 | 100건 모두 예외 없이 성공, `WITHDRAWAL` 행 100, **최종 잔액 > 0** (불변식 1 위반). `@RepeatedTest(5)`로 5회 모두 위반이 재현됨. 회차별 최종 잔액을 기록 |
| 2 | 잔액 1,000,000 | `PessimisticWithdrawService`로 10,000원 × 100건 동시 | 성공 100, 잔액 부족 0, 최종 잔액 0.00, 행 100, 불변식 3개 성립 |
| 3 | 잔액 1,000,000 | `OptimisticWithdrawService`(최대 시도 100)로 10,000원 × 100건 동시 | 성공 100, 재시도 소진 0, 최종 잔액 0.00, 행 100, 누적 재시도 수 기록 |
| 4 | 잔액 1,000,000 | `OptimisticWithdrawService`(최대 시도 10)로 10,000원 × 100건 동시 | 성공 + 재시도 소진 = 100, 불변식 3개 성립 (최종 잔액 = 1,000,000 − 10,000 × 성공 수). 성공, 소진, 누적 재시도 수 기록 |
| 5 | 잔액 1,000,000 | `AtomicUpdateWithdrawService`로 10,000원 × 100건 동시 | 성공 100, 최종 잔액 0.00, 행 100, 각 `balance_after` 값이 0~990,000 사이 10,000 단위로 서로 겹치지 않음 |
| 6 | 잔액 100,000 | 비관적 / 낙관적(최대 시도 50) / 조건부 UPDATE 각각 3,000원 × 50건 동시 | 세 방식 모두 성공 33, 잔액 부족 17, 재시도 소진 0, 최종 잔액 1000.00, 행 33 |
| 7 | 잔액 100,000 | `NaiveWithdrawService`로 3,000원 × 50건 동시 | 불변식 1 위반 (최종 잔액 ≠ 100,000 − 3,000 × 성공 수). 성공 수와 최종 잔액 기록 |
| 8 | 잔액 100,000 | 4개 구현 각각에 금액 0 / −1 / 없는 계좌번호로 1건 | `InvalidAmountException` / `InvalidAmountException` / `AccountNotFoundException`, 잔액, 행 수 변화 없음 |
| 9 | 잔액 100,000 | `AtomicUpdateWithdrawService`로 100,000원 1건 → 1원 1건 | 첫 건 성공(잔액 0.00, 경계값 `balance >= ?`의 `=`), 두 번째 `InsufficientBalanceException` |
| 10 | 잔액 100,000 | 조건부 UPDATE에서 `AND balance >= ?`를 잠시 빼고 3,000원 × 50건 동시 | 성공 33, 나머지 17건은 체크 제약 위반(MySQL 3819)으로 실패. Spring 예외 클래스 기록 후 조건을 되돌린다 |

계산식:
- 6번: 100,000 ÷ 3,000 = 33 (나머지 1,000) → 성공 33 × 3,000 = 99,000 → 최종 1,000 / 실패 50 − 33 = 17
- 3번에서 최대 시도 100이면 소진이 0인 이유: 어떤 요청의 충돌 1회는 다른 요청 1건의 커밋이 그 사이에 있었다는 뜻이고, 다른 요청은 99건이라 충돌은 최대 99회다. 6번의 최대 시도 50도 같은 논리(성공 커밋은 최대 33건)로 소진이 0이다

### 측정표 (`docs/m5-8-concurrency-control.md`)
측정 규칙: 시나리오 2~5(1,000,000원, 10,000원 × 100건)를 1회 실행으로 보고, 워밍업 3회 후 5회 측정해 중앙값을 기록한다. 실행마다 계좌를 새로 만든다. 소요 시간은 출발 신호(`start.countDown()`)부터 마지막 작업 종료까지다. 처리량 = 100 ÷ 소요 시간(초). 표 위에 JDK 버전, CPU 코어 수, OS, MySQL 버전, 스레드 풀 크기(32), HikariCP 풀 크기(10)를 적는다.

| 방식 | 성공 | 잔액 부족 | 재시도 소진 | 누적 재시도 | 최종 잔액 | 소요 시간 중앙값(ms) | 처리량(건/s) |
|---|---|---|---|---|---|---|---|
| Naive (`@Transactional`만) | | | | | | | |
| 비관적 락 | | | | | | | |
| 낙관적 락 (최대 10회) | | | | | | | |
| 낙관적 락 (최대 100회) | | | | | | | |
| 조건부 UPDATE | | | | | | | |

표 아래에 다음 세 경우 각각 어떤 방식을 고를지와 근거(측정값 인용)를 적는다: (가) 인기 계좌 하나에 출금이 몰릴 때, (나) 서로 다른 계좌에 출금이 흩어질 때, (다) 잔액 차감 외에 한도 확인, 상태 확인 등 검증 규칙이 3개 이상일 때.

## 제약
- 재시도 루프를 `@Transactional` 메서드 **안**에 두지 않는다. 같은 트랜잭션 안에서 다시 읽으면 영속성 컨텍스트의 1차 캐시와 REPEATABLE READ 스냅샷 때문에 같은 version을 다시 읽는다. 재시도는 트랜잭션 메서드를 가진 다른 빈을 바깥에서 다시 호출하는 구조여야 한다.
- 시나리오 1, 7(lost update)의 기대값으로 특정 잔액 숫자를 assert하지 않는다. 실행마다 달라진다. "불변식 1 위반"만 assert한다.
- `synchronized`, `ReentrantLock` 등 JVM 락으로 해결하지 않는다: 서버 2대에서는 소용없다.
- 조건부 UPDATE를 Spring Data `@Modifying @Query`로 쓰는 경우, 같은 트랜잭션에서 그 계좌 엔티티를 이미 읽어 둔 상태라면 영속성 컨텍스트의 값은 UPDATE 이전 값이다. 다시 읽기 전에 영속성 컨텍스트를 비워야 하는지 확인한다.

## 힌트
<details>
<summary>힌트 1: 시나리오 1이 재현되지 않을 때</summary>

100개 작업이 실제로 동시에 출발하는지 확인한다 (`ready`, `start` 래치). 출금 하나가 너무 빨리 끝나 사실상 순서대로 실행되고 있다면 SQL 로그의 SELECT와 UPDATE가 번갈아 찍히는지 본다.
`NaiveWithdrawService`의 UPDATE 문이 `balance = ?`(계산된 값)인지 SQL 로그에서 확인하고, M5-7 실험 6과 연결해 왜 덮어쓰기가 되는지 설명한다. 같은 흐름을 JPA 변경 감지로 바꿔 보면 `@Version`이 있을 때와 없을 때 결과가 어떻게 달라지는지도 기록한다.
</details>

<details>
<summary>힌트 2: 낙관적 락 충돌 시 나오는 예외</summary>

`@Version` 충돌이 나면 Hibernate는 `UPDATE ... WHERE id = ? AND version = ?`의 수정 행 수가 0인 것을 보고 예외를 던지고, Spring은 이것을 `ObjectOptimisticLockingFailureException`(상위 `OptimisticLockingFailureException`)으로 바꾼다. 이 예외는 커밋 시점(flush)에 나므로, 서비스 메서드 안의 try/catch가 아니라 트랜잭션 프록시 바깥에서 잡힌다.
Spring Data JPA Reference의 "Locking" 절과 Jakarta Persistence 3.2 명세의 "Optimistic Locking" 절을 읽는다.
</details>

## 완료 기준
- [ ] `./gradlew test --tests "lab.bank.dblock.*"`에서 시나리오 1~10 테스트가 통과한다 (1, 7은 "위반 재현"을 assert)
- [ ] 시나리오 2~6을 `@RepeatedTest(20)`으로 돌려 20회 모두 통과한다
- [ ] `docs/m5-8-concurrency-control.md`에 측정표(환경 정보 포함)와 (가)(나)(다) 선택 근거가 있다
- [ ] `docs/m5-8-concurrency-control.md`에 시나리오 1의 회차별 최종 잔액 5개와, 시나리오 10의 예외 클래스가 있다

## 생각해볼 질문
1. 비관적 락에서 100개 요청이 같은 행을 기다리는 동안 HikariCP 커넥션 10개는 어떤 상태인가? 출금 하나가 외부 API 호출 때문에 3초 걸린다면 (M5-6 시나리오 17) 측정표의 비관적 락 처리량은 어떻게 바뀔까?
2. 낙관적 락의 최대 시도 횟수를 10으로 했을 때 소진된 요청은 사용자에게 어떤 응답(HTTP 상태 코드, Phase 4의 `ErrorCode`)으로 돌려줘야 하나? 클라이언트가 자동 재시도해도 안전한가?
3. Phase 6 M6-2에서는 잔액 컬럼 하나를 차감하는 대신 복식부기 분개(`JournalEntry` + `JournalLine` 2행 이상)를 INSERT한다. 같은 계좌에 동시 출금이 몰릴 때, 이 미션의 세 방식 중 어느 것을 분개 구조에 그대로 쓸 수 있고 어느 것은 쓸 수 없는가? 같은 요청이 두 번 들어오는 경우(멱등성)는 이 미션의 세 방식 중 어느 것도 막지 못하는 이유도 적는다.
