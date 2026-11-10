# M6-6 일 마감과 대사

> 가이드 수준: L3, 예상 시간: 4~6h, 선행: M6-5

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 업무일자마다 계좌별 마감 잔액 스냅샷을 남기고, 대사 규칙 R1~R5로 원장, 잔액, 거래내역의 불일치를 찾는 일 마감 Job을 만든다.
- 테스트가 일부러 망가뜨린 행 1개(잔액 +1원, 균형 깨진 분개 라인, 분개 없는 거래내역)를 대사 Job이 정확히 그 계좌, 그 규칙으로 찾아내는 것을 보여준다.
- 대사 도중 이체가 계속 들어와도 거짓 불일치가 0건인 것을 테스트로 보여준다.

## 배경
`account.balance`는 조회를 빠르게 하려고 둔 값이다. 원장(분개 라인)과 이 값이 어긋나는 버그: 분개 없이 잔액만 UPDATE, 운영자의 수기 SQL, 롤백되지 않은 부분 쓰기: 는 API 응답만으로는 보이지 않는다. 고객이 "잔액이 이상하다"고 문의하기 전에 은행이 먼저 찾아야 한다.
그래서 은행은 매일 마감 후 두 기록을 비교하는 대사를 돌리고, 불일치는 자동으로 고치지 않고 리포트로 남긴다.
M6-5에서 Spring Batch Job과 재시작을 다뤘다. 이 미션은 같은 도구로 "돈을 움직이지 않고 검사만 하는" Job을 만들고, M6-1에서 규칙만 정해둔 휴면 전환을 실제로 실행한다.

## 요구사항

### 1. 업무일 마감 규칙 (이 미션의 규칙)
1. `business_day` 테이블(Flyway `V7__`): 업무일자 PK, 상태(`CLOSED`, `CLOSED_WITH_MISMATCH`), 마감 시각, 불일치 수.
2. 업무일자 D의 마감은 `Clock` 기준 현재 날짜(Asia/Seoul)가 D보다 뒤일 때만 실행한다. D 당일이나 미래 날짜는 422 `BUSINESS_DATE_NOT_ENDED`.
3. D의 `interestAccrualJob`(M6-5)이 `COMPLETED`가 아니면 마감 Job은 첫 Step에서 실패하고 종료 설명에 `INTEREST_JOB_NOT_COMPLETED`를 남긴다.
4. 이미 `CLOSED`인 D를 다시 마감하면 409 `ALREADY_CLOSED`. `CLOSED_WITH_MISMATCH`인 D는 새 실행 파라미터(`run.id`)로 다시 실행할 수 있다. 재실행은 스냅샷을 다시 만들지 않고 대사(R1~R5)와 상태 갱신만 다시 한다.
5. 실행 경로: `POST /api/admin/jobs/daily-closing` (본문 `{"businessDate":"2026-11-10"}`), 응답 202 + `JobExecution` ID.

### 2. Job 구성 `dailyClosingJob` (`lab.corebank.closing`)
1. `snapshotStep`: D 이전에 개설된 모든 계좌에 대해 `account_balance_snapshot`((`account_id`, `business_date`) 유니크)에 D의 마감 잔액(= 고객예금 분개 라인 중 업무일자 ≤ D인 라인의 Σ대변 − Σ차변)을 저장한다. 청크 지향, 청크 크기 100.
2. `reconcileStep`: 아래 R1~R5를 검사하고, 어긋난 건마다 `reconciliation_mismatch` 행을 1개 만든다.
3. `dormancyStep`: M6-1의 휴면 판정 규칙(`L + 365일 < D`)을 만족하는 `ACTIVE` 계좌를 전이 T4로 `DORMANT`로 바꾼다. 계좌마다 상태 변경과 이력 행 추가가 한 트랜잭션이다.
4. `closeStep`: 불일치가 0건이면 `business_day` 상태 `CLOSED`, 1건 이상이면 `CLOSED_WITH_MISMATCH`와 불일치 수를 저장한다. 불일치가 있어도 Job의 `BatchStatus`는 `COMPLETED`이고, `ExitStatus`의 종료 코드는 `COMPLETED_WITH_MISMATCH`다.

