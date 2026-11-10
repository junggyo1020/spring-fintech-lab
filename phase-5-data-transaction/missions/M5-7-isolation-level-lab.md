# M5-7 격리 수준 실험실

> 가이드 수준: L2 · 예상 시간: 3~5h · 선행: M5-3

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- mysql CLI 두 세션을 번갈아 실행해 dirty read, non-repeatable read, phantom, lost update를 재현하고, 시각(T1~Tn)별 결과를 기록표로 남긴다.
- MySQL 8.4 REPEATABLE READ에서 일반 `SELECT`(스냅샷)와 `SELECT ... FOR UPDATE`(최신 커밋 값)가 같은 트랜잭션 안에서 서로 다른 값(150,000 / 160,000)을 돌려주는 것을 보여준다.
- 갭 락이 INSERT를 막는 장면을 `performance_schema.data_locks`의 `LOCK_MODE`(`X`, `INSERT_INTENTION`)와 `LOCK_DATA`(`supremum pseudo-record`)로 보여준다.
- 블로킹이 없는 실험 4개를 JDBC 커넥션 두 개로 자동화한 테스트로 만든다.

## 배경
"격리 수준 REPEATABLE READ면 lost update가 안 생긴다"는 말은 MySQL에서 틀렸다. InnoDB의 RR은 일반 `SELECT`에 스냅샷을 보여줄 뿐, 두 트랜잭션이 같은 잔액을 읽고 각자 계산한 값을 쓰는 것은 막지 않는다 (실험 6). 반대로 "RR에서도 phantom이 생긴다"는 교과서 설명은 InnoDB의 일반 `SELECT`에는 맞지 않는다 (실험 4).
이 차이를 모르면 M5-8에서 "왜 `@Transactional`만으로 출금이 깨지는가"를 설명할 수 없다. 표준(ANSI SQL)의 정의가 아니라 **MySQL 8.4 InnoDB가 실제로 하는 일**을 눈으로 확인하는 것이 이 미션의 목적이다.
M5-3에서 만든 Testcontainers 환경으로 자동화 테스트를 만든다. README 5~6절을 먼저 읽는다.

## 요구사항
1. **실험용 DB 준비.** 애플리케이션 DB(`bank`)와 분리된 `bank_lab` DB를 쓴다. M5-1의 `01_schema.sql`, `02_seed.sql`을 그대로 재사용하는 초기화 스크립트 `sql/lab/reset.sh`를 만든다. 실험마다 시작 전에 실행한다.
   ```bash
   docker exec -i bank-mysql mysql -uroot -proot -e "CREATE DATABASE IF NOT EXISTS bank_lab"
   docker exec -i bank-mysql mysql -uroot -proot bank_lab < sql/01_schema.sql
   docker exec -i bank-mysql mysql -uroot -proot bank_lab < sql/02_seed.sql
   ```
   초기 상태: 계좌 id 1 = 150,000, id 2 = 30,000, id 3 = 0, id 4 = 0 (4행).
2. **세션.** 터미널 3개를 연다. A와 B는 실험 세션, C는 락 관찰 세션이다. 모두 `docker exec -it bank-mysql mysql -uroot -proot bank_lab`으로 접속한다. 블로킹이 있는 실험에서는 B에서 먼저 `SET SESSION innodb_lock_wait_timeout = 10;`을 실행해 대기 시간을 50초(기본값)에서 10초로 줄인다.
3. **격리 수준 지정.** 각 실험 표의 첫 줄에 적힌 격리 수준을 `SET SESSION TRANSACTION ISOLATION LEVEL ...`로 A(필요하면 B도)에 지정한다. `SESSION` 없이 `SET TRANSACTION ...`만 쓰면 **다음 트랜잭션 하나에만** 적용된다는 점에 주의한다. 실험 전 `SELECT @@transaction_isolation;`으로 확인한다.
4. **기록표.** `docs/m5-7-isolation-lab.md`에 아래 실험 1~7의 표를 옮기고, "실제 결과" 열을 추가해 화면에 나온 값을 적는다. 기대 결과와 다르면 다른 이유를 표 아래에 적는다.
5. **자동화 테스트 `lab.bank.isolation.IsolationLevelTest`.** 실험 1, 2, 3, 4는 블로킹이 없으므로 한 스레드에서 `DataSource.getConnection()`으로 얻은 커넥션 두 개를 번갈아 사용해 재현한다. 세션 A 커넥션은 `setAutoCommit(false)` + `setTransactionIsolation(...)`, 세션 B 커넥션은 autocommit으로 둔다. Testcontainers DB에 `02_seed.sql`과 같은 계좌 4개를 넣고 시작하며, 계좌는 `number`로 지정한다. JPA, `@Transactional`은 쓰지 않는다.

