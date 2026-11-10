# M5-1 SQL 기초

> 가이드 수준: L2 · 예상 시간: 3~5h · 선행: M4-8

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 컬럼·타입·제약 조건 명세표만 보고 `account`, `account_transaction` 두 테이블의 DDL을 작성해 MySQL 8.4에서 실행한다.
- JOIN, `GROUP BY`, `HAVING`, 윈도 함수로 7개 질의를 작성하고, 결과 집합이 이 문서의 기대 결과와 행 단위로 일치함을 보여준다.
- 제약 조건 위반 6종을 일부러 일으켜 MySQL 에러 코드(1048, 1062, 1406, 1451, 1452, 3819)를 기록한다.
- mysql CLI에서 `START TRANSACTION` / `COMMIT` / `ROLLBACK`으로 이체를 실행하고, 실패한 문장 뒤에도 트랜잭션이 열려 있음을 보여준다.

## 배경
Phase 4까지 계좌와 거래내역은 `Map` 안에 있었다. 서버를 재시작하면 모든 잔액이 사라진다. 은행은 잔액을 DB에 저장하고, "잔액은 음수가 될 수 없다", "같은 계좌번호는 두 번 생길 수 없다" 같은 규칙을 애플리케이션 코드뿐 아니라 **DB 제약 조건**으로도 지킨다. 애플리케이션에 버그가 있어도 DB가 마지막으로 막아준다.
이 미션은 M5-2부터 쓸 스키마를 만들고, JPA가 만들어 줄 SQL을 직접 읽을 수 있을 만큼 SQL을 손으로 써 본다.
Phase 1 M1-3에서 `Ledger.replayBalance`로 했던 "잔액 = 거래 합계" 검증을 이번에는 SQL 한 문장(질의 6)으로 한다.

## 요구사항
모든 SQL은 `workspace/sql/` 아래 파일로 저장하고, README의 "워크스페이스 만들기"대로 띄운 `bank-mysql` 컨테이너에서 실행한다.
파일 실행: `docker exec -i bank-mysql mysql -ubank -pbank bank < sql/01_schema.sql`

1. **`sql/01_schema.sql` — DDL.** 아래 명세대로 두 테이블을 만든다. 파일 맨 앞에서 `account_transaction`, `account` 순서로 `DROP TABLE IF EXISTS` 해서 몇 번을 실행해도 같은 결과가 나오게 한다. 엔진은 InnoDB, 문자셋은 MySQL 8.4 기본값(`utf8mb4`, `utf8mb4_0900_ai_ci`)을 쓴다.

   **`account`**

   | 컬럼 | 타입 | 제약 |
   |---|---|---|
   | `id` | `BIGINT` | 기본 키, `AUTO_INCREMENT` |
   | `number` | `VARCHAR(13)` | `NOT NULL`, 유니크 제약 이름 `uk_account_number` (형식 `110-1234-5678`) |
   | `owner_name` | `VARCHAR(50)` | `NOT NULL` (예금주 표시 이름) |
   | `owner_id` | `VARCHAR(50)` | `NOT NULL` (M4-7의 `Account.ownerId`, 로그인 username) |
   | `currency` | `VARCHAR(3)` | `NOT NULL` (`KRW`, `USD`) |
   | `balance` | `DECIMAL(19,2)` | `NOT NULL`, 체크 제약 이름 `chk_account_balance_non_negative` (`balance >= 0`) |
   | `status` | `VARCHAR(10)` | `NOT NULL` (`ACTIVE`, `FROZEN`, `CLOSED`) |
   | `created_at` | `DATETIME(6)` | `NOT NULL`, 기본값 `CURRENT_TIMESTAMP(6)` |

   **`account_transaction`** (`TRANSACTION`은 MySQL 키워드라서 테이블 이름에 접두어를 붙인다)

   | 컬럼 | 타입 | 제약 |
   |---|---|---|
   | `id` | `BIGINT` | 기본 키, `AUTO_INCREMENT` |
   | `transaction_uuid` | `VARCHAR(36)` | `NOT NULL`, 유니크 제약 이름 `uk_tx_uuid` (Phase 1 `Transaction.id`) |
   | `account_id` | `BIGINT` | `NOT NULL`, 외래 키 이름 `fk_tx_account` → `account(id)` (`ON DELETE` 옵션 없음 = RESTRICT) |
   | `type` | `VARCHAR(20)` | `NOT NULL` (`DEPOSIT`, `WITHDRAWAL`, `TRANSFER_IN`, `TRANSFER_OUT`, `REVERSAL`) |
   | `amount` | `DECIMAL(19,2)` | `NOT NULL`, 체크 제약 이름 `chk_tx_amount_positive` (`amount > 0`) |
   | `balance_after` | `DECIMAL(19,2)` | `NOT NULL` |
   | `memo` | `VARCHAR(100)` | `NULL` 허용 |
   | `reversal_of` | `VARCHAR(36)` | `NULL` 허용 (취소 거래일 때 원거래 `transaction_uuid`) |
   | `occurred_at` | `DATETIME(6)` | `NOT NULL` |

   인덱스: `idx_tx_account_occurred (account_id, occurred_at)`. 외래 키 `fk_tx_account`는 이 인덱스를 함께 쓴다.

