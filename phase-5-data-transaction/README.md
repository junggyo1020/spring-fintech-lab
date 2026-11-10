# Phase 5: SQL, JDBC, JPA, 트랜잭션, DB 락 (4주)

> 가이드 수준: L2, 선행: Phase 4 완료, 이 Phase의 workspace 시작 방법: Phase 4 workspace 복사 + MySQL 8.4, JPA, Flyway 추가

## 학습 목표
이 Phase를 끝내면 다음을 할 수 있다.
- 같은 이체 기능을 JDBC → JdbcTemplate → JPA 세 가지로 구현하고, 각 단계에서 사라진 코드 줄 수를 표로 보여준다.
- `@Transactional`이 프록시, `PlatformTransactionManager`, `TransactionSynchronizationManager`를 거쳐 커넥션을 스레드에 묶는 과정을 그림 없이 순서대로 말하고, 롤백 규칙, 전파, self-invocation, readOnly, 커넥션 풀 고갈을 M5-6의 시나리오 18개로 재현한다.
- MySQL 8.4 InnoDB에서 dirty read, non-repeatable read, phantom, lost update를 두 세션 교차 실행으로 재현하고, 각 단계의 결과를 시간순 표(T1~Tn)로 기록한다.
- 100건 동시 출금을 비관적 락, 낙관적 락, 조건부 UPDATE로 각각 통과시키고 처리량, 실패 수, 재시도 수를 측정표로 비교한다.
- InnoDB 데드락 로그(`LATEST DETECTED DEADLOCK`)를 읽어 어떤 트랜잭션이 어떤 인덱스 레코드를 기다렸는지 표로 정리하고, 인덱스 유무에 따라 `performance_schema.data_locks` 행 수가 102개에서 4개로 바뀌는 것을 보여준다.

## 이 Phase의 결과물
Phase 4의 웹 API와 컨트롤러는 그대로 두고, `BankService`, `TransferEngine` 안의 메모리 저장(`Map`, `Ledger`)을 MySQL로 바꾼다 (M5-4에서 연결). 도메인 이름(`Money`, `Account`, `AccountNumber`, `Transaction`, `TransactionType`, `BankException`, `ErrorCode`)과 Phase 2의 `TransferEngine`, `TransferCommand`, `TransferResult`는 이름을 바꾸지 않는다. 패키지도 Phase 4 구조(`common/ money/ account/ ledger/ interest/ application/ transfer/ web/ security/ config/`)를 이어 쓴다.

```
phase-5-data-transaction/workspace/
├── build.gradle.kts
├── sql/                                  # M5-1, M5-7, M5-9 (mysql CLI로 실행하는 SQL)
│   ├── 01_schema.sql
│   ├── 02_seed.sql
│   ├── 03_queries.sql
│   ├── 04_transaction_and_constraints.sql
│   └── lab/                              # M5-7, M5-9 실험용
├── docs/                                 # 측정표, 기록표 (각 미션의 완료 기준에 경로 명시)
└── src/
    ├── main/java/lab/bank/
    │   ├── common/ money/ interest/ config/ web/ security/   # Phase 4 그대로 (컨트롤러 변경 없음)
    │   ├── account/           # Account(M5-2 id 추가, M5-4 JPA 매핑), AccountRepository(M5-2 신규)
    │   ├── ledger/            # Transaction(record 유지), AccountTransaction 엔티티(M5-4)
    │   ├── application/       # BankService(M5-4에서 DB 저장소 사용), AccountQueryService(M5-5)
    │   ├── transfer/          # Phase 2 TransferEngine 인터페이스, JpaTransferEngine(M5-4)
    │   ├── persistence/
    │   │   ├── jdbc/          # M5-2 JdbcAccountRepository, JdbcTransferService, M5-3 JdbcTemplate 버전
    │   │   └── jpa/           # M5-4 Spring Data 리포지토리, JpaAccountRepository
    │   ├── txlab/             # M5-6 트랜잭션 함정 실험용 빈
    │   └── dblock/            # M5-8 출금 서비스 4종, M5-9 락 순서 이체, 데드락 재시도
    │                          # (Phase 2의 concurrency/ 패키지와 섞지 않는다)
    ├── main/resources/
    │   ├── application.yml
    │   └── db/migration/      # V1__create_account_and_transaction.sql, V2__add_account_version.sql
    └── test/java/lab/bank/    # Testcontainers 통합 테스트 (M5-3 이후)
```

