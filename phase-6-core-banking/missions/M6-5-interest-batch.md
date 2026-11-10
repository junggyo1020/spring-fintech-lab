# M6-5 이자 배치 (Spring Batch)

> 가이드 수준: L3, 예상 시간: 5~7h, 선행: M6-3

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 계좌 1,000개의 일 이자를 청크 크기 100으로 적립하는 Spring Batch Job을 만들고, 250번째 계좌에서 실패시킨 뒤 재시작해 적립 행이 정확히 1,000개인 것을 테스트로 보여준다.
- 같은 업무일자로 Job을 다시 실행하거나 다른 실행 파라미터로 한 번 더 실행해도 이자 분개가 추가로 생기지 않는 것을 테스트로 보여준다.
- 월말 지급 분개의 이자, 소득세, 지방소득세 금액이 `fintech-domain-facts` 1절의 계산 순서와 일치하는 것을 Python `decimal`로 미리 계산한 기대값으로 보여준다.

## 배경
이자는 매일 밤 모든 계좌에 대해 계산된다. 이 작업이 중간에 실패했을 때 처음부터 다시 돌리면 이미 처리된 계좌에 이자가 두 번 들어가고, 실패 지점을 모른 채 멈춰두면 나머지 고객은 이자를 못 받는다.
배치의 정합성 요구는 "실패하면 실패한 지점부터 다시 시작하고, 몇 번을 다시 돌려도 계좌, 날짜마다 이자는 한 번"이다.
Phase 1 M1-4에서 이자 계산기(`InterestPolicy`)와 세금 계산기(`TaxCalculator`)를 만들었고, M6-3에서 분개와 잔액을 한 트랜잭션으로 남기는 방법을 만들었다. 이 미션은 둘을 배치로 묶는다.

## 요구사항

### 1. 이자 규칙
아래 1~5는 **이 미션의 규칙**이다(실제 입출금 예금 이자 규칙은 상품 약관마다 다르다). 6은 확인된 세법 사실(`fintech-domain-facts` 1절, 확인일 2026-11-10)이고, 6의 10원 미만 절사만 이 미션의 규칙이다.

1. 상품 `DEMAND_DEPOSIT`의 연이율은 3.5%(`0.035000`)다. Flyway로 `product`에 넣는다.
2. 적립 대상: 업무일자 D에 상태가 `ACTIVE`, `SUSPENDED`, `DORMANT`이고 D 이전(D 포함)에 개설된 계좌. `CLOSED` 계좌는 적립하지 않는다.
3. 적립 원금: D의 마감 잔액 = 그 계좌의 고객예금 분개 라인 중 업무일자 ≤ D인 라인의 (Σ대변 − Σ차변). `account.balance` 현재 값을 쓰지 않는다(배치가 다음 날 새벽에 돌 때 이미 바뀌어 있다). 원금이 0원이면 적립 행을 만들지 않는다.
4. 일 적립액 = 원금 × 연이율 ÷ (D가 속한 해가 윤년이면 366, 아니면 365). 소수 10자리에서 버린다(`RoundingMode.DOWN`). 원 단위로 자르지 않고 `interest_accrual`에 소수 10자리 그대로 저장한다.
5. 지급: D가 그 달의 말일이면 같은 Job 실행 안에서 적립 다음에 지급한다. 계좌별 그 달(1일~D) 적립액 합계를 원 미만 버림한 값이 세전 이자다. 버린 원 미만 금액은 다음 달로 넘기지 않는다.
6. 세금: 소득세 = 세전 이자 × 14%, 10원 미만 절사 → 지방소득세 = (절사한 소득세) × 10%, 10원 미만 절사 → 실지급액 = 세전 이자 − 소득세 − 지방소득세. 15.4%를 한 번에 곱하지 않는다.
   - 예 (`fintech-domain-facts` 1절): 세전 이자 28,767원 → 소득세 4,027.38 → 4,020원 / 지방소득세 402 → 400원 / 실지급 24,347원.
7. 지급 분개(유형 `INTEREST`): 차변 이자비용(세전 이자) / 대변 고객예금(실지급액), 예수소득세(소득세), 예수지방소득세(지방소득세). 0원인 라인은 만들지 않는다(M6-2의 J3). 세전 이자가 0원이면 분개를 만들지 않고 그 달 적립 행만 지급 완료로 표시한다.
8. 지급은 고객 주도 거래가 아니다(M6-1). 휴면 판정 기준 시각을 바꾸지 않는다.
9. 그 달 지급일에 `CLOSED`인 계좌의 미지급 적립 행은 `FORFEITED`로 표시하고 지급하지 않는다(이 미션의 규칙).