## 테스트 시나리오
아래 표에서 SQL의 `acc1`은 `account WHERE id = 1`을 줄인 표기다. 실제로는 `SELECT balance FROM account WHERE id = 1;`처럼 친다. 빈칸은 그 시각에 해당 세션이 아무것도 하지 않는다는 뜻이다. 기대 결과는 `mysql:8.4` 이미지(8.4.13)에서 이 문서의 절차대로 두 세션을 실행해 확인한 값이다(2026-11-10). 실험 7은 3회 실행 모두 세션 B가 데드락으로 롤백됐다.

### 실험 1: dirty read (A: READ UNCOMMITTED)
| 시각 | 세션 A | 세션 B | 기대 결과 |
|---|---|---|---|
| T1 | `SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED; START TRANSACTION;` | | |
| T2 | | `START TRANSACTION; UPDATE account SET balance = balance - 100000 WHERE id = 1;` | B: 1 row affected (커밋 안 함) |
| T3 | `SELECT balance` acc1 | | A: **50000.00** (커밋 안 된 값을 읽음) |
| T4 | | `ROLLBACK;` | |
| T5 | `SELECT balance` acc1; `COMMIT;` | | A: 150000.00 |

같은 절차를 A의 격리 수준만 READ COMMITTED로 바꿔 반복하면 T3의 A 결과는 150000.00이다.

### 실험 2: non-repeatable read (A: READ COMMITTED → REPEATABLE READ 비교)
| 시각 | 세션 A | 세션 B | 기대 결과 (RC) | 기대 결과 (RR) |
|---|---|---|---|---|
| T1 | 격리 수준 지정; `START TRANSACTION;` | | | |
| T2 | `SELECT balance` acc1 | | 150000.00 | 150000.00 |
| T3 | | `UPDATE account SET balance = balance + 10000 WHERE id = 1;` (autocommit) | B: 1 row affected | B: 1 row affected |
| T4 | `SELECT balance` acc1 | | **160000.00** | **150000.00** |
| T5 | `COMMIT;` 후 `SELECT balance` acc1 | | 160000.00 | 160000.00 |

### 실험 3: REPEATABLE READ의 스냅샷 읽기 vs 잠금 읽기
| 시각 | 세션 A (RR) | 세션 B | 기대 결과 |
|---|---|---|---|
| T1 | `START TRANSACTION;` | | |
| T2 | `SELECT balance` acc1 | | 150000.00 (이 시점에 스냅샷 생성) |
| T3 | | `UPDATE account SET balance = balance + 10000 WHERE id = 1;` (autocommit) | 1 row affected |
| T4 | `SELECT balance` acc1 | | 150000.00 |
| T5 | `SELECT balance FROM account WHERE id = 1 FOR UPDATE;` | | **160000.00** (잠금 읽기는 최신 커밋 값) |
| T6 | `SELECT balance` acc1 | | **150000.00** (일반 SELECT는 여전히 T2 스냅샷) |
| T7 | `UPDATE account SET balance = balance - 5000 WHERE id = 1;` | | 1 row affected |
| T8 | `SELECT balance` acc1 | | 155000.00 (UPDATE는 최신 값 160,000에서 계산, 자기 변경은 보임) |
| T9 | `COMMIT;` | `SELECT balance` acc1 | B: 155000.00 |