## 핵심 개념 정리 (미션 전에 읽기)

### 1. SQL과 인덱스 기초
InnoDB 테이블은 **기본 키 순서로 정렬된 B+tree(클러스터드 인덱스)** 자체다. 행 데이터는 기본 키 B+tree의 리프에 들어 있다. 보조 인덱스(secondary index)의 리프에는 "인덱스 컬럼 값 + 기본 키 값"만 있어서, 보조 인덱스로 찾은 뒤 기본 키로 한 번 더 찾아간다.

| 질의 형태 | 인덱스가 없을 때 | `(account_id, occurred_at)` 인덱스가 있을 때 |
|---|---|---|
| `WHERE account_id = 7` | 테이블 전체(10만 행) 스캔 | 인덱스에서 account_id=7 구간만 읽음 |
| `WHERE account_id = 7 ORDER BY occurred_at DESC LIMIT 20` | 전체 스캔 + 정렬(`Using filesort`) | 인덱스 순서를 거꾸로 읽고 20행에서 멈춤 |
| `WHERE occurred_at >= ?` (선두 컬럼 없음) | 전체 스캔 | 이 인덱스로는 구간 탐색을 못 함 (선두 컬럼 규칙) |

금융 시스템에서 인덱스는 속도만의 문제가 아니다. 6절에서 보듯이 `UPDATE`와 `SELECT ... FOR UPDATE`는 **읽은 인덱스 레코드마다 락을 건다**. 인덱스가 없으면 한 계좌를 잠그려다 테이블의 모든 계좌를 잠근다.

시간 구간은 반열린 구간(`>= 시작 AND < 다음날 0시`)으로 쓴다. `BETWEEN '2026-01-01' AND '2026-01-31'`은 `'2026-01-31 00:00:00'`까지만 포함해서 1월 31일 23시 59분 거래를 놓친다 (M5-1 시나리오 3에서 확인).

### 2. JDBC, JdbcTemplate, JPA가 각각 숨기는 것

| 작업 | JDBC (M5-2) | JdbcTemplate (M5-3) | JPA (M5-4) |
|---|---|---|---|
| 커넥션 얻기, 반납 | 직접 `getConnection()`, `close()` | 숨김 | 숨김 |
| `PreparedStatement` 생성, 파라미터 바인딩 | 직접 | 직접 (SQL과 인자만 전달) | 숨김 (JPQL 또는 메서드 이름) |
| `ResultSet` → 객체 변환 | 직접 반복문 | `RowMapper` 한 개 | 숨김 (엔티티 매핑) |
| `SQLException` 처리 | checked 예외를 직접 잡음 | `DataAccessException` 계층으로 변환 | 같음 |
| 트랜잭션 경계 | `setAutoCommit(false)`, `commit()`, `rollback()` 직접 | `@Transactional` | `@Transactional` |
| 같은 트랜잭션의 메서드끼리 커넥션 공유 | 메서드 파라미터로 `Connection`을 넘김 | 스레드에 묶인 커넥션을 자동 사용 | 같음 |
| 변경 감지 (UPDATE 문 생성) | 없음 | 없음 | 커밋 시 스냅샷과 비교해 자동 UPDATE |

추상화가 올라갈수록 코드는 줄지만 **실행되는 SQL이 눈에 안 보인다**. 그래서 M5-4부터는 SQL 로그와 Hibernate 통계(`Statistics.getPrepareStatementCount()`)로 실행된 SQL 개수를 테스트에서 직접 센다.