2. **`sql/02_seed.sql` — 시드 데이터.** 아래 행을 이 순서로 INSERT한다 (`id`는 AUTO_INCREMENT가 1부터 매기게 둔다). `transaction_uuid`는 `UUID()`로 채운다. 파일 맨 앞에서 두 테이블을 비우고(`DELETE` 후 `ALTER TABLE ... AUTO_INCREMENT = 1`, 또는 `01_schema.sql` 재실행) 시작한다.

   | account.id | number | owner_name | owner_id | currency | balance | status |
   |---|---|---|---|---|---|---|
   | 1 | 110-0000-0001 | 김하나 | kim | KRW | 150000.00 | ACTIVE |
   | 2 | 110-0000-0002 | 이두리 | lee | KRW | 30000.00 | ACTIVE |
   | 3 | 110-0000-0003 | 박세나 | park | KRW | 0.00 | FROZEN |
   | 4 | 110-0000-0004 | 최네오 | choi | KRW | 0.00 | ACTIVE |

   | tx.id | account_id | type | amount | balance_after | memo | occurred_at |
   |---|---|---|---|---|---|---|
   | 1 | 1 | DEPOSIT | 200000 | 200000 | 급여 | 2026-01-05 09:00:00 |
   | 2 | 1 | WITHDRAWAL | 30000 | 170000 | 카드대금 | 2026-01-10 12:30:00 |
   | 3 | 1 | TRANSFER_OUT | 50000 | 120000 | 이두리 이체 | 2026-01-31 23:59:59 |
   | 4 | 2 | TRANSFER_IN | 50000 | 50000 | 김하나 이체 | 2026-01-31 23:59:59 |
   | 5 | 1 | DEPOSIT | 30000 | 150000 | 환급 | 2026-02-01 00:00:00 |
   | 6 | 2 | WITHDRAWAL | 30000 | 20000 | ATM 출금 | 2026-02-03 08:15:00 |
   | 7 | 3 | DEPOSIT | 10000 | 10000 | 입금 | 2026-01-15 10:00:00 |
   | 8 | 3 | WITHDRAWAL | 10000 | 0 | 출금 | 2026-01-20 10:00:00 |

   계좌 2의 `balance`(30,000)는 거래내역 합계와 일부러 다르게 넣었다. 질의 6이 이 불일치를 찾아야 한다.