변형 3-1 (스냅샷 생성 시점): 초기화 후 A `START TRANSACTION;` → B `UPDATE ... + 10000` → A `SELECT` → B `UPDATE ... + 10000` → A `SELECT`. A의 두 결과는 **160000.00, 160000.00**이다 (스냅샷은 `START TRANSACTION`이 아니라 첫 SELECT 시점). A의 첫 줄을 `START TRANSACTION WITH CONSISTENT SNAPSHOT;`으로 바꾸면 두 결과는 150000.00, 150000.00이다.

### 실험 4: phantom (조건 `balance >= 100000`, `balance`에는 인덱스 없음)
| 시각 | 세션 A | 세션 B | 기대 결과 (RC) | 기대 결과 (RR) |
|---|---|---|---|---|
| T1 | 격리 수준 지정; `START TRANSACTION;` `SELECT id FROM account WHERE balance >= 100000;` | | 1행 (id 1) | 1행 (id 1) |
| T2 | | `INSERT INTO account (number, owner_name, owner_id, currency, balance, status) VALUES ('110-0000-0005', '정다섯', 'jung', 'KRW', 200000, 'ACTIVE');` | B: 성공 (id 5) | B: 성공 (id 5) |
| T3 | 같은 SELECT | | **2행** (id 1, 5) | **1행** (id 1) |
| T4 | 같은 SELECT에 `FOR UPDATE` 추가 | | 2행 | **2행** (잠금 읽기는 최신 커밋 행을 봄) |
| T5 | `COMMIT;` | | | |

### 실험 5: 갭 락과 INSERT 의도 락
| 시각 | 세션 A | 세션 B | 세션 C | 기대 결과 (RR) | 기대 결과 (RC) |
|---|---|---|---|---|---|
| T1 | 격리 수준 지정; `START TRANSACTION;` `SELECT id FROM account WHERE id > 4 FOR UPDATE;` | | | A: Empty set | A: Empty set |
| T2 | | | `data_locks` 조회 (README 6절 SQL) | 2행: `TABLE`/`IX`/`GRANTED`, `RECORD`/`PRIMARY`/`X`/`GRANTED`/`supremum pseudo-record` | 1행: `TABLE`/`IX`/`GRANTED` |
| T3 | | `INSERT` (실험 4의 T2와 같은 문장) | | B: **대기** | B: 즉시 성공 |
| T4 | | | `data_locks`, `data_lock_waits` 조회 | `data_locks` 4행 — 위 2행 + B의 `TABLE`/`IX`/`GRANTED` + B의 `RECORD`/`PRIMARY`/`LOCK_MODE`에 `INSERT_INTENTION` 포함/`WAITING`/`supremum pseudo-record`. `data_lock_waits` 1행 (요청 = B 트랜잭션, 차단 = A 트랜잭션) | (해당 없음) |
| T5 | (아무것도 안 함) | | | 10초 후 B: `ERROR 1205 (HY000): Lock wait timeout exceeded; try restarting transaction` | |
| T6 | `COMMIT;` | `INSERT` 다시 실행 | | B: 성공 | |

변형 5-1: A의 T1을 `SELECT id FROM account WHERE id = 2 FOR UPDATE;`로 바꾸면 RR에서도 B의 INSERT는 즉시 성공한다. T2의 `data_locks`는 2행(`IX`, `PRIMARY`/`X,REC_NOT_GAP`/`2`)이다.

