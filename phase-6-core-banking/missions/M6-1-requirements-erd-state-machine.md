# M6-1 요구사항·ERD·상태 머신 설계

> 가이드 수준: L3 · 예상 시간: 5~7h · 선행: M5-9

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 유스케이스 8개 이상, 업무 규칙 15개 이상, 예외 상황 12개 이상에 각각 번호(`UC-`, `BR-`, `EX-`)를 붙인 요구사항 정의서를 쓴다.
- 이 문서의 필수 테이블과 제약을 모두 담은 ERD를 Mermaid `erDiagram`으로 그리고, 같은 내용의 Flyway `V1__init_schema.sql`이 MySQL 8.4에 적용되는 것을 Testcontainers 테스트로 보여준다.
- 계좌 상태 4개와 전이 7개를 표로 정의하고, 표에 없는 전이가 예외로 거부되는 것을 단위 테스트로 보여준다.

## 배경
코어뱅킹 사고의 상당수는 코드보다 규칙이 먼저 비어 있어서 생긴다. "정지 계좌에 입금이 되는가", "해지 계좌로 이체가 들어오면 어떻게 되는가"를 아무도 정하지 않으면 개발자마다 다르게 구현하고, 그 차이는 운영에서 돈이 걸린 문의로 드러난다.
Phase 1~5에서는 미션 문서가 규칙을 정해줬다. Phase 6부터는 학습자가 규칙을 먼저 문서로 정하고, 이후 미션의 테스트 이름에 규칙 번호(`BR-07` 등)를 붙인다.
Phase 5 M5-9까지는 `lab.bank` 프로젝트 하나에 기능을 더해왔다. 이 미션은 새 프로젝트 `lab.corebank`의 첫 커밋으로, 테이블과 상태 규칙을 먼저 고정한다.

## 요구사항

### 1. 요구사항 정의서 `workspace/docs/requirements.md`
1. 유스케이스(`UC-01`~) 8개 이상. 최소 다음을 포함한다: 고객 등록, 계좌 개설, 현금 입금, 현금 출금, 당행이체, 거래내역 조회, 계좌 해지, 휴면 해제. 각 유스케이스는 "행위자 / 사전 조건 / 기본 흐름(번호 단계) / 사후 조건(바뀌는 테이블과 컬럼)"을 적는다.
2. 업무 규칙(`BR-01`~) 15개 이상. 이 문서 3절의 규칙과 아래 금액 규칙을 반드시 옮겨 적고, 나머지는 학습자가 정한다.
   - 금액은 원화 정수다. 소수점이 있는 금액(`"1000.5"`)은 400으로 거부한다.
   - 거래 금액은 1원 이상 1,000,000,000원 이하다 (이 미션의 규칙). 0원, 음수, 상한 초과는 400으로 거부한다.
   - 잔액은 0원 미만이 될 수 없다. 출금·이체 출금 후 잔액이 음수가 되는 요청은 422 `INSUFFICIENT_BALANCE`로 거부하고 잔액은 바뀌지 않는다.
   - 출금계좌와 입금계좌가 같은 당행이체는 422 `SAME_ACCOUNT_TRANSFER`로 거부한다.
3. 예외 상황(`EX-01`~) 12개 이상. 각 항목은 "조건 / HTTP 상태 / 에러 코드 / 데이터 변화 없음 여부"를 적는다. 400(형식 오류), 404(계좌 없음), 409(멱등 처리 중), 422(업무 규칙 위반)를 모두 1개 이상 포함한다.
4. 용어 사전: 업무일자, 고객 주도 거래, 정상 잔액 방향, 반대 분개를 이 문서의 정의대로 적는다.

### 2. ERD `workspace/docs/erd.md`
Mermaid `erDiagram` 코드 블록 1개와, 테이블별 "컬럼 / 타입 / NULL 허용 / 제약" 표를 쓴다. 컬럼은 학습자가 정하되 아래 테이블과 제약은 반드시 있어야 한다.