3. **`sql/03_queries.sql` — 조회 질의 7개.** 각 질의 위에 `-- Q1` 형식의 주석을 단다. 거래 방향 규칙: `DEPOSIT`, `TRANSFER_IN`은 +, `WITHDRAWAL`, `TRANSFER_OUT`은 −. (`REVERSAL`은 시드에 없으므로 이 미션에서는 다루지 않는다.)
   - Q1: `ACTIVE` 계좌의 `number`, `owner_name`, `balance`를 `number` 오름차순으로
   - Q2: 계좌 `110-0000-0001`의 2026년 1월 거래를 `occurred_at` 오름차순으로. 반열린 구간(`>= '2026-01-01' AND < '2026-02-01'`)으로 쓴 버전과 `BETWEEN '2026-01-01' AND '2026-01-31'`로 쓴 버전 두 개
   - Q3: 모든 계좌의 `number`, `owner_name`, 거래 건수. 거래가 0건인 계좌도 0으로 나와야 한다
   - Q4: 계좌 `110-0000-0001`의 거래 유형별 건수와 금액 합계, `type` 오름차순
   - Q5: 출금성 거래(`WITHDRAWAL` + `TRANSFER_OUT`) 합계가 50,000 이상인 계좌의 `number`와 합계 (`HAVING` 사용)
   - Q6: 모든 계좌의 `number`, `balance`, 거래내역으로 다시 계산한 잔액(`ledger_balance`), 그리고 둘이 다른 계좌만 고르는 버전. 거래가 없는 계좌의 `ledger_balance`는 `NULL`이 아니라 `0.00`
   - Q7: 계좌별 가장 최근 거래 1건(`ROW_NUMBER()` 윈도 함수, 같은 시각이면 `id`가 큰 것)

4. **`sql/04_transaction_and_constraints.sql` — 트랜잭션과 제약 조건.** 시드 직후 상태에서 실행한다.
   - 이체 1: 계좌 1 → 계좌 4로 20,000원. `START TRANSACTION`, `UPDATE` 2개, `INSERT` 2개(`TRANSFER_OUT`, `TRANSFER_IN`), `COMMIT`
   - 이체 2: 계좌 4에 1,000,000원을 먼저 더하고, 계좌 1에서 1,000,000원을 빼는 순서로 실행한다. 두 번째 `UPDATE`가 체크 제약에 걸려 실패한 뒤 `SELECT`로 계좌 4 잔액을 확인하고, `ROLLBACK`한다
   - 제약 위반 6종(테스트 시나리오 9~14)을 각각 한 문장씩 실행하고, 출력된 에러 메시지를 주석으로 붙여 둔다