### 3. 대사 규칙

| 규칙 | 비교 대상 A | 비교 대상 B | 불일치 행의 대상 |
|---|---|---|---|
| R1 | 업무일자 D인 분개마다 Σ차변 | 같은 분개의 Σ대변 | `journal_entry_id` |
| R2 | 계좌마다 `account.balance` | 그 계좌의 고객예금 분개 라인 전체의 Σ대변 − Σ차변 | `account_id` |
| R3 | 계좌마다 D의 `account_transaction` 금액 합계(입금성 +, 출금성 −) | 그 계좌의 업무일자 D 고객예금 분개 라인의 Σ대변 − Σ차변 | `account_id` |
| R4 | Σ`account.balance` (전체 계좌) | 고객예금 계정 원장 잔액 (INV-2) | 없음 (전체 1행) |
| R5 | 전체 `journal_line`의 Σ차변 (시산표) | 전체 `journal_line`의 Σ대변 | 없음 (전체 1행) |

- `reconciliation_mismatch` 열: 업무일자, `JobExecution` ID, 규칙 코드(`R1`~`R5`), 대상 ID(없으면 NULL), 기대값(B), 실제값(A), 차이(A − B), 발견 시각.
- R2는 Job 실행 시점의 값을 비교한다. 같은 계좌의 `balance`와 분개 합계를 **같은 DB 트랜잭션 안에서** 읽는다. 두 값을 다른 트랜잭션에서 읽으면 그 사이에 커밋된 이체 때문에 거짓 불일치가 생긴다(MySQL InnoDB 기본 격리 수준 `REPEATABLE READ`의 일관된 읽기, M5-7).
- 대사 Job은 어떤 테이블의 돈 관련 값도 고치지 않는다. 불일치를 고치는 방법은 이 미션 범위 밖이다.

### 4. 설계 문서 `workspace/docs/batch-design.md` (M6-5 문서에 절 추가)
- `dailyClosingJob`의 Step 구성도와 각 Step의 트랜잭션 경계.
- R1~R5 각각을 SQL 몇 번으로 계산하는지, 그 SQL이 쓰는 인덱스(`EXPLAIN` 결과의 `key` 열).
- R2를 계좌별 트랜잭션으로 읽을 때와 청크(100계좌) 트랜잭션으로 읽을 때, 이체가 동시에 들어오면 각각 무엇이 보이는지.

## 직접 작성할 테스트 시나리오
`workspace/docs/test-scenarios/M6-6.md`에 표(번호 / Given / When / Then)를 쓰고 리뷰를 받은 뒤 구현한다. 손상 주입은 테스트 코드에서 `JdbcTemplate`으로 SQL을 직접 실행해 만든다. Then에는 불일치 행의 규칙 코드, 대상 ID, 기대값, 실제값, 차이를 쓴다.