| 테이블 | 반드시 있어야 하는 제약 |
|---|---|
| `customer` | PK |
| `product` | 상품 코드 유니크, 연이율 컬럼 `DECIMAL(7,6)` (예: 3.5% → `0.035000`) |
| `account` | 계좌번호 유니크, `customer_id`·`product_id` FK, `status` NOT NULL, `balance` `DECIMAL(19,0)` NOT NULL, 마지막 고객 주도 거래 시각 컬럼 |
| `account_status_history` | `account_id` FK, 변경 전 상태(최초 개설 시 NULL), 변경 후 상태, 사유 코드, 변경 시각 |
| `ledger_account` (계정과목) | 계정 코드 유니크, 계정 유형(자산·부채·자본·수익·비용), 정상 잔액 방향(차변·대변) |
| `journal_entry` (분개) | 업무일자, 분개 유형, 반대 분개 대상 `reversal_of_entry_id` 유니크(NULL 허용) |
| `journal_line` (분개 라인) | `journal_entry_id`·`ledger_account_id` FK, 고객 계좌 `account_id`(NULL 허용), 차변/대변 구분, 금액 `DECIMAL(19,0)` |
| `account_transaction` (고객용 거래내역) | `account_id` FK, 거래 유형, 금액, 거래 후 잔액, 업무일자, 연결된 `journal_entry_id` |
| `idempotency_record` | (`customer_id`, `idempotency_key`) 복합 유니크 |
| `transfer_limit` | `account_id` 유니크, 1회 한도, 1일 한도 |

- 고객 거래내역 테이블 이름은 `transaction`이 아니라 `account_transaction`으로 한다. `TRANSACTION`은 MySQL 키워드라 쿼리마다 백틱이 필요해진다.
- 금액 컬럼에 `FLOAT`, `DOUBLE`을 쓰지 않는다.
- M6-4 이후 미션이 테이블을 추가할 때는 `V2__`, `V3__` 마이그레이션으로 추가하고 `erd.md`도 같은 커밋에서 고친다.

### 3. 계좌 상태 머신 `workspace/docs/state-machine.md`
아래 상태·전이·허용 거래 규칙은 **이 미션의 규칙**이다(실제 은행의 휴면·정지 제도를 옮긴 것이 아니다). `state-machine.md`에 그대로 옮기고 Mermaid `stateDiagram-v2`로 그린다.

상태 4개: `ACTIVE`(정상), `SUSPENDED`(정지), `DORMANT`(휴면), `CLOSED`(해지). 계좌 개설 시 상태는 `ACTIVE`다.

| 전이 | 출발 → 도착 | 조건 | 사유 코드 |
|---|---|---|---|
| T1 | `ACTIVE` → `SUSPENDED` | 비밀번호 연속 5회 오류 (M6-4에서 구현) | `PASSWORD_LOCKED` |
| T2 | `ACTIVE` → `SUSPENDED` | 관리자 정지 요청 (사고 신고 등) | `ADMIN_SUSPEND` |
| T3 | `SUSPENDED` → `ACTIVE` | 관리자 해제 요청. 비밀번호 오류 횟수를 0으로 만든다 | `ADMIN_RESUME` |
| T4 | `ACTIVE` → `DORMANT` | 휴면 판정 규칙(아래)을 만족 | `DORMANCY` |
| T5 | `DORMANT` → `ACTIVE` | 고객의 휴면 해제 요청 | `DORMANCY_RELEASE` |
| T6 | `ACTIVE` → `CLOSED` | 고객의 해지 요청, 잔액 0원, 진행 중인 타행이체(`REQUESTED`·`SENT`·`UNKNOWN`) 0건 | `CUSTOMER_CLOSE` |
| T7 | (없음) → `ACTIVE` | 계좌 개설 | `OPEN` |