## 테스트 시나리오
"실행"을 mysql CLI에서 돌린 결과가 "기대 결과"와 행 수·값·순서까지 같아야 한다. 금액은 `DECIMAL(19,2)`이므로 `150000.00`처럼 소수 둘째 자리까지 출력된다.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 01, 02 실행 직후 | `SHOW CREATE TABLE account_transaction` | `uk_tx_uuid`, `idx_tx_account_occurred`, `fk_tx_account`, `chk_tx_amount_positive`가 모두 보임 |
| 2 | 시드 직후 | Q1 | 3행: `110-0000-0001 / 김하나 / 150000.00`, `110-0000-0002 / 이두리 / 30000.00`, `110-0000-0004 / 최네오 / 0.00` |
| 3 | 시드 직후 | Q2 반열린 구간 버전 / `BETWEEN` 버전 | 반열린 구간: 3행 (tx 1, 2, 3 — 23:59:59 거래 포함, 2/1 00:00:00 제외) / `BETWEEN`: 2행 (tx 1, 2 — tx 3 누락) |
| 4 | 시드 직후 | Q3 | 4행 (`number` 순): 0001 → 4, 0002 → 2, 0003 → 2, 0004 → 0. INNER JOIN으로 바꾸면 3행 (0004 사라짐) |
| 5 | 시드 직후 | Q4 | 3행: `DEPOSIT / 2 / 230000.00`, `TRANSFER_OUT / 1 / 50000.00`, `WITHDRAWAL / 1 / 30000.00` |
| 6 | 시드 직후 | Q5 | 1행: `110-0000-0001 / 80000.00` (0002는 30,000, 0003은 10,000이라 제외) |
| 7 | 시드 직후 | Q6 전체 버전 / 불일치만 고르는 버전 | 전체 4행 `ledger_balance`: 150000.00, 20000.00, 0.00, 0.00 / 불일치 1행: `110-0000-0002 / 30000.00 / 20000.00` |
| 8 | 시드 직후 | Q7 | 3행: 계좌 1 → tx 5 (`2026-02-01 00:00:00`, DEPOSIT, 30000.00), 계좌 2 → tx 6, 계좌 3 → tx 8. 계좌 4는 거래가 없어 나오지 않음 |
| 9 | 시드 직후 | `owner_name`을 `NULL`로 계좌 INSERT | `ERROR 1048` Column 'owner_name' cannot be null, 행 수 4 유지 |
| 10 | 시드 직후 | `number = '110-0000-0001'`로 계좌 INSERT | `ERROR 1062` Duplicate entry '110-0000-0001' for key 'account.uk_account_number' |
| 11 | 시드 직후 | `currency = 'KRWX'`로 계좌 INSERT | `ERROR 1406` Data too long for column 'currency' (8.4 기본 `sql_mode`의 `STRICT_TRANS_TABLES` 때문. 엄격 모드가 아니면 경고와 함께 `KRW`로 잘려 들어간다) |
| 12 | 시드 직후 | `DELETE FROM account WHERE id = 3` | `ERROR 1451` Cannot delete or update a parent row: a foreign key constraint fails |
| 13 | 시드 직후 | `account_id = 999`로 거래 INSERT | `ERROR 1452` Cannot add or update a child row: a foreign key constraint fails |
| 14 | 시드 직후 | `UPDATE account SET balance = -1 WHERE id = 4` / `amount = 0`으로 거래 INSERT | 둘 다 `ERROR 3819` Check constraint '…' is violated (제약 이름이 각각 `chk_account_balance_non_negative`, `chk_tx_amount_positive`) |
| 15 | 시드 직후 | 이체 1 후 `SELECT id, balance FROM account WHERE id IN (1, 4)`, `SELECT COUNT(*) FROM account_transaction` | 계좌 1 = 130000.00, 계좌 4 = 20000.00, 거래 10행 |
| 16 | 15 직후 | 이체 2: 계좌 4 `+1,000,000` 성공 → 계좌 1 `-1,000,000` 실패 → 같은 세션에서 계좌 4 조회 | 두 번째 UPDATE는 `ERROR 3819`. 그 직후 계좌 4 조회 결과 `1020000.00` (실패한 문장만 취소되고 트랜잭션은 열려 있음) |
| 17 | 16 직후 | `ROLLBACK` 후 계좌 1, 4 조회 | 계좌 1 = 130000.00, 계좌 4 = 20000.00 (15번 상태로 복귀) |

9~14번의 INSERT·UPDATE는 확인하려는 컬럼 하나만 틀리게 하고 나머지 컬럼은 모두 올바른 값으로 채운다. 예를 들어 `owner_id`를 빠뜨리면 `ERROR 1364` Field 'owner_id' doesn't have a default value가 먼저 나서 의도한 에러를 볼 수 없다.

계산식 (7번): 계좌 1 = 200,000 − 30,000 − 50,000 + 30,000 = 150,000 / 계좌 2 = 50,000 − 30,000 = 20,000 / 계좌 3 = 10,000 − 10,000 = 0.

