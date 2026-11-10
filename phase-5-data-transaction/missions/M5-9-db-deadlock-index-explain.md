# M5-9 DB 데드락과 인덱스·실행계획

> 가이드 수준: L2 · 예상 시간: 4~6h · 선행: M5-8

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- A→B, B→A 이체로 MySQL 데드락을 mysql CLI와 Spring 테스트 양쪽에서 재현하고, `SHOW ENGINE INNODB STATUS`의 `LATEST DETECTED DEADLOCK` 부분을 트랜잭션별 "가진 락 / 기다린 락" 표로 정리한다.
- 락 순서 고정과 데드락 재시도로 동시 이체 100건(A→B 50, B→A 50)을 데드락 0건으로 통과시키는 테스트를 만든다.
- 같은 `SELECT ... FOR UPDATE`가 인덱스가 없을 때 `data_locks` 102행, 일반 인덱스일 때 4행, 유니크 인덱스일 때 3행의 락을 잡는 것을 보여주고, 인덱스가 없으면 관계없는 계좌의 UPDATE까지 막히는 것을 재현한다.
- 거래내역 10만 행 테이블에서 인덱스 3가지 상태별 `EXPLAIN`의 `type`, `key`, `rows`, `Extra`를 기록표로 비교한다.

## 배경
Phase 2 M2-3에서 두 스레드가 락 두 개를 반대 순서로 잡으면 영원히 멈추는 것을 재현했다. DB에서는 InnoDB가 데드락을 감지해 한쪽 트랜잭션을 통째로 롤백한다. 멈추지는 않지만, 롤백된 이체 요청은 사용자에게 실패로 돌아간다. 이체가 몰리는 월급날 오전에 데드락 실패가 쌓이면 고객 민원으로 이어진다.
인덱스도 동시성 문제다. M5-7에서 본 것처럼 InnoDB는 행이 아니라 **탐색한 인덱스 레코드**에 락을 건다. `WHERE`의 컬럼에 인덱스가 없으면 한 계좌를 잠그려던 문장이 테이블의 모든 계좌를 잠근다.
M5-8의 `PessimisticWithdrawService`에서 쓴 `PESSIMISTIC_WRITE` 조회를 이체에 그대로 쓴다. README 6절의 락 표와 에러 코드 표를 먼저 읽는다.

## 요구사항
1. **수동 데드락 실험 (`bank_lab`).** M5-7의 `sql/lab/reset.sh`로 초기화한 뒤 아래 시나리오 1을 세션 A, B로 실행한다. 실행 전에 root 세션에서 `SET GLOBAL innodb_print_all_deadlocks = ON;`을 실행해 모든 데드락이 에러 로그(`docker logs bank-mysql`)에도 남게 한다 (기본값 `OFF`, 컨테이너 재시작 시 원래대로 돌아감).
2. **데드락 분석표.** `SHOW ENGINE INNODB STATUS\G` 출력에서 `LATEST DETECTED DEADLOCK` 부분을 복사해 `docs/m5-9-deadlock.md`에 붙이고, 아래 표를 채운다.

   | 항목 | 트랜잭션 (1) | 트랜잭션 (2) |
   |---|---|---|
   | 실행 중이던 SQL | | |
   | 가진 락 (index, `lock_mode`, 레코드 기본 키 값) | | |
   | 기다린 락 (index, `lock_mode`, 레코드 기본 키 값) | | |
   | 롤백 대상 (`WE ROLL BACK TRANSACTION`) | | |
3. **`lab.bank.dblock.LockingTransferService`.** `TransferResult transfer(TransferCommand command)`, `@Transactional`. 두 계좌를 M5-8의 `PESSIMISTIC_WRITE` 조회로 잠근 뒤 M5-4 `JpaTransferEngine`과 같은 검증 규칙으로 이체한다. 잠그는 순서를 바꿀 수 있게 두 가지 모드를 둔다 (방법 자유):
   - `REQUEST_ORDER` — 출금 계좌 → 입금 계좌 순서 (데드락 재현용)
   - `NUMBER_ORDER` — 계좌번호 문자열 오름차순
