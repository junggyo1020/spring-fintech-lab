# M5-5 N+1 문제

> 가이드 수준: L2 · 예상 시간: 4~5h · 선행: M5-4

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- "계좌 목록 + 계좌별 거래 건수" 조회에서 N+1을 재현하고, 실행 SQL 수(계좌 11개 → 12개)를 테스트로 고정한다.
- 같은 조회를 fetch join, `@EntityGraph`, `hibernate.default_batch_fetch_size` 세 방식으로 바꾸고 SQL 수·반환 행 수·소요 시간을 비교표로 기록한다.
- `@ManyToOne` 방향 N+1에서 SQL 수가 "1 + 거래 수"가 아니라 "1 + 서로 다른 계좌 수"인 이유를 영속성 컨텍스트로 설명하고 테스트로 보여준다.
- 컬렉션 fetch join과 페이지네이션을 함께 쓸 때 사용하는 Hibernate 버전에서 실제로 나가는 SQL과 경고를 기록하고, 배치 페치로 바꾼 페이지 조회의 SQL 수를 테스트로 고정한다.

## 배경
계좌 목록 화면에 계좌 1,000개와 각 계좌의 거래 건수를 보여준다고 하자. 코드는 `findAll()` 한 줄과 반복문 하나라서 리뷰에서 문제가 안 보인다. 그런데 실행되는 SQL은 1,001개다. 개발 DB의 계좌 10개에서는 아무도 모르다가, 운영에서 응답 시간과 DB 커넥션 점유 시간이 계좌 수에 비례해 늘어난다.
M5-4에서 만든 `Statistics` 측정 방법으로 SQL 수를 테스트에 고정하면, 누군가 연관 매핑이나 조회 메서드를 바꿔 N+1이 다시 생길 때 테스트가 실패한다.

## 요구사항
1. **조회 결과 DTO.** `lab.bank.application.AccountSummary` — `record AccountSummary(String number, String ownerName, int transactionCount)`. 반환 목록은 `number` 오름차순이다.
2. **`lab.bank.application.AccountQueryService`.** 아래 4개 메서드를 만든다. 모두 `@Transactional(readOnly = true)`이고 반환 타입은 `List<AccountSummary>`다.
   - `summariesNaive()` — `findAll()` 후 각 계좌의 `transactions` 컬렉션 크기를 읽는다
   - `summariesFetchJoin()` — JPQL `left join fetch`로 계좌와 거래내역을 한 번에 읽는다
   - `summariesEntityGraph()` — Spring Data 리포지토리 메서드에 `@EntityGraph(attributePaths = "transactions")`
   - `summariesBatch()` — `summariesNaive()`와 같은 코드. 배치 페치 설정(`spring.jpa.properties.hibernate.default_batch_fetch_size`)을 켠 테스트 클래스에서만 측정한다
3. **거래내역 → 계좌 방향 조회.** `List<String> ownerNamesOfAllTransactions()` — 모든 거래내역을 읽고 각 거래의 `getAccount()`에서 예금주 이름을 꺼낸다. 단순 버전과 fetch join 버전 두 개를 만든다.
4. **페이지 조회.** `Page<AccountSummary> summaryPage(int page, int size)` — `number` 오름차순.
   - 1단계: 리포지토리 메서드에 `@EntityGraph(attributePaths = "transactions")`와 `Pageable`을 함께 써서 구현하고 SQL과 로그를 관찰한다 (시나리오 9~10).
   - 2단계: 계좌만 페이지 조회(SQL에 `LIMIT`)하고, 거래 건수는 배치 페치로 읽도록 바꾼다 (시나리오 11~12).
5. **테스트 데이터.** 기본 데이터: 계좌 11개(`110-0000-0001` ~ `110-0000-0011`, 예금주 `고객01` ~ `고객11`). 0001~0010은 거래내역 3건씩(총 30건), 0011은 0건. 측정용 데이터: 계좌 1,000개, 계좌마다 거래내역 10건(총 10,000건). 데이터는 `JdbcTemplate.batchUpdate` 등으로 별도 트랜잭션에서 넣고 커밋한 뒤, `statistics.clear()` 후 측정한다.