### 실험 6: REPEATABLE READ에서도 생기는 lost update
| 시각 | 세션 A (RR) | 세션 B (RR) | 세션 C | 기대 결과 |
|---|---|---|---|---|
| T1 | `START TRANSACTION;` `SELECT balance` acc1 | | | A: 150000.00 |
| T2 | | `START TRANSACTION;` `SELECT balance` acc1 | | B: 150000.00 |
| T3 | `UPDATE account SET balance = 147000 WHERE id = 1;` (150,000 − 3,000을 애플리케이션이 계산한 값) | | | 1 row affected |
| T4 | | `UPDATE account SET balance = 145000 WHERE id = 1;` (150,000 − 5,000) | | B: 대기 (A가 레코드 X 락 보유) |
| T5 | `COMMIT;` | | | B의 UPDATE가 끝남: 1 row affected |
| T6 | | `COMMIT;` | `SELECT balance` acc1 | **145000.00** — 8,000원이 출금됐는데 잔액은 5,000원만 줄었다. A의 출금 3,000원이 사라짐 |

변형 6-1 (잠금 읽기로 수정): T1, T2의 SELECT에 `FOR UPDATE`를 붙인다. B의 T2가 대기하고, 이때 C의 `data_locks`는 4행(A: `IX`/`GRANTED`, `PRIMARY`/`X,REC_NOT_GAP`/`1`/`GRANTED`, B: `IX`/`GRANTED`, `PRIMARY`/`X,REC_NOT_GAP`/`1`/`WAITING`)이다. A가 147000으로 UPDATE 후 커밋하면 B의 SELECT가 **147000.00**을 돌려주고, B가 142000으로 UPDATE 후 커밋 → 최종 142000.00.
변형 6-2 (원자적 UPDATE): A `UPDATE account SET balance = balance - 3000 WHERE id = 1;`, B `UPDATE account SET balance = balance - 5000 WHERE id = 1;` (B는 A 커밋까지 대기) → 최종 142000.00.

### 실험 7: SERIALIZABLE
| 시각 | 세션 A (SERIALIZABLE) | 세션 B (SERIALIZABLE) | 세션 C | 기대 결과 |
|---|---|---|---|---|
| T1 | `START TRANSACTION;` `SELECT balance` acc1 | | | A: 150000.00 |
| T2 | | `START TRANSACTION;` `SELECT balance` acc1 | `data_locks` 조회 | B: 150000.00. C: A와 B 각각 `TABLE`/`IS` + `PRIMARY`/`S,REC_NOT_GAP`/`1` (총 4행, 일반 SELECT가 공유 락을 잡음) |
| T3 | `UPDATE account SET balance = 147000 WHERE id = 1;` | | | A: 대기 (B의 S 락) |
| T4 | | `UPDATE account SET balance = 145000 WHERE id = 1;` | | 둘 중 한 세션에 `ERROR 1213 (40001): Deadlock found when trying to get lock; try restarting transaction`. 다른 세션의 UPDATE는 진행됨 |
| T5 | 살아남은 세션에서 `COMMIT;` | | `SELECT balance` acc1 | A가 살아남았으면 147000.00, B가 살아남았으면 145000.00. 어느 쪽이었는지 기록 |

### 자동화 테스트 (`IsolationLevelTest`)
| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 계좌 0001 = 150,000 | 실험 1의 T1~T5를 커넥션 두 개로 실행 (A: `TRANSACTION_READ_UNCOMMITTED`) | T3 = 50000.00, T5 = 150000.00 |
| 2 | 같은 준비 | 실험 1을 A `TRANSACTION_READ_COMMITTED`로 | T3 = 150000.00 |
| 3 | 같은 준비 | 실험 2를 RC / RR로 각각 | T4 = 160000.00 / 150000.00 |
| 4 | 같은 준비 | 실험 3의 T1~T8 (A: RR) | T4 = 150000.00, T5 = 160000.00, T6 = 150000.00, T8 = 155000.00 |
| 5 | 계좌 4개 | 실험 4의 T1~T4 (A: RC / RR) | RC: 1행, 2행, 2행 / RR: 1행, 1행, 2행 |