4. **`lab.bank.dblock.DeadlockRetryExecutor`.** 이체를 실행하다 `PessimisticLockingFailureException`이 나고 그 가장 구체적인 원인(`getMostSpecificCause()`)이 MySQL 에러 코드 1213인 `SQLException`이면, 트랜잭션 **바깥에서** 처음부터 다시 실행한다. 최대 시도 3회(첫 시도 포함), 재시도 사이 대기 없음 (이 미션의 규칙). 1213이 아닌 예외(예: 1205 락 대기 시간 초과, 잔액 부족)는 재시도하지 않는다. 데드락 발생 횟수를 테스트에서 읽을 수 있게 노출한다.
5. **인덱스와 락 범위 실험 (`bank_lab`).** 초기화 후 아래 SQL로 계좌 96개를 더 넣어 100개로 만든다 (고객 이름 `고객001`~`고객096`, 잔액 10,000).
   ```sql
   SET SESSION cte_max_recursion_depth = 1000;
   INSERT INTO account (number, owner_name, owner_id, currency, balance, status)
   WITH RECURSIVE seq (n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 96)
   SELECT CONCAT('110-0001-', LPAD(n, 4, '0')), CONCAT('고객', LPAD(n, 3, '0')), CONCAT('user', LPAD(n, 3, '0')), 'KRW', 10000, 'ACTIVE'
   FROM seq;
   ```
   시나리오 6~8을 세 상태(인덱스 없음 / `CREATE INDEX idx_account_owner ON account (owner_name)` / 유니크 인덱스 `uk_account_number` 사용)로 실행한다. 락을 세기 전에 같은 SELECT를 `EXPLAIN`해 `key` 값이 기대한 인덱스(또는 `NULL`)인지 먼저 확인한다.
6. **실행계획 실험 (`bank_lab`).** 아래 SQL로 거래내역 10만 행 테이블 `tx_lab`을 만든다. `CREATE TABLE ... LIKE`는 인덱스는 복사하고 외래 키는 복사하지 않으므로 인덱스를 자유롭게 지우고 만들 수 있다.
   ```sql
   CREATE TABLE tx_lab LIKE account_transaction;
   SET SESSION cte_max_recursion_depth = 100000;
   INSERT INTO tx_lab (transaction_uuid, account_id, type, amount, balance_after, memo, reversal_of, occurred_at)
   WITH RECURSIVE seq (n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM seq WHERE n < 100000)
   SELECT UUID(), MOD(n, 100) + 1, 'DEPOSIT', 1000, 1000, NULL, NULL,
          TIMESTAMP('2026-01-01 09:00:00') + INTERVAL MOD(n DIV 100, 365) DAY
   FROM seq;
   ANALYZE TABLE tx_lab;
   ```
   대상 질의 Q: `SELECT id, amount, occurred_at FROM tx_lab WHERE account_id = 7 AND occurred_at >= '2026-03-01' AND occurred_at < '2026-04-01' ORDER BY occurred_at DESC LIMIT 20;`
   인덱스 상태 3가지: (가) `DROP INDEX idx_tx_account_occurred ON tx_lab;`로 보조 인덱스 없음 (유니크 `uk_tx_uuid`만 남음) / (나) `CREATE INDEX idx_tx_lab_account ON tx_lab (account_id);` / (다) (나)의 인덱스를 지우고 `CREATE INDEX idx_tx_account_occurred ON tx_lab (account_id, occurred_at);`

## 테스트 시나리오
수동 실험(1, 6~9)은 `bank_lab`에서 root 세션으로 실행한다. B 세션은 먼저 `SET SESSION innodb_lock_wait_timeout = 10;`을 실행한다. Spring 테스트(2~5)는 Testcontainers DB에서 A = `110-0000-0001`, B = `110-0000-0002`로 한다.
수동 실험(1, 6~12)의 기대 결과는 `mysql:8.4` 이미지(8.4.13)에서 이 문서의 스키마·데이터로 실행해 확인한 값이다(2026-11-10). 시나리오 1은 3회 실행 모두 세션 B가 롤백됐다. Spring 테스트 2의 예외는 JdbcTemplate·JPA 모두 `CannotAcquireLockException`(Spring Boot 4.1.2)이었다.

