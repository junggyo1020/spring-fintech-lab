# M5-3 JdbcTemplate, Flyway, Testcontainers

> 가이드 수준: L2, 예상 시간: 4~5h, 선행: M5-2

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- M5-2의 저장소와 이체를 `JdbcTemplate` + `@Transactional`로 다시 구현하고, 반복 코드 줄 수 감소량을 M5-2 표에 열을 추가해 보여준다.
- 스키마를 Flyway 마이그레이션 `V1__create_account_and_transaction.sql`로 옮기고, `flyway_schema_history` 행과 `information_schema.TABLE_CONSTRAINTS` 조회로 스키마가 M5-1 명세와 같음을 테스트로 확인한다.
- Testcontainers `mysql:8.4` 컨테이너로 통합 테스트를 실행해, 로컬 `bank-mysql` 컨테이너 없이 `./gradlew test`가 통과하게 만든다.
- `@Transactional` 메서드 안의 `JdbcTemplate` 호출 두 번이 같은 커넥션(`SELECT CONNECTION_ID()` 값 동일)을 쓴다는 것을 테스트로 보여준다.

## 배경
M5-2에서 이체 한 번에 try 블록, catch, `Connection` 파라미터가 여러 개 필요했다. 실무 코드가 이 형태라면 누군가 한 군데에서 `rollback()`을 빠뜨리는 것은 시간 문제다.
스키마도 마찬가지다. 개발자 노트북, CI, 운영 DB에 손으로 DDL을 치면 세 곳의 스키마가 어긋난다. Flyway는 "어떤 마이그레이션이 어디까지 적용됐는지"를 DB 안의 `flyway_schema_history` 테이블에 기록하고, 이미 적용된 파일이 바뀌면 애플리케이션 시작을 거부한다.
테스트가 H2 같은 다른 DB에서 통과해도 MySQL에서 실패할 수 있다 (체크 제약, 락 동작, 에러 코드가 다르다). M5-7~M5-9는 InnoDB 락 동작을 테스트하므로 처음부터 실제 MySQL 8.4 컨테이너로 테스트한다.

## 요구사항
1. **의존성.** README "워크스페이스 만들기"의 M5-3 줄 4개를 추가한다. Spring Boot 4.x에서 Flyway는 `spring-boot-starter-flyway`로 자동 설정되고, MySQL을 쓰려면 `org.flywaydb:flyway-mysql` 모듈도 있어야 한다. Testcontainers 2.x는 아티팩트 이름에 `testcontainers-` 접두어가 붙고, MySQL 컨테이너 클래스는 `org.testcontainers.mysql.MySQLContainer`다 (1.x 블로그 코드의 `org.testcontainers.containers.MySQLContainer<?>`와 다름).
2. **마이그레이션.** `src/main/resources/db/migration/V1__create_account_and_transaction.sql`에 M5-1 `01_schema.sql`의 `CREATE TABLE` 두 개와 인덱스, 제약을 옮긴다. `DROP TABLE` 문과 시드 데이터는 넣지 않는다.
3. **로컬 DB 전환.** 로컬 `bank` DB에는 M5-1에서 손으로 만든 테이블이 있다. 이 상태로 애플리케이션을 처음 실행해 Flyway의 에러(시나리오 7)를 확인한 뒤, `bank` DB의 두 테이블을 지우고 다시 실행해 Flyway가 스키마를 만들게 한다. `spring.flyway.baseline-on-migrate`는 쓰지 않는다.
4. **`lab.bank.persistence.jdbc.JdbcTemplateAccountRepository implements AccountRepository`.** `@Repository` 빈으로 등록한다. 메서드 동작(INSERT/UPDATE 판정, 0행 UPDATE 시 `AccountNotFoundException`, `findAll` 정렬)은 M5-2와 같다. `ResultSet` → `Account` 변환은 `RowMapper<Account>` 하나로 모은다.
5. **`lab.bank.persistence.jdbc.JdbcTemplateTransferService`.** `TransferResult transfer(TransferCommand command)`에 `@Transactional`을 붙인다. 커넥션 획득, `setAutoCommit`, `commit`, `rollback` 코드는 쓰지 않는다. 검증 순서와 예외는 M5-2 `JdbcTransferService`와 같다. Phase 4 API는 아직 메모리 `BankService`, `TransferEngine`을 쓴다 (API를 DB에 연결하는 것은 M5-4).
6. **테스트 컨테이너 설정.** `src/test/java/lab/bank/support/` 아래에 `MySQLContainer`(`mysql:8.4`)를 `@ServiceConnection`으로 등록하는 테스트 설정을 하나 만들고, 모든 `@SpringBootTest`가 이것을 가져다 쓴다. Flyway는 컨테이너에 대해 자동 실행된다. Phase 3~4에서 만든 `@SpringBootTest` 테스트도 이제 `DataSource`가 필요하므로 같은 설정을 가져다 쓰게 고친다 (`@WebMvcTest`는 DB가 필요 없으므로 그대로 둔다).
7. **M5-2 테스트 이전.** M5-2의 시나리오 1~12를 `JdbcTemplateAccountRepository` + `JdbcTemplateTransferService` 대상으로 다시 작성한다 (시나리오 10 "트랜잭션 없는 버전"은 M5-2에만 둔다). 기대 결과는 M5-2와 같고, 예외 클래스만 시나리오 4처럼 바뀐다. M5-2 테스트 자체도 로컬 컨테이너 대신 Testcontainers의 `DataSource`를 쓰도록 옮겨서, `bank-mysql`이 꺼져 있어도 `./gradlew test`가 통과하게 한다.
8. **테스트 격리.** 통합 테스트 메서드, 클래스에 `@Transactional`을 붙이지 않는다. 각 테스트는 `@BeforeEach`에서 `account_transaction`, `account` 순서로 `DELETE` 한다.