### 3. 영속성 컨텍스트
영속성 컨텍스트는 `EntityManager` 하나가 관리하는 "엔티티 식별자 → 엔티티 인스턴스" 맵이다. Spring에서는 기본적으로 **트랜잭션 하나 = 영속성 컨텍스트 하나**다 (`spring.jpa.open-in-view=false`일 때).

| 기능 | 동작 | M5-4에서 확인할 관찰값 |
|---|---|---|
| 1차 캐시 | 같은 트랜잭션에서 `findById(1L)`을 두 번 호출하면 SELECT는 1번 | `getPrepareStatementCount()` 증가량 1 |
| 동일성 보장 | 같은 행을 두 번 읽으면 같은 인스턴스 (`==`가 true) | JPQL로 두 번 읽어도 SELECT는 2번, 인스턴스는 같음 |
| 변경 감지 | 커밋(flush) 시 로딩 시점 스냅샷과 비교해 바뀐 엔티티만 UPDATE | 출금 후 커밋 → UPDATE 1번, 출금 후 같은 금액 입금 → UPDATE 0번 |
| 쓰기 지연 | UPDATE, DELETE는 flush 때까지 모아둠 | 단, `IDENTITY` 기본 키 엔티티의 INSERT는 `persist()` 즉시 실행 |
| flush 시점 | 커밋 직전, 그리고 JPQL 실행 직전(같은 테이블을 조회할 때) | 출금 후 JPQL 조회 → UPDATE가 SELECT보다 먼저 로그에 찍힘 |

트랜잭션이 끝나면 엔티티는 준영속(detached) 상태가 되어, 값을 바꿔도 DB에 반영되지 않는다.

### 4. `@Transactional` 동작 원리
`@Transactional`은 Phase 3 M3-4에서 만든 프록시와 같은 구조다. Spring Boot는 기본으로 CGLIB(클래스 기반) 프록시를 만든다.

```
호출자 → [프록시] TransactionInterceptor
            1. PlatformTransactionManager.getTransaction(정의)
               - JpaTransactionManager가 커넥션을 얻고 setAutoCommit(false)
               - TransactionSynchronizationManager에 (DataSource → ConnectionHolder)를
                 현재 스레드의 ThreadLocal 맵으로 등록
            2. 실제 객체의 메서드 호출
               - JdbcTemplate, EntityManager는 같은 스레드의 ConnectionHolder를 찾아 같은 커넥션을 씀
            3. 정상 반환 → commit / RuntimeException, Error → rollback / checked 예외 → commit
            4. ThreadLocal에서 리소스 제거, 커넥션을 풀에 반납
```

이 구조에서 바로 나오는 결과 네 가지:
- 같은 클래스 안에서 `this.other()`로 부르면 프록시를 거치지 않아 트랜잭션이 시작되지 않는다 (self-invocation).
- 커넥션은 **스레드**에 묶인다. `@Transactional` 메서드 안에서 다른 스레드(`ExecutorService`, `CompletableFuture`)로 넘긴 작업은 그 트랜잭션에 참여하지 않는다. 동시성 테스트에서 테스트 메서드에 `@Transactional`을 붙이면 작업 스레드는 테스트가 넣은 데이터를 보지 못한다.
- 트랜잭션이 열려 있는 동안 커넥션 하나를 계속 점유한다. 트랜잭션 안에서 3초 걸리는 외부 API를 부르면 커넥션도 3초 동안 묶인다 (M5-6).
- `private` 메서드는 프록시가 가로챌 수 없다. Spring Framework 6.0부터 클래스 기반 프록시에서는 `protected`와 package-private 메서드도 트랜잭션이 적용된다 (단, 외부에서 프록시를 통해 호출될 때만).