### 2. 테이블 (Flyway `V5__`, `V6__`)
1. Spring Batch 메타 테이블: `spring-batch-core-6.0.6.jar` 안의 `org/springframework/batch/core/schema-mysql.sql` 내용을 Flyway 마이그레이션 파일로 옮긴다. `spring.batch.jdbc.initialize-schema`는 `never`로 둔다(README "워크스페이스 만들기" 3절).
2. `interest_accrual`: (`account_id`, `accrual_date`) 유니크, 적립액 `DECIMAL(29,10)`, 원금, 연이율, 지급 상태(`UNPAID`, `PAID`, `FORFEITED`).
3. `interest_payment`: (`account_id`, `payment_month`) 유니크(`payment_month`는 `'2026-11'` 형식), 세전 이자, 소득세, 지방소득세, 실지급액, `journal_entry_id`.

### 3. Job 구성 (`lab.corebank.interest`)
1. Job 이름 `interestAccrualJob`, 식별 파라미터 `businessDate`(`LocalDate`). Spring Boot 4.1.x + Spring Batch 6.0.x 기준으로 JDBC `JobRepository`를 쓴다(`spring-boot-starter-batch-jdbc`).
2. `accrualStep`: 청크 지향 처리, 청크 크기 100. 읽기는 계좌 ID 오름차순. 재시작 시 마지막 커밋 다음 계좌부터 읽는다.
3. `paymentStep`: D가 말일일 때만 실행한다(아니면 Job은 `accrualStep`만 실행하고 `COMPLETED`). 계좌 1개의 지급(분개 저장, `account.balance` 증가, `account_transaction` `INTEREST` 행, `interest_payment` 행, 적립 행 상태 변경)은 한 트랜잭션이다.
4. 중복 방지는 두 겹이다: (a) Spring Batch 재시작 위치, (b) `interest_accrual`, `interest_payment` 유니크 제약. (b)에 걸린 계좌는 실패가 아니라 "이미 처리됨"으로 건너뛰고 건너뛴 수를 `StepExecution`의 쓰기 건너뜀 수 또는 로그로 남긴다.
5. 실행 방법: 테스트에서는 `JobOperator`(Spring Batch 6에서 `JobLauncher`를 확장한다)로 실행한다. 운영용 실행 경로로 `POST /api/admin/jobs/interest-accrual` (본문 `{"businessDate":"2026-11-30"}`)을 만든다. 응답은 202 + `JobExecution` ID다.
6. 테스트에서 특정 계좌 처리 중 예외를 일으키는 장치(예: 테스트 프로파일에서만 등록되는 `ItemProcessor` 래퍼, 실패시킬 계좌 ID를 프로퍼티로 받음)를 만든다. 운영 코드 경로에는 이 장치가 없다.

### 4. 설계 문서 `workspace/docs/batch-design.md` (M6-6과 같이 쓴다)
- Job, Step 구성도 (Mermaid `flowchart`), 각 Step의 reader/processor/writer 클래스 이름, 청크 크기, 트랜잭션 경계.
- 재시작 시 Spring Batch가 어디서 다시 읽는지, 어떤 메타 테이블(`BATCH_STEP_EXECUTION_CONTEXT` 등)의 어떤 값이 그 위치를 정하는지 실제 테스트 실행 후 조회한 값과 함께 적는다.
- `JdbcPagingItemReader`와 `JdbcCursorItemReader` 중 무엇을 골랐는지와 이유 (재시작, 커넥션 점유 시간, 읽는 도중 계좌가 추가될 때의 동작).

## 직접 작성할 테스트 시나리오
`workspace/docs/test-scenarios/M6-5.md`에 표(번호 / Given / When / Then)를 쓰고 리뷰를 받은 뒤 구현한다. 금액 기대값은 구현 코드가 아니라 Python `decimal`(또는 손 계산)로 구하고, 계산이 3단계 이상이면 표 아래에 계산식을 적는다.