### 시나리오 1: 수동 데드락
| 시각 | 세션 A | 세션 B | 기대 결과 |
|---|---|---|---|
| T1 | `START TRANSACTION;` `UPDATE account SET balance = balance - 1000 WHERE id = 1;` | | 1 row affected |
| T2 | | `START TRANSACTION;` `UPDATE account SET balance = balance - 1000 WHERE id = 2;` | 1 row affected |
| T3 | `UPDATE account SET balance = balance + 1000 WHERE id = 2;` | | A: 대기 |
| T4 | | `UPDATE account SET balance = balance + 1000 WHERE id = 1;` | 둘 중 한 세션에 `ERROR 1213 (40001): Deadlock found when trying to get lock; try restarting transaction`, 다른 세션의 대기 중이던 UPDATE는 즉시 완료 |
| T5 | 살아남은 세션에서 `COMMIT;`, 롤백된 세션에서 `SELECT balance FROM account WHERE id IN (1, 2);` | | B가 롤백됐다면 id 1 = 149000.00, id 2 = 31000.00 / A가 롤백됐다면 id 1 = 151000.00, id 2 = 29000.00. 어느 경우든 합계 180000.00. 롤백된 세션의 T1(또는 T2) UPDATE도 취소됨 (데드락은 트랜잭션 전체 롤백) |

### Spring 테스트
| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 2 | A = 1,000,000, B = 1,000,000 | 스레드 2개, 각자 `TransactionTemplate` 안에서 스레드 1은 A 잠금 → 래치 대기 → B 잠금, 스레드 2는 B 잠금 → 래치 대기 → A 잠금 (`PESSIMISTIC_WRITE` 조회만 사용, 래치 2개로 "둘 다 첫 락을 잡은 뒤" 두 번째 락 요청) | 정확히 1개 스레드가 `PessimisticLockingFailureException` 하위 예외(구체 클래스 기록), `getMostSpecificCause()`의 에러 코드 1213. 다른 스레드는 정상 커밋 |
| 3 | A = 1,000,000, B = 1,000,000 | `REQUEST_ORDER`, 재시도 없이 A→B 1,000원 50건 + B→A 1,000원 50건 동시 (32 스레드) | 성공 + 데드락 실패 = 100, 데드락 이외 예외 0, A + B = 2000000.00, A = 1,000,000 − 1,000 × (A→B 성공) + 1,000 × (B→A 성공). 5회 실행해 회차별 데드락 실패 수 기록 |
| 4 | 3번과 같음 | `REQUEST_ORDER` + `DeadlockRetryExecutor`(최대 3회) | 성공 + 재시도 소진 = 100, A + B = 2000000.00, 3번의 등식 성립. 회차별 데드락 발생 수·재시도 소진 수 기록 |
| 5 | 3번과 같음 | `NUMBER_ORDER` + `DeadlockRetryExecutor`(최대 3회) | 성공 100, **데드락 발생 0**, A = 1000000.00, B = 1000000.00, `TRANSFER_OUT` 행 100, `TRANSFER_IN` 행 100 |

계산식 (5번): A = 1,000,000 − 1,000 × 50 + 1,000 × 50 = 1,000,000. B도 같다.

### 인덱스와 락 범위 (계좌 100개, REPEATABLE READ)
세션 A: `START TRANSACTION;` 후 아래 SELECT. 세션 C: `SELECT COUNT(*) FROM performance_schema.data_locks WHERE OBJECT_SCHEMA = 'bank_lab';`와 README 6절 조회. 세션 B: `UPDATE account SET balance = balance + 1 WHERE id = 4;` (예금주 `최네오`, A가 찾는 계좌와 다른 계좌). 각 상태가 끝나면 A, B 모두 `ROLLBACK;`.