반드시 포함할 경우 (최소 13개 행):
1. 정상 데이터(계좌 10개, 입금, 출금, 이체, 이자 섞어 50건): 불일치 0건, `business_day` `CLOSED`, 종료 코드 `COMPLETED`
2. 계좌 X에 `UPDATE account SET balance = balance + 1`: R2 1행(X, 차이 +1), R4 1행(차이 +1), R1, R3, R5 0행, 다른 계좌 불일치 0
3. 업무일자 D인 기존 분개에 고객예금 X 차변 500원 라인 INSERT: R1(그 분개), R2(X), R3(X), R4, R5 각 1행, 차이 값을 부호까지 적는다
4. 분개 없이 `account_transaction`에 X의 입금 1,000원 행 INSERT: R3 1행(X)만, R1, R2, R4, R5 0행
5. 손상 2와 4를 서로 다른 계좌에 동시에 주입: 각 계좌의 불일치만 나옴
6. 불일치가 있는 마감 후 `account.balance`가 손상된 값 그대로인 것 (대사가 고치지 않음)
7. 대사 실행 중 다른 스레드가 당행이체 500건을 계속 보냄: 불일치 0건
8. D 당일에 마감 요청: 422 `BUSINESS_DATE_NOT_ENDED`
9. D의 이자 Job 미완료: 마감 Job `FAILED`, 종료 설명 `INTEREST_JOB_NOT_COMPLETED`
10. `CLOSED`인 D 재마감: 409, `CLOSED_WITH_MISMATCH`인 D를 손상 복구 후 `run.id=2`로 재실행: `CLOSED`, 스냅샷 행 수 변화 없음
11. 휴면 전환: 마지막 고객 주도 거래일 L = D − 366일인 `ACTIVE` 계좌는 `DORMANT` + 이력 1행, L = D − 365일 계좌는 `ACTIVE` 유지, `SUSPENDED` 계좌는 L과 상관없이 유지
12. 스냅샷: D의 스냅샷 금액 == D−1 스냅샷 + R3의 B값 (계좌 3개 이상으로 확인)

## 제약
- 대사 Job에서 `account`, `journal_entry`, `journal_line`, `account_transaction`에 UPDATE, DELETE, INSERT를 하지 않는다(휴면 전환 `dormancyStep`의 `account.status`와 이력 INSERT만 예외).
- 불일치를 로그로만 남기지 않는다: 로그는 보관 기간이 지나면 사라지고 집계 쿼리로 조회할 수 없다. 반드시 `reconciliation_mismatch` 테이블에 남긴다.
- R1~R5를 계좌마다 분개 전체를 메모리로 읽어 Java에서 더하는 방식으로 구현하지 않는다. 합계는 SQL 집계로 구한다.

## 힌트
<details>
<summary>힌트 1: Job은 COMPLETED인데 결과는 다르게 알리기</summary>

Spring Batch Reference 6.0 "Configuring a Step" → "Controlling Step Flow"에서 `ExitStatus`와 `BatchStatus`의 차이를 읽는다. Step이나 Job 리스너에서 종료 코드를 바꿀 수 있는 지점이 어디인지 찾는다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 M6-6 시나리오 표의 모든 행에 대응하는 테스트가 통과한다
- [ ] 손상 주입 테스트(시나리오 2~5)가 불일치 행의 규칙 코드, 대상 ID, 차이를 모두 assert한다
- [ ] 시나리오 7(대사 중 이체 500건)을 `@RepeatedTest(5)`로 돌려 5번 모두 불일치 0건이다
- [ ] `workspace/docs/batch-design.md`에 4절의 Step 구성도, R1~R5 SQL과 `EXPLAIN` `key` 열, R2 트랜잭션 범위 비교가 있다
- [ ] PR 본문에 `workspace/docs/test-scenarios/M6-6.md` 표가 붙어 있다

## 생각해볼 질문
1. 손상 2(잔액 +1원)는 원장에는 문제가 없고 `account.balance`만 틀렸다. 이 불일치를 고치는 방법은 반대 분개인가, `balance` 수정인가? 어느 쪽이 "원장이 원본"이라는 원칙과 맞는가?
2. R2를 청크 트랜잭션 하나로 계좌 100개씩 읽으면 InnoDB가 그 트랜잭션 동안 유지해야 하는 것(undo 로그)이 늘어난다. 계좌 100만 개에서 청크 크기를 정하는 기준은 무엇인가?
3. 당행 원장끼리의 대사(R1~R5)와 당행 vs 대외기관 대사(M6-7)는 무엇이 다른가? 대외기관 대사에서는 어느 쪽 기록이 맞다고 볼 근거가 있는가?
4. Phase 8에서 이체 완료를 Kafka 이벤트로 다른 서비스에 보내면, "이 서비스의 원장 vs 다른 서비스가 받은 이벤트" 대사가 새로 필요해진다. R3와 같은 모양의 규칙을 하나 만들어본다.