반드시 포함할 경우 (최소 14개 행):
1. 잔액 10,000,000원 계좌를 2026-11-01~2026-11-30 매일 적립: 일 적립액(소수 10자리), 30일 합계, 11-30 지급의 세전 이자, 소득세, 지방소득세, 실지급액. 세전 이자가 28,767원, 실지급액이 24,347원이 되는지 직접 계산해 확인한다
2. 같은 원금으로 2028-02-01~2028-02-29(윤년, 366일 기준) 적립과 02-29 지급
3. 잔액 1,000원 계좌의 30일 적립과 지급 (세전 이자가 10원 미만이라 세금 라인이 없는 경우)
4. 세전 이자 72원: 소득세 10원, 지방소득세 0원, 지방소득세 라인 없음
5. 원금 0원 계좌: 적립 행 없음
6. 월 중간에 입금이 있는 계좌: 입금 전후 날짜의 원금이 다름 (원금 3번 규칙 확인)
7. `CLOSED` 계좌 적립 제외, 지급일에 `CLOSED`인 계좌의 미지급 적립이 `FORFEITED`
8. `DORMANT` 계좌 적립, 지급 대상, 지급 후 마지막 고객 주도 거래 시각 불변
9. 11-29(말일 아님) 실행: `paymentStep` 미실행
10. 계좌 1,000개, 청크 100, 250번째 계좌에서 예외: 첫 실행 `FAILED`, 적립 행 200개 → 같은 파라미터로 재시작 `COMPLETED`, 적립 행 1,000개, 재시작 `JobExecution`의 읽은 수 800
11. `COMPLETED`된 `businessDate=2026-11-30`으로 다시 실행: `JobInstanceAlreadyCompleteException`(Spring Batch 6.0.6 `org.springframework.batch.core.launch` 패키지)
12. 같은 업무일자 + 식별 파라미터 `run.id=2`로 새 `JobInstance` 실행: 적립 행, 지급 행, 분개 추가 0개
13. 지급 Step 중 계좌 1개의 분개 저장 실패: 그 계좌의 잔액, 거래내역, `interest_payment`, 적립 상태가 모두 지급 전 그대로
14. Job 종료 후 INV-1, INV-2 성립

## 제약
- 이자 계산에 `double`을 쓰지 않는다. 중간값을 원 단위로 반올림하지 않는다: 1절 4번 규칙대로 소수 10자리까지 유지한다.
- Job 안에서 계좌를 전부 `List`로 메모리에 올려 처리하지 않는다: 계좌 수가 100만 개가 되면 힙이 부족해진다.
- `@EnableBatchProcessing`을 붙이지 않는다: Spring Boot 4.1 문서에 따르면 이 애노테이션을 붙이면 Boot의 Batch 자동 구성(JDBC 스키마 초기화 포함)이 물러나고, 저장소 설정을 `@EnableJdbcJobRepository` 속성으로 직접 해야 한다. 붙여야 한다면 이유를 `batch-design.md`에 적는다.
- 배치 처리 중 외부 HTTP 호출을 하지 않는다.

## 힌트
<details>
<summary>힌트 1: 재시작 위치 확인</summary>

Spring Batch Reference 6.0 "Configuring a Step for Restart" 절과 "ItemStream" 절을 읽는다. 재시작 테스트 후 `BATCH_STEP_EXECUTION`의 `READ_COUNT`, `WRITE_COUNT`, `COMMIT_COUNT`, `STATUS` 열을 두 실행에 대해 조회해보면 재시작이 어디서 시작했는지 숫자로 보인다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 M6-5 시나리오 표의 모든 행에 대응하는 테스트가 통과한다
- [ ] 시나리오 1의 테스트가 실지급액 24,347원, 소득세 4,020원, 지방소득세 400원을 assert한다
- [ ] 재시작 테스트(시나리오 10) 후 `SELECT account_id, accrual_date, COUNT(*) FROM interest_accrual GROUP BY account_id, accrual_date HAVING COUNT(*) > 1` 결과가 0행이다
- [ ] `workspace/docs/batch-design.md`에 4절의 구성도, 메타 테이블 조회 결과, reader 선택 이유가 있다
- [ ] PR 본문에 `workspace/docs/test-scenarios/M6-5.md` 표와 기대값 계산식이 붙어 있다

## 생각해볼 질문
1. 적립 원금을 `account.balance`가 아니라 업무일자 기준 분개 합계로 구하게 한 이유는 무엇인가? 배치가 00:05에 돌 때와 03:00에 돌 때 `account.balance`를 쓰면 무엇이 달라지는가?
2. 유니크 제약이 있으면 Spring Batch 재시작 기능 없이도 중복 지급은 막힌다. 그렇다면 `JobRepository`의 재시작 위치는 무엇을 더 해주는가? 계좌 100만 개 기준으로 답한다.
3. 매일 원 단위로 잘라 적립하는 규칙과 이 미션처럼 소수 10자리로 적립하고 월말에 한 번 자르는 규칙을 잔액 1,000원 계좌로 비교하면 한 달 이자가 각각 얼마인가?
4. Phase 8에서 corebank 인스턴스가 3대가 되면, 세 인스턴스의 스케줄러가 같은 시각에 이 Job을 실행한다. JDBC `JobRepository`가 같은 `JobInstance`의 동시 실행을 막아주는가? 막는다면 어떤 예외로 막는가?