롤백 규칙의 기본값은 "`RuntimeException`과 `Error`는 롤백, checked 예외는 커밋"이다. Spring Framework 6.2부터 `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)`로 이 기본값을 바꿀 수 있다.

### 5. 격리 수준과 이상 현상 (MySQL 8.4 InnoDB 기준)
MySQL의 기본 격리 수준은 `REPEATABLE READ`다 (`SELECT @@transaction_isolation` → `REPEATABLE-READ`).
InnoDB는 일반 `SELECT`(**일관된 읽기, consistent read**)와 `SELECT ... FOR UPDATE`, `UPDATE`, `DELETE`(**잠금 읽기, locking read**)를 다르게 처리한다.

| 격리 수준 | dirty read | non-repeatable read | phantom (일반 SELECT) | phantom (잠금 읽기) | lost update (읽고-계산-쓰기) |
|---|---|---|---|---|---|
| READ UNCOMMITTED | 발생 | 발생 | 발생 | 발생 (갭 락 없음) | 발생 |
| READ COMMITTED | 없음 | 발생 | 발생 | 발생 (갭 락 없음) | 발생 |
| REPEATABLE READ | 없음 | 없음 (스냅샷) | 없음 (스냅샷) | 없음 (next-key 락이 INSERT를 막음) | **발생** (MySQL은 감지하지 않음) |
| SERIALIZABLE | 없음 | 없음 | 없음 | 없음 | 발생하지 않는 대신 데드락(에러 1213)으로 한쪽이 롤백 |

REPEATABLE READ의 스냅샷은 `START TRANSACTION` 시점이 아니라 **그 트랜잭션의 첫 번째 일관된 읽기 시점**에 만들어진다.
잠금 읽기는 스냅샷이 아니라 **가장 최근에 커밋된 값**을 읽는다. 그래서 RR에서 일반 `SELECT`는 150,000을, 바로 다음 `SELECT ... FOR UPDATE`는 160,000을 돌려줄 수 있다 (M5-7 실험 3).
SERIALIZABLE에서는 autocommit이 꺼진 트랜잭션의 일반 `SELECT`가 `SELECT ... FOR SHARE`로 바뀐다.

### 6. InnoDB 락
| 락 | `data_locks.LOCK_MODE` 표기 | 무엇을 막는가 |
|---|---|---|
| 테이블 의도 락 | `IX` (`LOCK_TYPE = TABLE`) | 행 락을 걸기 전에 테이블에 먼저 걸림. `LOCK TABLES ... WRITE`와만 충돌 |
| 레코드 락 | `X,REC_NOT_GAP` | 그 인덱스 레코드 하나의 수정, 잠금 읽기 |
| 갭 락 | `X,GAP` | 레코드 사이 빈 구간에 INSERT |
| next-key 락 | `X` | 레코드 + 그 앞의 갭 (REPEATABLE READ의 기본 잠금 단위) |
| INSERT 의도 락 | `INSERT_INTENTION` 포함 | INSERT가 갭 락에 막혀 기다릴 때 보임 |

락은 **행이 아니라 탐색한 인덱스 레코드**에 걸린다.
- 유니크 인덱스 등호 검색으로 1건을 찾으면: 테이블 `IX` 1개 + 인덱스 레코드 `X,REC_NOT_GAP` + (보조 인덱스라면) 기본 키 레코드 `X,REC_NOT_GAP`.
- 인덱스 없는 컬럼으로 검색하면: 기본 키 전체를 스캔하면서 **모든 레코드와 supremum(마지막 레코드 뒤의 가상 레코드)**에 `X`가 걸린다.

락 관찰 SQL (root 계정으로 별도 세션에서 실행):
```sql
SELECT ENGINE_TRANSACTION_ID, OBJECT_NAME, INDEX_NAME, LOCK_TYPE, LOCK_MODE, LOCK_STATUS, LOCK_DATA
FROM performance_schema.data_locks
ORDER BY ENGINE_TRANSACTION_ID, LOCK_TYPE DESC, INDEX_NAME, LOCK_DATA;

SELECT REQUESTING_ENGINE_TRANSACTION_ID, BLOCKING_ENGINE_TRANSACTION_ID
FROM performance_schema.data_lock_waits;
```