## 제약
- 실험 1~7은 반드시 mysql CLI에서 손으로 한다. GUI 도구는 autocommit과 트랜잭션 처리 방식이 도구마다 달라서 결과가 바뀔 수 있다.
- 실험 전에 매번 `sql/lab/reset.sh`를 실행한다. 앞 실험에서 열어 둔 트랜잭션이 있으면 락이 남아 다음 실험 결과가 바뀐다 (세션 C의 `data_locks`가 비어 있는지 확인하고 시작).
- 자동화 테스트에서 블로킹이 생기는 실험(5, 6-1, 7)을 한 스레드로 재현하지 않는다. 한 스레드에서 대기하면 테스트가 `innodb_lock_wait_timeout`만큼 멈춘다.
- 기록표의 "실제 결과"를 기대 결과에서 복사하지 않는다. 화면에 나온 그대로 적는다.

## 힌트
<details>
<summary>힌트 1: 실험 5에서 supremum에 락이 걸리는 이유</summary>

`id > 4`를 만족하는 레코드가 없으므로 InnoDB는 "id 4 뒤의 빈 공간 전체"를 잠가야 새 행이 끼어들지 못한다. 인덱스의 마지막 레코드 뒤에는 실제 데이터가 없는 가상 레코드(supremum)가 있고, 그 레코드의 next-key 락이 곧 "4 이후 전체 갭"에 대한 락이다.
MySQL 8.4 Reference Manual 17.7.1 "InnoDB Locking"의 "Next-Key Locks"와 "Insert Intention Locks" 절을 읽는다.
</details>

<details>
<summary>힌트 2: 실험 7에서 데드락이 나는 이유</summary>

A와 B가 모두 S 락을 가진 상태에서 둘 다 X 락을 요청하면, A는 B의 S 락이 풀리기를, B는 A의 S 락이 풀리기를 기다린다. 17.7.5 "Deadlocks in InnoDB" 절의 예제와 비교하고, `SHOW ENGINE INNODB STATUS\G`의 `LATEST DETECTED DEADLOCK` 부분을 열어 두 트랜잭션이 가진 락과 기다린 락의 `lock_mode`를 찾아본다 (M5-9에서 자세히 다룬다).
</details>

## 완료 기준
- [ ] `docs/m5-7-isolation-lab.md`에 실험 1~7(변형 포함)의 기록표가 "실제 결과" 열까지 채워져 있다
- [ ] 실험 5 T4와 실험 6-1의 `data_locks` 조회 결과 원문이 기록표에 붙어 있다
- [ ] `./gradlew test --tests "lab.bank.isolation.*"`에서 자동화 테스트 5개가 통과한다
- [ ] `docs/m5-7-isolation-lab.md`에 README 5절 표를 직접 다시 그리고, 각 칸 옆에 근거가 된 실험 번호를 적었다

## 생각해볼 질문
1. 실험 3에서 같은 트랜잭션 안의 두 SELECT가 150,000과 160,000을 돌려줬다. 잔액을 읽고 출금 가능 여부를 판단하는 코드는 둘 중 어느 SELECT를 써야 하는가? 그 이유를 실험 6과 연결해 설명한다.
2. PostgreSQL의 REPEATABLE READ는 실험 6의 T4~T5에서 B의 UPDATE를 직렬화 실패 에러로 거부한다. MySQL과 PostgreSQL 중 어느 동작이 금융 시스템에 더 안전한가? 애플리케이션 코드는 각각 무엇을 준비해야 하나?
3. Phase 6 M6-8에서는 인스턴스 2대가 같은 계좌를 처리한다. 이 미션에서 본 DB 락은 인스턴스가 여러 대여도 그대로 동작하는가? Redis 분산락이 필요한 경우는 어떤 경우일지 예측해 본다.