## 테스트 시나리오
"SQL 수"는 `Statistics.getPrepareStatementCount()`. 배치 크기는 테스트 클래스에 `@TestPropertySource(properties = "spring.jpa.properties.hibernate.default_batch_fetch_size=...")`로 준다. 기본 데이터(계좌 11개, 거래 30건) 기준이다.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 배치 설정 없음 | `summariesNaive()` | SQL 수 12 (계좌 1 + 컬렉션 11), `getCollectionFetchCount()` 11, 결과 11행, 0001의 건수 3, 0011의 건수 0 |
| 2 | 배치 설정 없음 | `summariesFetchJoin()` | SQL 수 1, 결과 11행 (중복 계좌 없음), 0011의 건수 0 |
| 3 | 배치 설정 없음 | 2번 쿼리의 `left join fetch`를 `join fetch`로 바꿔 실행 | SQL 수 1, 결과 10행 (거래 없는 0011이 빠짐) — 확인 후 `left`로 되돌린다 |
| 4 | 배치 설정 없음 | `summariesEntityGraph()` | SQL 수 1, 결과 11행 |
| 5 | 배치 크기 100 | `summariesBatch()` | SQL 수 2 (계좌 1 + `IN` 절 컬렉션 조회 1), 결과 11행 |
| 6 | 배치 크기 5 | `summariesBatch()` | SQL 수 4 (계좌 1 + 컬렉션 3번: 11 ÷ 5 올림 = 3), 결과 11행 |
| 7 | 배치 설정 없음 | `ownerNamesOfAllTransactions()` 단순 버전 / fetch join 버전 | 단순: SQL 수 11 (거래 1 + 서로 다른 계좌 10), 결과 30개 / fetch join: SQL 수 1, 결과 30개 |
| 8 | 배치 설정 없음, `AccountTransaction.account`를 잠시 `FetchType.EAGER`로 변경 | 거래내역 `findAll()`만 호출 (계좌 접근 없음) | SQL 수 11 (접근하지 않아도 즉시 계좌 10개 조회). 확인 후 `LAZY`로 되돌린다 |
| 9 | 배치 설정 없음 | 1단계 `summaryPage(0, 5)` | 결과 5행 (0001~0005, 건수 각 3), `getTotalElements()` 11. SQL 로그에 `LIMIT`이 있는지, 로그에 `HHH90003004` 경고가 있는지 기록 (Boot 4.1.2의 Hibernate 7.4.13에서 확인한 결과: 경고 없음, SQL 수 2 = 계좌만 `limit ?,?`로 자른 파생 테이블에 거래를 `left join`한 SELECT 1 + count 1) |
| 10 | `spring.jpa.properties.hibernate.query.fail_on_pagination_over_collection_fetch=true` | 9번과 같은 호출 | 9번에서 경고가 나왔다면 예외 발생 (예외 클래스 기록), 경고가 없었다면 9번과 같은 결과 (Hibernate 7.4.13에서는 예외 없이 9번과 같은 결과). 어느 쪽이었는지 Hibernate 버전과 함께 기록 |
| 11 | 배치 크기 100 | 2단계 `summaryPage(0, 5)` | SQL 수 3 (계좌 `LIMIT` 조회 1 + count 1 + 컬렉션 `IN` 조회 1), 결과 5행, 건수 각 3, `getTotalElements()` 11, `getTotalPages()` 3 |
| 12 | 배치 크기 100 | 2단계 `summaryPage(2, 5)` | SQL 수 2 (count 조회 생략), 결과 1행 (0011, 건수 0), `getTotalElements()` 11 |
| 13 | 측정용 데이터 (계좌 1,000, 거래 10,000) | `summariesNaive()` / `summariesFetchJoin()` / `summariesEntityGraph()` / 배치 크기 100의 `summariesBatch()` | SQL 수 각각 1,001 / 1 / 1 / 11. 결과는 모두 1,000행, 각 건수 10 |

계산식:
- 6번: 1 + ⌈11 / 5⌉ = 1 + 3 = 4
- 12번: Spring Data는 마지막 페이지에서 "offset 10 + 결과 1행 < offset + size 5"이면 전체 건수를 10 + 1 = 11로 계산하고 count 쿼리를 생략한다
- 13번 배치: 1 + ⌈1,000 / 100⌉ = 11

### 측정표 (`docs/m5-5-n-plus-one.md`)
측정 규칙: 측정용 데이터에서 메서드 호출 1회를 1회 실행으로 보고, 워밍업 3회 후 5회 측정해 중앙값을 기록한다. 매 실행 전 영속성 컨텍스트는 비어 있어야 한다 (새 트랜잭션). 표 위에 JDK 버전, CPU 코어 수, OS, MySQL 버전, Hibernate 버전을 적는다.