락 대기와 데드락은 다르게 끝난다.

| 상황 | MySQL 에러 | 롤백 범위 | 관련 설정 (8.4 기본값) |
|---|---|---|---|
| 락 대기 시간 초과 | `1205` Lock wait timeout exceeded | **해당 문장만** 롤백, 트랜잭션은 열려 있음 | `innodb_lock_wait_timeout = 50`(초), `innodb_rollback_on_timeout = OFF` |
| 데드락 감지 | `1213` Deadlock found when trying to get lock | **트랜잭션 전체** 롤백 | `innodb_deadlock_detect = ON` |

Spring에서는 둘 다 `PessimisticLockingFailureException`의 하위 클래스로 변환된다. 구체 클래스(`CannotAcquireLockException` 등)는 접근 기술(JdbcTemplate/JPA)과 예외 변환기에 따라 다르므로 테스트는 상위 클래스로 잡고, 실제 클래스는 기록한다. `DeadlockLoserDataAccessException`은 Spring Framework 6.0.3부터 deprecated다.

### 7. 동시성 제어 3종
Phase 2에서 메모리로 겪은 lost update가 DB에서 다시 나온다. `@Transactional`은 원자성(전부 커밋 또는 전부 롤백)을 줄 뿐, 두 트랜잭션이 같은 값을 읽고 각자 계산해 덮어쓰는 것을 막지 않는다.

| 방식 | SQL 모양 | 충돌 시 동작 | 맞는 상황 |
|---|---|---|---|
| 비관적 락 | `SELECT ... FOR UPDATE` 후 `UPDATE` | 뒤에 온 트랜잭션이 커밋까지 대기 | 같은 행에 충돌이 잦을 때 (인기 계좌) |
| 낙관적 락 | `UPDATE ... SET version = version + 1 WHERE id = ? AND version = ?` | 0행 수정 → 예외 → 애플리케이션이 재시도 | 충돌이 드물고 대기를 피하고 싶을 때 |
| 조건부 UPDATE | `UPDATE account SET balance = balance - ? WHERE number = ? AND balance >= ?` | 0행 수정 = 잔액 부족 | 검증 규칙이 SQL 한 문장으로 표현될 때 |

Phase 2 M2-5의 CAS 루프와 낙관적 락은 같은 원리다 (값 대신 `version` 컬럼을 비교).

### 8. 트랜잭션 경계와 커넥션 풀
HikariCP의 기본 `maximumPoolSize`는 10이다. 트랜잭션 하나가 커넥션 하나를 처음부터 끝까지 점유하므로, 동시에 열린 트랜잭션 수가 풀 크기를 넘으면 나머지는 `connectionTimeout`(기본 30,000ms) 동안 기다리다 실패한다. `REQUIRES_NEW`는 바깥 트랜잭션의 커넥션을 쥔 채로 두 번째 커넥션을 요구하므로, 풀 크기 1에서는 반드시 실패한다 (M5-6 시나리오 11).

## 워크스페이스 만들기

```bash
# 1. Phase 4 workspace 복사 (Phase 4 원본은 그대로 둔다)
cp -R phase-4-spring-web/workspace/. phase-5-data-transaction/workspace/
cd phase-5-data-transaction/workspace

# 2. MySQL 8.4 컨테이너 실행 (M5-1부터 사용)
docker run -d --name bank-mysql \
  -e MYSQL_ROOT_PASSWORD=root \
  -e MYSQL_DATABASE=bank \
  -e MYSQL_USER=bank \
  -e MYSQL_PASSWORD=bank \
  -p 3306:3306 \
  mysql:8.4

# 3. 접속 확인 (애플리케이션 계정)
docker exec -it bank-mysql mysql -ubank -pbank bank
# 락 관찰, SHOW ENGINE INNODB STATUS는 PROCESS 권한이 필요하므로 root로 접속
docker exec -it bank-mysql mysql -uroot -proot
```