| # | 상태 | 세션 A의 SELECT | 기대 결과(Then) |
|---|---|---|---|
| 6 | `owner_name` 인덱스 없음 | `SELECT id FROM account WHERE owner_name = '이두리' FOR UPDATE;` | `EXPLAIN` `type = ALL`, `key = NULL`. 결과 1행(id 2). `data_locks` **102행** = `TABLE`/`IX` 1 + `PRIMARY`/`X` 레코드 100 + `supremum pseudo-record` 1. 세션 B: **대기**, 10초 후 `ERROR 1205` |
| 7 | `idx_account_owner` 생성 후 | 6번과 같음 | `EXPLAIN` `type = ref`, `key = idx_account_owner`. `data_locks` **4행**: `TABLE`/`IX`, `idx_account_owner`/`X`/`'이두리', 2`, `PRIMARY`/`X,REC_NOT_GAP`/`2`, `idx_account_owner`/`X,GAP`/`'최네오', 4`. 세션 B: **즉시 성공** |
| 8 | `idx_account_owner` 삭제 후 | `SELECT id FROM account WHERE number = '110-0000-0002' FOR UPDATE;` | `EXPLAIN` `type = const`, `key = uk_account_number`. `data_locks` **3행**: `TABLE`/`IX`, `uk_account_number`/`X,REC_NOT_GAP`/`'110-0000-0002', 2`, `PRIMARY`/`X,REC_NOT_GAP`/`2`. 세션 B: 즉시 성공 |

7번의 `X,GAP`이 `'최네오', 4`에 걸리는 이유: `idx_account_owner`는 `utf8mb4_0900_ai_ci` 정렬 순서로 `고객001`~`고객096`, `김하나`, `박세나`, `이두리`, `최네오` 순이고, `이두리` 다음 레코드가 `최네오`다. 실제 `LOCK_DATA`가 다르면 그대로 기록하고 이유를 찾는다.

### 실행계획 (`tx_lab` 100,000행)
| # | 인덱스 상태 | 실행 | 기대 결과(Then) |
|---|---|---|---|
| 9 | 모든 상태 공통 | Q를 실행 / `SELECT COUNT(*)`로 Q의 `WHERE`만 적용 / `SELECT COUNT(*) FROM tx_lab WHERE account_id = 7` | 20행 / 93 / 1000 |
| 10 | (가) 보조 인덱스 없음 | `EXPLAIN` Q | `type = ALL`, `key = NULL`, `rows` 약 100,000 (통계 추정치, 실제 값 기록), `Extra`에 `Using filesort` 포함 |
| 11 | (나) `(account_id)` | `EXPLAIN` Q | `type = ref`, `key = idx_tx_lab_account`, `rows` 약 1,000, `Extra`에 `Using filesort` 포함 |
| 12 | (다) `(account_id, occurred_at)` | `EXPLAIN` Q | `type = range`, `key = idx_tx_account_occurred`, `rows` 약 93, `Extra`에 `Using filesort` **없음** (`Backward index scan` 등 실제 값 기록) |

계산식 (9번): `account_id = 7`인 행은 n = 6, 106, …, 99,906 → 1,000행이고 날짜 인덱스는 k = 0~999에 대해 k mod 365. 3월(1월 1일 기준 59~89일째)에 해당하는 k는 59~89, 424~454, 789~819로 31 × 3 = 93.

기록표 `docs/m5-9-explain.md` 열: 상태, `type`, `possible_keys`, `key`, `key_len`, `rows`, `filtered`, `Extra`, Q 실행 시간 중앙값(ms). 실행 시간 측정 규칙: Q를 워밍업 3회 후 5회 실행해 중앙값을 기록하고, 표 위에 MySQL 버전, CPU 코어 수, OS, Docker에 할당한 메모리를 적는다.

## 제약
- 데드락 재시도를 `@Transactional` 메서드 안에서 하지 않는다. 1213을 받은 트랜잭션은 이미 롤백됐으므로 같은 트랜잭션에서 다음 SQL을 실행해도 이체가 완성되지 않는다.
- 시나리오 3, 4에서 데드락 발생 수를 특정 숫자로 assert하지 않는다 (실행마다 다르다). 불변식(합계, 등식)만 assert하고 발생 수는 기록한다. 시나리오 2와 5는 결정적이므로 숫자를 assert한다.
- 시나리오 6~8을 하나의 트랜잭션에서 연달아 하지 않는다. 앞 상태의 락이 남아 행 수가 합쳐진다.
- 데드락을 줄이려고 `innodb_deadlock_detect`를 끄지 않는다. 끄면 데드락이 `innodb_lock_wait_timeout`(50초) 대기로 바뀐다.