## 테스트 시나리오
| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 새 컨테이너로 컨텍스트 시작 | `SELECT version, success FROM flyway_schema_history WHERE version IS NOT NULL` | 1행: `version = '1'`, `success = 1` |
| 2 | 1번 직후 | `information_schema.TABLE_CONSTRAINTS`에서 `TABLE_SCHEMA = DATABASE()`, 테이블별 `CONSTRAINT_NAME`, `CONSTRAINT_TYPE` 조회 | `account` 3행: `PRIMARY`(PRIMARY KEY), `uk_account_number`(UNIQUE), `chk_account_balance_non_negative`(CHECK) / `account_transaction` 4행: `PRIMARY`, `uk_tx_uuid`(UNIQUE), `fk_tx_account`(FOREIGN KEY), `chk_tx_amount_positive`(CHECK) |
| 3 | M5-2 시나리오 1~9, 11, 12의 준비 | 같은 실행을 새 구현으로 | 잔액, 거래 행 수, 도메인 예외가 M5-2 기대 결과와 같다 |
| 4 | A = 100,000, B = 0 | `transfer(A → B, 30,000, memo = "가" × 101자)` | `DataAccessException` 하위 예외 (예상 구체 클래스 `DataIntegrityViolationException`: 실제 클래스를 기록), `getMostSpecificCause()`가 `SQLException`이고 에러 코드 1406. A = 100000.00, B = 0.00, 거래 행 0 |
| 5 | `@Transactional` 메서드 하나를 가진 테스트용 빈 | 그 메서드 안에서 `jdbcTemplate.queryForObject("SELECT CONNECTION_ID()", Long.class)` 2회 | 두 값이 같다. 같은 메서드 안에서 `TransactionSynchronizationManager.isActualTransactionActive()` = `true` |
| 6 | 5번과 같은 빈의 트랜잭션 없는 메서드 | `isActualTransactionActive()`, `TransactionSynchronizationManager.getResource(dataSource)` | `false`, `null` |
| 7 | 로컬 `bank` DB에 M5-1 테이블이 있고 `flyway_schema_history`는 없음 | `./gradlew bootRun` | 시작 실패, 로그에 `Found non-empty schema(s)` … `but no schema history table` 메시지 |
| 8 | 로컬 `bank` DB를 Flyway로 만든 뒤 | `V1__...sql` 파일 끝에 주석 한 줄(`-- changed`)을 추가하고 `./gradlew bootRun` | 시작 실패, `FlywayValidateException`, 메시지에 버전 `1`의 checksum mismatch. 주석을 지우면 다시 정상 시작 |
| 9 | 8번 확인 후 | `V1` 파일을 원래대로 되돌리고 `./gradlew test` | 통과 (Testcontainers는 매번 새 DB라 8번의 문제가 테스트에서는 안 보인다는 점을 기록) |