MySQL 8.0은 2026년 4월에 지원이 끝났다. 이 Phase는 LTS인 8.4를 쓴다. 로컬 3306 포트를 이미 다른 MySQL이 쓰고 있으면 `-p 13306:3306`으로 바꾸고 아래 URL의 포트도 바꾼다.
컨테이너를 `docker rm`으로 지우면 데이터도 사라진다. `docker stop bank-mysql` / `docker start bank-mysql`은 데이터를 유지한다.

`build.gradle.kts`의 `dependencies`에 추가할 줄과 추가하는 미션 (버전은 Spring Boot 4.1.x 의존성 관리가 정한다):

```kotlin
dependencies {
    // M5-2
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    runtimeOnly("com.mysql:mysql-connector-j")

    // M5-3
    implementation("org.springframework.boot:spring-boot-starter-flyway")
    implementation("org.flywaydb:flyway-mysql")          // MySQL은 스타터 외에 DB별 모듈이 필요
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
    testImplementation("org.testcontainers:testcontainers-junit-jupiter")  // Testcontainers 2.x 이름
    testImplementation("org.testcontainers:testcontainers-mysql")          // 1.x의 org.testcontainers:mysql

    // M5-4
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
}
```

`src/main/resources/application.yml` (M5-2에서 datasource, M5-3에서 flyway, M5-4에서 jpa 부분을 추가):

```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/bank
    username: bank
    password: bank
  flyway:
    enabled: true            # M5-3부터
  jpa:                       # M5-4부터
    open-in-view: false
    hibernate:
      ddl-auto: validate     # 스키마는 Flyway만 만든다. Hibernate는 검증만
    properties:
      hibernate:
        format_sql: true
        generate_statistics: true   # 테스트에서 SQL 개수를 세기 위해

logging:
  level:
    org.hibernate.SQL: debug                 # 실행 SQL
    org.hibernate.orm.jdbc.bind: trace       # 바인딩 파라미터 (Hibernate 6 이상 카테고리)
```

접속 시 `Public Key Retrieval is not allowed` 오류가 나면 로컬 개발용 URL에만 `?allowPublicKeyRetrieval=true&useSSL=false`를 붙인다.
Testcontainers 테스트(M5-3 이후)는 Docker 데몬이 켜져 있어야 실행된다.

## 주차별 계획

| 주 | 미션 | 개념 학습 범위 |
|---|---|---|
| 1주 | M5-1, M5-2, M5-3 | 핵심 개념 1~2절, 『Real MySQL 8.0』 1권 4장 |
| 2주 | M5-4, M5-5 | 핵심 개념 3절, 『자바 ORM 표준 JPA 프로그래밍』 3장, 8장, 10장(페치 조인), 15장 |
| 3주 | M5-6, M5-7 | 핵심 개념 4~5절, Spring Framework Reference "Transaction Management", 『Real MySQL 8.0』 1권 5장 |
| 4주 | M5-8, M5-9 | 핵심 개념 6~8절, MySQL 8.4 Reference Manual "InnoDB Locking and Transaction Model", 『Real MySQL 8.0』 1권 8장, 10장 |

미션 예상 시간 합계 40~56h (중앙값 48h). 주 10~15시간 기준 4주다.
주별 합계: 1주 11~16h, 2주 10~13h, 3주 9~13h, 4주 10~14h. 1주 차 상한(16h)이 주 15시간을 넘으므로, 1주 차에 15시간을 쓰고도 M5-3이 남으면 남은 부분을 2주 차로 넘긴다(2주 차 상한 13h).

## 미션