| 방식 | SQL 수 | 반환 계좌 수 | DB에서 받은 행 수 (SQL 로그로 계산) | 소요 시간 중앙값(ms) |
|---|---|---|---|---|
| 단순 (N+1) | | | | |
| fetch join | | | | |
| `@EntityGraph` | | | | |
| 배치 크기 100 | | | | |

"DB에서 받은 행 수"는 fetch join이 계좌 1,000행이 아니라 조인 결과 10,000행을 받는다는 점을 보이기 위한 열이다.

## 제약
- 시나리오 1~13은 SQL 수를 `assertThat(...).isEqualTo(...)`로 고정한다. "N+1이 없다"를 SQL 로그를 눈으로 보고 판단하지 않는다.
- 연관 컬렉션을 `FetchType.EAGER`로 바꿔서 해결하지 않는다 (시나리오 8 실험 후 되돌린다).
- `@OneToMany` 컬렉션 두 개 이상을 한 쿼리에서 fetch join하지 않는다. 이 미션은 컬렉션 하나만 다루지만, Phase 6에서 컬렉션이 늘어날 때 Hibernate의 `MultipleBagFetchException`을 검색해 이유를 확인한다.
- 측정용 데이터(10,000건) 테스트는 기본 `./gradlew test`에서 빠지도록 JUnit `@Tag("measure")`를 붙이고, Gradle에서 태그로 따로 실행한다.

## 힌트
<details>
<summary>힌트 1: 배치 크기가 바뀌면 SQL 수가 왜 그렇게 변하는가</summary>

배치 페치는 지연 로딩 컬렉션 하나를 초기화할 때, 같은 영속성 컨텍스트 안에서 아직 초기화되지 않은 같은 종류의 컬렉션을 최대 N개까지 `WHERE account_id IN (?, ?, ...)` 한 번으로 함께 읽는다.
Hibernate ORM User Guide의 "Fetching" 장에서 "Batch fetching" 절을 읽고, SQL 로그에서 `IN` 절의 `?` 개수를 세어 본다.
</details>

<details>
<summary>힌트 2: 페이지 조회와 컬렉션 fetch join</summary>

계좌 5개를 원해도 조인 결과는 "계좌 × 거래" 행이라서 SQL의 `LIMIT 5`는 거래 5행을 자를 뿐 계좌 5개를 보장하지 못한다. 이 때문에 Hibernate는 버전에 따라 경고(`HHH90003004`)와 함께 전체를 읽어 메모리에서 자르거나, 다른 SQL 형태로 해결한다.
`./gradlew dependencies --configuration runtimeClasspath | grep hibernate-core`로 버전을 확인하고, 그 버전의 Hibernate 마이그레이션 가이드에서 "pagination"과 "collection fetch"를 검색한다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 시나리오 1~12 테스트가 통과한다
- [ ] `./gradlew test -PincludeTags=measure`(또는 직접 정한 태그 실행 방법)로 시나리오 13과 측정이 실행되고, `docs/m5-5-n-plus-one.md`에 측정표와 환경 정보가 있다
- [ ] `docs/m5-5-n-plus-one.md`에 시나리오 9~10의 관찰 결과(Hibernate 버전, `LIMIT` 유무, 경고 유무, 예외 클래스)가 있다
- [ ] `docs/m5-5-n-plus-one.md`에 "어떤 조회에 어떤 방식을 쓰겠는가"를 목록 조회 / 단건 상세 조회 / 페이지 조회 3가지 경우로 나눠 적었다

## 생각해볼 질문
1. 시나리오 7에서 SQL이 31개가 아니라 11개인 이유는 무엇인가? 거래 30건이 모두 서로 다른 계좌에 속했다면 몇 개가 되나?
2. fetch join은 SQL 1개로 끝나지만 측정표의 "DB에서 받은 행 수"는 가장 많다. 계좌당 거래가 10,000건인 계좌가 섞여 있다면 fetch join과 배치 페치 중 무엇을 고르겠는가?
3. Phase 6의 거래내역 조회 API는 계좌 하나에 거래가 500,000건까지 쌓이는 것을 전제로 한다 (이 미션의 가정). M4-5의 커서 페이지네이션과 이 미션의 결과를 함께 놓고, 거래내역 조회에 `@OneToMany` 컬렉션을 쓰지 않고 별도 쿼리로 조회해야 하는 이유를 적어 본다.