7~9번은 로컬 수동 실험이다. 실행한 명령과 에러 메시지 첫 3줄을 `docs/m5-3-flyway.md`에 붙인다.

### 반복 코드 줄 수 비교 (M5-2 측정 2 표에 열 추가)

| 항목 | JDBC (M5-2) | JdbcTemplate (M5-3) | 감소량 |
|---|---|---|---|
| 이체 흐름 전체 줄 수 (빈 줄, 주석, import 제외) | | | |
| try 블록 개수 | | | |
| `SQLException`을 잡는 catch 개수 | | | |
| `Connection`을 파라미터로 받는 메서드 개수 | | | |
| `ResultSet` → `Account` 변환 코드 위치 개수 | | | |

## 제약
- 테스트용 DB로 H2 등 다른 DB를 쓰지 않는다: M5-1의 체크 제약 에러 코드(3819), M5-7 이후의 락 동작이 MySQL과 다르다.
- 이미 커밋한 마이그레이션 파일은 수정하지 않는다 (시나리오 8 실험 후 원래대로 되돌린다). 스키마 변경은 새 버전 파일(`V2__...`)로만 한다.
- `spring.flyway.clean-disabled`를 `false`로 바꾸지 않는다. `flyway clean`은 스키마의 모든 객체를 지운다.
- `JdbcTemplateTransferService`에서 `DataSource.getConnection()`을 직접 호출하지 않는다. 직접 얻은 커넥션은 `@Transactional`이 스레드에 묶어 둔 커넥션과 다른 커넥션이다.

## 힌트
<details>
<summary>힌트 1: 컨테이너를 테스트 클래스마다 새로 띄우지 않는 방법</summary>

`@Testcontainers` + `static @Container` 필드는 테스트 클래스 단위로 컨테이너를 띄우고 내린다. 테스트 클래스가 10개면 MySQL이 10번 뜬다.
Spring Boot Reference의 "Testcontainers" 장에서 "Using Service Connections" 절과, 컨테이너를 `@TestConfiguration`의 `@Bean`으로 선언하고 `@Import`하는 예제를 읽는다. 이 방식이 Spring 테스트 컨텍스트 캐시와 함께 쓰일 때 컨테이너가 몇 번 뜨는지 로그(`Creating container for image: mysql:8.4`)로 세어 본다.
</details>

<details>
<summary>힌트 2: 같은 커넥션인지 확인하는 방법</summary>

`TransactionSynchronizationManager.getResource(dataSource)`가 돌려주는 객체의 타입을 출력해 본다 (`ConnectionHolder`).
`DataSourceUtils.getConnection(DataSource)` Javadoc을 읽고, `JdbcTemplate`이 커넥션을 얻을 때 이 메서드를 쓰는지 Spring 소스(`JdbcTemplate.execute`)에서 확인한다.
</details>

## 완료 기준
- [ ] `docker stop bank-mysql` 상태에서 `./gradlew test`가 통과한다 (Docker 데몬은 켜져 있어야 함)
- [ ] 테스트 로그에서 `mysql:8.4` 컨테이너 생성 로그가 전체 테스트 실행 동안 1번만 나온다
- [ ] 시나리오 1~6 테스트와 M5-2에서 옮긴 테스트 11개가 통과한다
- [ ] `docs/m5-3-flyway.md`에 시나리오 7~9의 명령과 에러 메시지가 있다
- [ ] `docs/m5-2-measurements.md`의 줄 수 표에 JdbcTemplate 열과 감소량 열이 채워져 있다

## 생각해볼 질문
1. `JdbcTemplate`이 `SQLException`을 `DataAccessException`(unchecked) 계층으로 바꿔 주는 것은 서비스 코드에 어떤 이득이 있나? MySQL을 PostgreSQL로 바꾸면 에러 코드 1406은 어떻게 되고, 서비스 코드는 무엇을 고쳐야 하나?
2. Flyway가 이미 적용된 마이그레이션의 체크섬 변경을 막는 이유는 무엇인가? 운영 DB에 잘못된 V3가 이미 적용됐다면 V3를 고치는 대신 무엇을 해야 하나?
3. Phase 6에서는 이체 요청 멱등성을 `idempotency_key` 유니크 제약으로 DB에서 보장한다. 그 테이블의 마이그레이션 파일 이름과 유니크 제약 이름을 지금 규칙(M5-1 명명 규칙)으로 미리 정해 본다.