| 미션 | 주제 | 예상 시간 |
|---|---|---|
| [M5-1](missions/M5-1-sql-basics.md) | SQL 기초 (DDL, DML, JOIN, 집계, 제약 조건) | 3~5h |
| [M5-2](missions/M5-2-raw-jdbc.md) | JDBC 맨손 구현과 수동 트랜잭션 | 4~6h |
| [M5-3](missions/M5-3-jdbctemplate-flyway-testcontainers.md) | JdbcTemplate, Flyway, Testcontainers | 4~5h |
| [M5-4](missions/M5-4-jpa-persistence-context.md) | JPA 전환과 영속성 컨텍스트, Phase 4 API 연결 | 6~8h |
| [M5-5](missions/M5-5-n-plus-one.md) | N+1 문제 | 4~5h |
| [M5-6](missions/M5-6-transaction-pitfalls.md) | 트랜잭션 함정 | 6~8h |
| [M5-7](missions/M5-7-isolation-level-lab.md) | 격리 수준 실험실 | 3~5h |
| [M5-8](missions/M5-8-db-concurrency-control.md) | DB 동시성 제어 3종 비교 | 6~8h |
| [M5-9](missions/M5-9-db-deadlock-index-explain.md) | DB 데드락과 인덱스, 실행계획 | 4~6h |

## 읽을거리
- 『Real MySQL 8.0』 1권: 4장 아키텍처(4.2 InnoDB 스토리지 엔진), 5장 트랜잭션과 잠금, 8장 인덱스, 10장 실행 계획
- 『자바 ORM 표준 JPA 프로그래밍』(김영한): 3장 영속성 관리, 4장 엔티티 매핑, 8장 프록시와 연관관계 관리, 10장 객체지향 쿼리 언어(10.2.6 페치 조인), 15장 고급 주제와 성능 최적화(15.4 성능 최적화의 N+1 문제)
- MySQL 8.4 Reference Manual: 17.7 "InnoDB Locking and Transaction Model" (17.7.1 InnoDB Locking, 17.7.2.1 Transaction Isolation Levels, 17.7.2.3 Consistent Nonlocking Reads, 17.7.3 Locks Set by Different SQL Statements, 17.7.5 Deadlocks), 10.8.2 "EXPLAIN Output Format", Performance Schema 장의 "Performance Schema Lock Tables" 절 (`data_locks`, `data_lock_waits`)
- Spring Framework Reference: Data Access › "Transaction Management" (Understanding the Spring Framework Transaction Abstraction, Declarative Transaction Management › Using `@Transactional`, Transaction Propagation, Rolling Back a Declarative Transaction)
- Spring Boot Reference: "Testcontainers" (Service Connections), How-to Guides › "Database Initialization" (Execute Flyway Database Migrations on Startup)
- Hibernate ORM 7 User Guide: "Persistence Contexts", "Flushing", "Fetching"(Batch fetching), "Statistics"

장, 절 번호는 판본에 따라 다를 수 있다. 번호가 다르면 위에 적은 절 제목으로 찾는다.

## 완료 기준
- [ ] `./gradlew test`가 Docker 데몬이 켜진 상태에서 Phase 5 테스트를 모두 통과한다 (Testcontainers `mysql:8.4`)
- [ ] `docs/` 아래에 M5-2 줄 수 비교표, M5-5 N+1 비교표, M5-7 교차 실행 기록표, M5-8 동시성 비교표, M5-9 데드락 분석표, EXPLAIN 기록표가 있다
- [ ] "`@Transactional`만 붙이면 동시성이 해결된다"가 틀렸음을 M5-8의 lost update 테스트(최종 잔액 > 0, 거래 행 100개)로 보여줄 수 있다
- [ ] Phase 4의 API(`POST /transfers` 등)를 애플리케이션 재시작 후 다시 호출해도 잔액이 유지된다 (MySQL에 저장됨)
- [ ] [레벨 진단](../docs/self-check.md) Phase 5 항목을 말로 설명할 수 있다