## 제약
- 금액 컬럼에 `FLOAT`/`DOUBLE` 금지 — 2진 부동소수점이라 `0.1 + 0.2`가 정확히 표현되지 않는다. `DECIMAL(19,2)`만 쓴다.
- 테이블·제약·인덱스 이름은 명세표의 이름을 그대로 쓴다. M5-3의 Flyway 마이그레이션과 M5-9의 락 관찰 결과(`INDEX_NAME`)가 이 이름을 기준으로 한다.
- `SELECT *` 금지 (Q1~Q7). 결과 컬럼을 명시해야 기대 결과와 비교할 수 있다.
- Q6에서 서브쿼리 또는 `LEFT JOIN` + `COALESCE` 중 하나를 쓰되, 거래가 0건인 계좌를 결과에서 빠뜨리지 않는다.
- ORM이나 GUI 도구가 만든 SQL을 붙여 넣지 않는다. 이 미션은 mysql CLI와 텍스트 에디터만 쓴다.

## 힌트
<details>
<summary>힌트 1: Q6에서 NULL이 결과를 바꾸는 지점</summary>

`LEFT JOIN` 후 `SUM()`은 거래가 없는 계좌에서 `NULL`을 돌려준다. `0.00 <> NULL`의 결과는 `TRUE`도 `FALSE`도 아닌 `NULL`이라서 `WHERE`에서 그 행이 빠진다.
MySQL 8.4 Reference Manual의 "Working with NULL Values" 절과 `COALESCE()` 함수 설명을 읽고, 계좌 4가 전체 버전에 `0.00`으로 나오는지 확인한다.
부호를 붙이는 방법은 `CASE WHEN type IN (...) THEN amount ELSE -amount END`를 검색어로 찾아본다.
</details>

<details>
<summary>힌트 2: 실패한 문장 뒤의 트랜잭션 상태</summary>

InnoDB는 대부분의 에러에서 **그 문장만** 되돌린다. 트랜잭션 전체를 되돌리는 대표적인 경우는 데드락(에러 1213)이다 (M5-9).
MySQL 8.4 Reference Manual의 "InnoDB Error Handling" 절(InnoDB Troubleshooting 아래)에서 어떤 에러가 문장만, 어떤 에러가 트랜잭션 전체를 롤백하는지 찾아 표로 옮겨 둔다.
</details>

## 완료 기준
- [ ] `01_schema.sql` → `02_seed.sql`을 연속 두 번 실행해도 에러 없이 끝나고, `SELECT COUNT(*)`가 `account` 4, `account_transaction` 8이다
- [ ] Q1~Q7 실행 결과가 테스트 시나리오 2~8의 기대 결과와 일치한다. 실제 출력을 `docs/m5-1-query-results.md`에 붙여 둔다
- [ ] `04_transaction_and_constraints.sql`에 시나리오 9~17의 SQL과 실제 에러 메시지(주석)가 있다
- [ ] `docs/m5-1-query-results.md`에 "실패한 문장 뒤 트랜잭션 상태"(시나리오 16)를 3줄 이내로 설명했다

## 생각해볼 질문
1. 잔액이 음수가 되면 안 된다는 규칙을 Phase 1의 `Account.withdraw()`가 이미 지키는데, DB에 체크 제약을 또 거는 이유는 무엇인가? 두 군데 규칙이 서로 다르게 바뀌면 어떤 일이 생기나?
2. `account.balance`와 거래내역 합계가 다를 때(질의 6) 어느 쪽을 믿어야 하는가? Phase 6에서는 잔액 컬럼 대신 복식부기 분개(`JournalEntry`, `JournalLine`)를 원천으로 삼는다. 이 구조에서 질의 6은 어떻게 바뀔까?
3. 기본 키를 `BIGINT AUTO_INCREMENT`로 두고 UUID는 별도 유니크 컬럼(`transaction_uuid`)으로 둔 이유는 무엇일까? InnoDB 클러스터드 인덱스(README 1절) 관점에서 UUID를 기본 키로 쓰면 INSERT가 어떻게 달라질지 예측해 본다.