- 표에 없는 전이(예: `SUSPENDED` → `CLOSED`, `DORMANT` → `CLOSED`, `CLOSED` → 무엇이든, `SUSPENDED` → `DORMANT`)는 422 `INVALID_STATUS_TRANSITION`으로 거부하고, 상태와 이력은 바뀌지 않는다.
- 같은 상태로의 전이(`ACTIVE` → `ACTIVE`)도 표에 없으므로 거부한다.
- T6에서 잔액이 0원이 아니면 422 `BALANCE_NOT_ZERO`로 거부한다.
- 전이가 성공하면 `account.status` 변경과 `account_status_history` 행 1개 추가가 같은 DB 트랜잭션에서 일어난다.

**휴면 판정 규칙 (이 미션의 규칙):** 기준일 D(업무일자)에 대해, 마지막 고객 주도 거래일 L(Asia/Seoul 날짜)이 `L + 365일 < D`이면 휴면 대상이다.
- 고객 주도 거래: 계좌 개설, 현금 입금, 현금 출금, 이 계좌가 출금계좌인 이체, 휴면 해제. 이자 지급과 다른 계좌에서 들어온 이체 입금은 고객 주도 거래가 아니다.
- 예: L = 2025-11-10이면 D = 2026-11-10은 휴면 대상이 아니고(2025-11-10 + 365일 = 2026-11-10), D = 2026-11-11은 휴면 대상이다.
- 휴면 판정은 `ACTIVE` 계좌만 한다. 휴면 전환을 실행하는 배치는 M6-6에서 만든다. 이 미션은 판정 규칙과 전이를 도메인 코드와 테스트로 만든다.

상태별 허용 거래 (이 미션의 규칙, 허용 안 됨은 422 `ACCOUNT_STATUS_NOT_ALLOWED`):

| 거래 | `ACTIVE` | `SUSPENDED` | `DORMANT` | `CLOSED` |
|---|---|---|---|---|
| 현금 입금 | 허용 | 허용 | 거부 | 거부 |
| 이체 입금 (입금계좌로서) | 허용 | 허용 | 거부 | 거부 |
| 현금 출금, 이체 출금 | 허용 | 거부 | 거부 | 거부 |
| 이자 지급 (M6-5) | 허용 | 허용 | 허용 | 거부 |
| 잔액·거래내역 조회 | 허용 | 허용 | 허용 | 허용 |

### 4. 코드
1. Flyway `src/main/resources/db/migration/V1__init_schema.sql`: 2절의 테이블과 제약 전부.
2. `lab.corebank.account.AccountStatus` 와 상태 전이를 수행하는 도메인 메서드. 전이 규칙은 한 곳(예: `AccountStatus` 또는 전이 규칙 클래스)에만 있다. 서비스 계층에 `if (status == ...)` 분기가 흩어지지 않는다.
3. 휴면 대상 판정 메서드: 입력은 기준일 `LocalDate`, 출력은 `boolean`.
4. 상태별 허용 거래 판정 메서드: 입력은 거래 종류, 출력은 허용 여부 또는 예외.
5. 이 미션에서 HTTP API는 만들지 않는다(M6-3에서 만든다).

## 직접 작성할 테스트 시나리오
`workspace/docs/test-scenarios/M6-1.md`에 표(번호 / Given / When / Then)를 쓰고 리뷰를 받은 뒤 구현한다. Then 열은 구체 값(상태 이름, 예외 클래스명 또는 에러 코드, 이력 행 개수)으로 쓴다.

반드시 포함할 경우 (최소 14개 행):
1. T1~T7 각각의 성공 경우 (7개 행), 각 행의 Then에 `account_status_history`에 추가되는 행의 from/to/사유 코드를 적는다
2. 표에 없는 전이 3개 이상: `SUSPENDED` → `CLOSED`, `CLOSED` → `ACTIVE`, `ACTIVE` → `ACTIVE`
3. 잔액 1원인 계좌의 해지 요청
4. 휴면 판정 경계 3개: L + 364일, L + 365일, L + 366일 (L = 2025-11-10으로 고정)
5. 윤년이 끼는 휴면 판정 1개: L = 2027-03-01, D = 2028-03-01 (`L + 365일` = 2028-02-29이므로 휴면 대상이다)
6. 이자 지급만 있고 고객 주도 거래가 없는 계좌의 휴면 판정
7. 상태별 허용 거래 표에서 "거부" 칸 3개 이상
8. Flyway 마이그레이션이 Testcontainers MySQL 8.4에 적용되고, `idempotency_record`에 같은 (`customer_id`, `idempotency_key`)를 2번 INSERT하면 두 번째가 실패하는 경우