## 힌트
<details>
<summary>힌트 1: 데드락 로그 읽는 순서</summary>

`LATEST DETECTED DEADLOCK` 아래는 `*** (1) TRANSACTION:` → `*** (1) HOLDS THE LOCK(S):` → `*** (1) WAITING FOR THIS LOCK TO BE GRANTED:` → `*** (2) ...` → `*** WE ROLL BACK TRANSACTION (n)` 순서다. 각 락 줄에서 `index PRIMARY of table`, `lock_mode X locks rec but not gap`, 그리고 그 아래 `0: len 8; hex ...`로 시작하는 레코드 덤프의 첫 필드(기본 키 값)를 찾는다.
MySQL 8.4 Reference Manual 17.7.5.1 "An InnoDB Deadlock Example"의 출력과 나란히 놓고 비교한다.
</details>

<details>
<summary>힌트 2: 락 순서를 정하는 기준</summary>

Phase 2 M2-3에서 쓴 락 순서 규칙(계좌번호 비교)을 DB 락에도 그대로 쓸 수 있는지 생각한다. 두 계좌를 한 문장(`WHERE number IN (?, ?) ... FOR UPDATE`)으로 잠그면 InnoDB가 어떤 순서로 레코드를 잠그는지, `EXPLAIN`의 `key`와 `type`이 무엇인지 확인해 본다. 한 문장으로 잠그는 방식과 두 번 나눠 잠그는 방식 중 어느 쪽을 택할지 근거를 남긴다.
</details>

## 완료 기준
- [ ] `docs/m5-9-deadlock.md`에 시나리오 1의 `LATEST DETECTED DEADLOCK` 원문, 요구사항 2의 분석표, `docker logs bank-mysql`에서 찾은 같은 데드락 로그 첫 5줄이 있다
- [ ] `./gradlew test --tests "lab.bank.dblock.*Deadlock*"`(테스트 이름은 자유, 실행 명령을 문서에 적는다)에서 시나리오 2~5 테스트가 통과하고, 시나리오 5를 `@RepeatedTest(20)`으로 돌려도 데드락 발생 0이다
- [ ] `docs/m5-9-deadlock.md`에 시나리오 3, 4의 회차별 데드락 수와 시나리오 6~8의 `data_locks` 조회 원문이 있다
- [ ] `docs/m5-9-explain.md`에 시나리오 10~12의 `EXPLAIN` 원문과 기록표가 있다

## 생각해볼 질문
1. 시나리오 6에서 인덱스가 없을 때 `UPDATE ... WHERE owner_name = ?`를 실행하면 운영 중인 다른 계좌의 출금이 모두 대기한다. 운영 DB에 이런 쿼리가 섞여 들어오는 것을 배포 전에 막으려면 무엇을 검사하겠는가 (예: CI에서 `EXPLAIN` 결과의 `type = ALL` 검사)?
2. 데드락 재시도 최대 3회가 모두 실패한 요청은 클라이언트에게 어떤 응답을 줘야 하나? 클라이언트가 같은 이체를 다시 보내면 중복 출금 위험은 없는가? Phase 4의 `Idempotency-Key`와 Phase 6 M6-3의 `idempotency_key` 유니크 제약이 이 상황에서 각각 무엇을 막아 주는지 비교한다.
3. 시나리오 12의 복합 인덱스 `(account_id, occurred_at)`는 Phase 4 M4-5의 커서 페이지네이션 쿼리에도 맞는가? 커서 조건(`occurred_at < ? OR (occurred_at = ? AND id < ?)`)까지 인덱스로 처리하려면 인덱스 컬럼을 어떻게 바꿔야 할지 `EXPLAIN`으로 확인해 본다.