## 제약
- 상태 값을 문자열 리터럴로 비교하지 않는다(`"ACTIVE".equals(...)` 금지) — 오타가 컴파일 오류로 잡히지 않는다.
- JPA `ddl-auto`는 `validate`만 쓴다 — 스키마의 원본은 Flyway 마이그레이션 하나여야 한다.
- 현재 날짜를 `LocalDate.now()`로 직접 읽지 않는다. 기준일은 메서드 인자나 주입받은 `Clock`으로 받는다 — 휴면 경계 테스트를 날짜에 상관없이 반복 실행하기 위해서다.
- 이 미션에서 MySQL 트리거, 저장 프로시저를 만들지 않는다(M6-2에서 분개 테이블 트리거만 만든다).

## 힌트
<details>
<summary>힌트 1: 전이 규칙을 한 곳에 두는 방법</summary>

`java.util.EnumMap<AccountStatus, Set<AccountStatus>>` 또는 `enum` 상수마다 허용 도착 상태를 돌려주는 메서드를 두는 두 방식이 있다. 두 방식 중 "사유 코드까지 검사해야 할 때" 어느 쪽이 더 바뀌기 쉬운지 비교해보고 고른다.
</details>

## 완료 기준
- [ ] `workspace/docs/requirements.md`에 `UC-` 8개 이상, `BR-` 15개 이상, `EX-` 12개 이상이 있고, 2절의 금액 규칙 4개가 `BR-` 번호로 들어 있다
- [ ] `workspace/docs/erd.md`의 Mermaid 블록이 GitHub 미리보기에서 렌더링되고, 2절 표의 테이블 10개와 제약이 모두 보인다
- [ ] `workspace/docs/state-machine.md`에 3절의 전이표, 휴면 판정 규칙, 허용 거래 표가 있다
- [ ] `./gradlew test`에서 M6-1 시나리오 표의 모든 행에 대응하는 테스트가 통과한다 (테스트 이름 또는 `@DisplayName`에 시나리오 번호 포함)
- [ ] Testcontainers 테스트 로그에 Flyway가 `V1__init_schema.sql`을 적용했다는 줄(`Successfully applied 1 migration`)이 보인다
- [ ] PR 본문에 `workspace/docs/test-scenarios/M6-1.md` 표가 붙어 있다

## 생각해볼 질문
1. 휴면 판정에서 "이체 입금"을 고객 주도 거래에서 뺀 이유는 무엇인가? 넣는다면 어떤 계좌가 영원히 휴면이 되지 않는가?
2. `account.balance` 컬럼을 두지 않고 매번 분개 라인 합계로 잔액을 계산하는 설계와 비교하면, 조회 성능과 정합성 검증 측면에서 각각 무엇을 얻고 잃는가? (M6-6 대사와 연결)
3. 상태 전이를 `UPDATE account SET status = 'CLOSED' WHERE id = ?`로 하면 동시에 들어온 입금과 해지가 겹칠 때 무엇이 일어날 수 있는가? 이 경합을 막는 방법을 M5-8의 3가지 방법 중 하나로 고르고 이유를 적는다.
4. Phase 7의 주문도 `접수 → 부분체결 → 전량체결 / 취소` 같은 상태 머신이다. 계좌 상태 머신과 달리 주문 상태 전이는 초당 5,000번 일어날 수 있다. 전이 이력을 매번 테이블에 INSERT하는 방식이 Phase 7에서도 그대로 통할까?
