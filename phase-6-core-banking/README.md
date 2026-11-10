# Phase 6: 코어뱅킹 프로젝트 (4주)

> 가이드 수준: L3, 선행: Phase 5 완료, 이 Phase의 workspace 시작 방법: Spring Initializr로 새로 생성 (Phase 5 코드는 참고만)

## 학습 목표
이 Phase를 끝내면 다음을 할 수 있다.
- 요구사항 정의서, ERD, 계좌 상태 전이표를 먼저 쓰고, 그 문서의 규칙 번호를 테스트 이름에 붙여 구현한다.
- 모든 돈의 움직임을 차변 합계 = 대변 합계인 분개로 기록하고, 계좌 잔액과 원장 합계가 같은지 배치로 대사한다.
- 같은 `Idempotency-Key` 요청을 동시에 2번, 재시도로 10번 보내도 돈이 한 번만 움직이는 것을 통합 테스트로 보여준다.
- 대외기관 호출이 타임아웃으로 끝난 이체를 `UNKNOWN` 상태로 두고, 조회 API로 확정하거나 반대 분개로 보상한다.
- 애플리케이션 인스턴스 2대에서 JVM 락이 깨지는 상황을 재현하고, Redis 분산락과 DB 락의 차이를 측정표로 비교한다.

평가 기준은 기능 개수가 아니라 **불변식**이다. 아래 4개는 Phase 6의 모든 미션이 끝난 시점에도, 각 미션의 테스트가 끝난 시점에도 성립해야 한다.

| # | 불변식 | 처음 검증하는 미션 |
|---|---|---|
| INV-1 | 모든 분개에서 Σ차변 금액 == Σ대변 금액 | M6-2 |
| INV-2 | Σ(고객 계좌의 `balance`) == 원장의 `고객예금` 계정 잔액 (Σ대변 − Σ차변) | M6-3 |
| INV-3 | 같은 고객이 같은 `Idempotency-Key`로 보낸 요청은 몇 번 와도 분개를 최대 1개만 만든다 | M6-3 |
| INV-4 | `타행이체미정산` 계정 잔액 == 상태가 `REQUESTED`, `SENT`, `UNKNOWN`인 타행이체 금액의 합계 (타임아웃이 나도 돈은 이 계정에 남아 있고 사라지지 않는다) | M6-7 |

## 이 Phase의 결과물

```
phase-6-core-banking/workspace/
├── corebank/                       ← Spring Boot 애플리케이션 (M6-1 ~ M6-8)
│   ├── build.gradle.kts
│   ├── compose.yaml                ← MySQL 8.4 + Redis 8
│   └── src/main/java/lab/corebank/
│       ├── common/                 ← Money, ErrorCode, BusinessException, Clock 설정
│       ├── customer/
│       ├── product/
│       ├── account/                ← Account, AccountStatus, 상태 이력
│       ├── ledger/                 ← LedgerAccount, JournalEntry, JournalLine (M6-2)
│       ├── transfer/               ← 입출금, 당행이체 API (M6-3)
│       ├── idempotency/            ← 멱등 레코드 (M6-3)
│       ├── limit/                  ← 이체 한도, 비밀번호 오류 횟수 (M6-4)
│       ├── interest/               ← 이자 배치 Job (M6-5)
│       ├── closing/                ← 일 마감, 대사 Job (M6-6)
│       ├── interbank/              ← 타행이체, 대외기관 클라이언트 (M6-7)
│       └── lock/                   ← 락 전략 (M6-8)
├── fake-kftc/                      ← 가짜 대외기관 서버, 별도 Spring Boot 앱 (M6-7)
└── docs/
    ├── requirements.md             ← M6-1
    ├── erd.md                      ← M6-1 (Mermaid erDiagram)
    ├── state-machine.md            ← M6-1
    ├── ledger-design.md            ← M6-2
    ├── idempotency-design.md       ← M6-3
    ├── concurrency-report.md       ← M6-4
    ├── batch-design.md             ← M6-5, M6-6
    ├── interbank-design.md         ← M6-7
    ├── distributed-lock-report.md  ← M6-8
    └── test-scenarios/M6-{N}.md    ← 미션마다 직접 작성하는 테스트 시나리오 표
```

## 핵심 개념 정리 (미션 전에 읽기)

### 1. 계정계 개요
은행 시스템에서 **계정계**는 계좌 잔액, 입출금, 이체, 이자, 원장을 처리하는 영역이다. 고객 화면, 상품 안내, 마케팅을 처리하는 영역(채널계, 정보계)과 구분한다.
계정계의 버그는 "화면이 이상하다"가 아니라 "돈이 생기거나 사라졌다"로 끝난다. 그래서 계정계는 다음 3가지를 설계 단계에서 정한다.

| 질문 | Phase 6에서 정하는 곳 |
|---|---|
| 잔액이 맞다는 것을 무엇으로 증명하는가 | 복식부기 분개(M6-2)와 대사 배치(M6-6) |
| 같은 요청이 두 번 오면 무엇이 일어나는가 | 멱등 레코드(M6-3) |
| 결과를 모르는 대외 호출은 어떻게 끝내는가 | `UNKNOWN` 상태와 조회, 보상(M6-7) |

Phase 6에서는 고객 인증을 다루지 않는다(Phase 4 M4-7에서 다뤘다). 이 Phase의 규칙: 요청자는 HTTP 헤더 `X-Customer-Id`(양의 정수)로 식별하고, 헤더가 없으면 400을 돌려준다.
업무일자는 이 Phase의 규칙으로 **Asia/Seoul 달력 날짜와 같다**(주말, 공휴일 구분 없음). 현재 시각은 항상 주입받은 `java.time.Clock`에서 읽는다.

### 2. 복식부기
은행 입장에서 고객 예금은 **부채**(고객에게 돌려줘야 할 돈), 보유 현금은 **자산**이다.
자산 증가, 부채 감소, 비용 발생은 **차변**, 자산 감소, 부채 증가, 수익 발생은 **대변**에 적는다. 모든 분개는 차변 합계 = 대변 합계다.

| 거래 | 차변 | 대변 |
|---|---|---|
| 고객 A 현금 10,000원 입금 | 현금(자산) 10,000 | 고객예금 A(부채) 10,000 |
| A → B 3,000원 당행이체 | 고객예금 A 3,000 | 고객예금 B 3,000 |
| A에게 이자 100원 지급 (세금 무시) | 이자비용 100 | 고객예금 A 100 |
| A에게 이자 10,000원 지급, 원천징수 1,540원 | 이자비용 10,000 | 고객예금 A 8,460 / 예수소득세 1,400 / 예수지방소득세 140 |
| A → 타행 C 5,000원 이체 (대외기관 정산 전) | 고객예금 A 5,000 | 타행이체미정산(부채) 5,000 |

(출처: 이 레포 `fintech-domain-facts` 6절, 확인일 2026-11-10. 계정과목 이름은 이 레포에서 정한 이름이고, 실제 은행 계정과목 체계는 은행마다 다르다.)

계정 잔액은 정상 잔액 방향으로 계산한다. 자산, 비용 계정은 Σ차변 − Σ대변, 부채, 자본, 수익 계정은 Σ대변 − Σ차변이다.
위 표의 5행을 모두 기록하면 고객예금 A의 잔액은 10,000 − 3,000 + 100 + 8,460 − 5,000 = 10,560원이다.
잘못 기록한 분개는 고치거나 지우지 않는다. 차변과 대변을 뒤집은 **반대 분개**를 새로 기록해 효과를 없앤다. 그래야 "언제 무엇이 잘못 기록됐고 언제 바로잡았는가"가 원장에 남는다.

### 3. 멱등성
모바일 앱은 응답을 못 받으면 같은 요청을 다시 보낸다. 서버가 첫 요청을 이미 처리했다면 두 번째 요청은 이체를 한 번 더 만든다.
**멱등성**은 같은 요청을 여러 번 보내도 결과가 한 번 보낸 것과 같은 성질이다. 클라이언트는 요청마다 새 UUID를 `Idempotency-Key` 헤더에 담고, 재시도할 때는 같은 값을 보낸다.

| 서버가 받은 요청 | 처리 |
|---|---|
| 처음 보는 키 | 처리하고 응답을 키와 함께 저장 |
| 처리가 끝난 키 + 같은 본문 | 저장된 응답을 그대로 돌려줌 (돈은 안 움직임) |
| 처리 중인 키 | 409 |
| 처리가 끝난 키 + 다른 본문 | 422 (키 재사용 오류) |

Phase 4 M4-4는 이 판단을 메모리에서 했다. 메모리 저장은 서버가 재시작되거나 인스턴스가 2대가 되면 깨진다. Phase 6은 판단 근거를 DB 유니크 제약에 둔다. 세부 규칙은 M6-3에서 정한다.

### 4. 한도와 시간 경계
이체 한도는 사고(계정 탈취, 오입력)가 났을 때 피해 금액의 상한이다. 한도는 "1회 한도"와 "1일 누적 한도" 두 가지로 둔다.
1일 누적은 "어느 날짜에 속한 이체인가"를 정해야 계산된다. 서버 JVM 기본 시간대가 UTC이면 한국 시각 오전 0시~9시 이체가 전날로 집계된다.
그래서 날짜는 항상 `Clock`의 `ZoneId`(Asia/Seoul)로 `LocalDate`를 만들어 구한다. 테스트에서는 시각을 23:59:59.999와 00:00:00.000으로 바꿔 끼울 수 있는 `Clock`을 쓴다.
1일 누적 한도는 동시성 문제이기도 하다. 남은 1일 한도 1,000,000원에 600,000원 이체 2건이 동시에 오면 "읽고-비교하고-쓰기"가 겹쳐 둘 다 통과할 수 있다. Phase 5 M5-8의 3가지 방법 중 하나로 막는다.

### 5. 배치와 재시작
이자 계산처럼 매일 밤 모든 계좌를 처리하는 작업은 API가 아니라 배치로 한다. Spring Batch의 용어는 다음과 같다.

| 용어 | 뜻 |
|---|---|
| `Job` | 배치 작업 1개 (예: 일 이자 적립) |
| `JobInstance` | `Job` + 식별 파라미터(예: `businessDate=2026-11-10`) 조합 1개 |
| `JobExecution` | `JobInstance`를 실행한 시도 1번. 실패 후 재시작하면 같은 `JobInstance`에 `JobExecution`이 하나 더 생긴다 |
| 청크(chunk) | 읽기 → 처리 → 쓰기를 N건 단위로 묶어 한 트랜잭션으로 커밋하는 단위 |

1,000개 계좌를 청크 크기 100으로 처리하다 250번째에서 실패하면 200건은 커밋되어 있다. 재시작은 201번째부터 해야 하고, 앞의 200건을 다시 처리하면 이자가 두 번 지급된다.
Spring Batch는 마지막으로 커밋한 위치를 `JobRepository`(DB 테이블)에 저장해 재시작 위치를 정한다. 그래도 "같은 계좌, 같은 날짜에 이자가 두 번 들어가지 않는다"는 DB 유니크 제약으로 한 번 더 막는다.
Spring Boot 4.1.x가 관리하는 Spring Batch는 6.0.x다(2026-11-10 확인, Boot 4.1.2 → Batch 6.0.6). Spring Batch 6의 `DefaultBatchConfiguration`은 기본으로 DB를 쓰지 않는 `ResourcelessJobRepository`를 구성한다. 이 저장소는 재시작 정보를 DB에 남기지 않으므로, Phase 6은 `spring-boot-starter-batch-jdbc`로 JDBC `JobRepository`를 쓴다.

### 6. 대사
**대사(reconciliation)** 는 두 기록(원장 합계 vs 계좌 잔액, 당행 vs 대외기관)을 비교해 불일치를 찾는 작업이다.
계좌 테이블의 `balance` 컬럼은 조회를 빠르게 하려고 둔 값이고, 원장(분개 라인)의 합계와 항상 같아야 한다. 둘 중 하나만 바뀌는 버그(분개 없이 잔액만 UPDATE, 롤백 누락)는 API 테스트로 잘 드러나지 않는다.
일 마감 배치는 매일 계좌마다 `balance`와 원장 합계를 비교하고, 다르면 불일치 리포트 테이블에 행을 남긴다. 대사는 불일치를 **고치지 않는다**. 원인을 사람이 확인한 뒤 반대 분개로 바로잡는다.
대사 배치가 실제로 불일치를 찾는지는 정상 데이터로는 확인할 수 없다. M6-6에서 테스트가 일부러 행 1개를 망가뜨리고 배치가 그 행을 찾는지 확인한다.

### 7. 대외 연동의 불확실성 (`UNKNOWN`)
타행이체는 금융결제원(KFTC) 전자금융공동망을 거친다. 당행 서버가 요청을 보내고 응답을 기다리다 타임아웃이 나면, 세 가지 중 무엇이 일어났는지 알 수 없다.

| 실제로 일어난 일 | 당행이 보는 것 |
|---|---|
| 요청이 대외기관에 도착하지 않음 | 타임아웃 |
| 도착했고 처리됨, 응답만 유실 | 타임아웃 |
| 도착했고 아직 처리 중 | 타임아웃 |

이때 "실패"로 보고 고객 돈을 돌려주면 2행에서 돈이 두 번 나간다(상대 은행에도 입금, 고객에게도 환불). "성공"으로 보면 1행에서 돈이 사라진다.
그래서 타임아웃은 실패도 성공도 아닌 `UNKNOWN` 상태로 두고, 대외기관의 조회 API로 결과를 확인한 뒤에만 확정한다. 확인 전까지 돈은 `타행이체미정산` 계정에 머문다.
재시도는 "요청이 도착하지 않았다"가 확실한 경우(연결 실패, 대외기관이 처리 전 거절한 503)에만 한다. 서킷 브레이커는 대외기관이 계속 실패할 때 새 요청을 미리 거절해, 결과를 모르는 이체가 계속 쌓이는 것을 막는다.

### 8. 분산락의 한계
`synchronized`, `ReentrantLock`(Phase 2)은 한 JVM 안의 스레드만 막는다. 인스턴스가 2대면 각 JVM이 자기 락을 따로 가지므로 서로를 막지 못한다.
Redis 분산락(Redisson `RLock`)은 락을 JVM 밖 Redis에 둔다. 하지만 락에는 **만료 시간(lease)** 이 있다. 락을 잡은 스레드가 GC 정지나 느린 쿼리로 만료 시간보다 오래 멈추면, 락은 풀리고 다른 인스턴스가 같은 락을 잡는다. 이때 두 인스턴스가 동시에 같은 계좌를 수정한다.
Martin Kleppmann은 이 문제를 **펜싱 토큰**(락을 잡을 때마다 증가하는 번호를 저장소가 검사해, 옛 번호의 쓰기를 거부)으로 설명한다. Redis 락만으로는 저장소(MySQL)가 옛 락 보유자의 쓰기를 거부하지 않는다.
Phase 6에서 돈의 정합성을 지키는 마지막 장치가 무엇인지는 M6-8의 측정 결과로 학습자가 결정하고 설계 문서에 근거를 적는다.

## 워크스페이스 만들기

### 1. 프로젝트 생성
<https://start.spring.io>에서 다음 값으로 생성해 `phase-6-core-banking/workspace/corebank/`에 압축을 푼다.

| 항목 | 값 |
|---|---|
| Project | Gradle - Kotlin |
| Spring Boot | 4.1.x 중 최신 (2026-11-10 기준 4.1.2) |
| Group / Artifact | `lab` / `corebank` |
| Package name | `lab.corebank` |
| Java | 21 |

생성 후 `build.gradle.kts`의 `dependencies` 블록을 아래와 같이 맞춘다. 버전이 없는 좌표는 Spring Boot BOM이 버전을 정한다.

```kotlin
dependencies {
    // M6-1 ~ M6-3
    implementation("org.springframework.boot:spring-boot-starter-webmvc")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-flyway")
    implementation("org.flywaydb:flyway-mysql")
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    runtimeOnly("com.mysql:mysql-connector-j")

    // M6-4: 비밀번호 해시
    implementation("org.springframework.security:spring-security-crypto")

    // M6-5, M6-6: Spring Batch + JDBC JobRepository
    implementation("org.springframework.boot:spring-boot-starter-batch-jdbc")

    // M6-7: 대외기관 HTTP 호출, 서킷 브레이커
    implementation("org.springframework.boot:spring-boot-starter-restclient")
    implementation("io.github.resilience4j:resilience4j-spring-boot4:2.4.0")
    implementation("org.springframework.boot:spring-boot-starter-aspectj")

    // M6-8: Redis 분산락
    implementation("org.redisson:redisson-spring-boot-starter:4.8.0")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-starter-webmvc-test")
    testImplementation("org.springframework.boot:spring-boot-starter-batch-jdbc-test")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
    testImplementation("org.testcontainers:testcontainers-junit-jupiter")
    testImplementation("org.testcontainers:testcontainers-mysql")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
```

버전 메모 (2026-11-10 Maven Central 확인):
- Spring Boot 4.1.2 BOM: Spring Framework 7.0.10, Spring Batch 6.0.6, Flyway 12.4.0, Testcontainers 2.0.5.
- Spring Boot 4에서 `spring-boot-starter-web`은 `spring-boot-starter-webmvc`로 바뀌었다(이전 이름은 deprecated). AOP 스타터 이름은 `spring-boot-starter-aspectj`다.
- Testcontainers 2.x는 모듈 이름에 `testcontainers-` 접두사가 붙고(`org.testcontainers:testcontainers-mysql`), `MySQLContainer` 클래스는 `org.testcontainers.mysql` 패키지에 있다. 1.x 기준 블로그 코드의 `org.testcontainers.containers.MySQLContainer`를 그대로 쓰지 않는다.
- Resilience4j는 2.4.0부터 Spring Boot 4용 모듈 `resilience4j-spring-boot4`를 제공한다. `resilience4j-spring-boot3`를 쓰지 않는다.
- Redisson 4.8.0 스타터는 Spring Boot 4.1용 `redisson-spring-data-41` 모듈을 끌어온다.
- Redis 의존성(M6-8)과 Resilience4j 의존성(M6-7)은 해당 미션을 시작할 때 추가해도 된다. Redisson 스타터를 넣으면 애플리케이션 시작 시 Redis 연결을 시도하므로, M6-8 전에 넣었다면 `compose.yaml`의 Redis도 띄워 둔다. 같은 이유로 Redisson 스타터를 넣은 뒤의 `@SpringBootTest`는 Redis가 필요하다. CI에도 Redis가 없으므로 테스트에서는 Testcontainers `GenericContainer("redis:8")`(포트 6379)에 `@ServiceConnection(name = "redis")`를 붙여 띄운다. Redisson 4.8.0 스타터가 이 연결 정보와 `spring.data.redis.host`, `port`를 읽는 것, 기본 `lockWatchdogTimeout`이 30,000ms인 것을 Boot 4.1.2에서 확인했다(2026-11-10).
- M0-3 CI는 `phase-*/workspace` 바로 아래에 `build.gradle.kts`가 있을 때만 `./gradlew test`를 실행한다. Phase 6의 빌드 파일은 `workspace/corebank/`와 `workspace/fake-kftc/`에 있으므로, CI 반복문에 이 두 디렉터리를 추가한다. CI의 `./gradlew test`는 `external` 태그 테스트(가짜 대외기관이 떠 있어야 하는 테스트)를 실행하지 않는다(M6-7 "직접 작성할 테스트 시나리오"의 Gradle 설정).

### 2. 로컬 MySQL, Redis (`compose.yaml`)

```yaml
services:
  mysql:
    image: mysql:8.4
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: corebank
      MYSQL_USER: corebank
      MYSQL_PASSWORD: corebank
      TZ: Asia/Seoul
    ports:
      - "3306:3306"
    command: ["--log-bin-trust-function-creators=1"]
  redis:
    image: redis:8
    ports:
      - "6379:6379"
```

```bash
cd phase-6-core-banking/workspace/corebank
docker compose up -d
docker compose ps        # mysql, redis 둘 다 running
docker compose exec mysql mysql -ucorebank -pcorebank corebank -e "SELECT VERSION();"   # 8.4.x
```

`--log-bin-trust-function-creators=1`은 M6-2에서 Flyway로 트리거를 만들 때 `ERROR 1419 (HY000): You do not have the SUPER privilege and binary logging is enabled`가 나는 것을 막는다. Testcontainers로 띄우는 MySQL에도 같은 옵션을 준다(`withCommand`).

### 3. `application.yml` 기본값

```yaml
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/corebank
    username: corebank
    password: corebank
  jpa:
    hibernate:
      ddl-auto: validate
    open-in-view: false
  batch:
    jdbc:
      initialize-schema: never   # Batch 메타 테이블은 Flyway 마이그레이션으로 만든다 (M6-5)
    job:
      enabled: false             # 애플리케이션 시작 시 Job 자동 실행 끔
```

### 4. 가짜 대외기관 (M6-7에서 생성)
`phase-6-core-banking/workspace/fake-kftc/`에 Spring Initializr로 두 번째 프로젝트를 만든다(Group `lab`, Artifact `fake-kftc`, Package `lab.fakekftc`, 의존성 `spring-boot-starter-webmvc` 하나). 포트는 9095다(Phase 8에서 Prometheus가 9090을 쓴다). 동작 규칙은 M6-7 문서에 있다.

## 주차별 계획

| 주 | 미션 | 개념 학습 범위 |
|---|---|---|
| 1주 | M6-1, M6-2 | 이 README 1~2절, DDIA 1판 7장 "Transactions" 중 "The Meaning of ACID" 절 다시 읽기 |
| 2주 | M6-3, M6-4 | 이 README 3~4절, IETF Idempotency-Key 초안 2절, Stripe 멱등성 글 |
| 3주 | M6-5, M6-6 | 이 README 5~6절, Spring Batch Reference "The Domain Language of Batch", "Configuring a JobRepository", "Chunk-oriented Processing" |
| 4주 | M6-7, M6-8 | 이 README 7~8절, Resilience4j CircuitBreaker 문서, Kleppmann 분산락 글, DDIA 1판 8장 |

## 미션

| 미션 | 주제 | 예상 시간 |
|---|---|---|
| [M6-1](missions/M6-1-requirements-erd-state-machine.md) | 요구사항, ERD, 상태 머신 설계 | 5~7h |
| [M6-2](missions/M6-2-double-entry-journal.md) | 복식부기 분개 엔진 | 4~6h |
| [M6-3](missions/M6-3-deposit-transfer-idempotency.md) | 입출금, 당행이체와 멱등성 | 6~8h |
| [M6-4](missions/M6-4-limits-password-concurrency.md) | 이체 한도, 비밀번호 오류 정지, 동시성 검증 | 5~7h |
| [M6-5](missions/M6-5-interest-batch.md) | 이자 배치 (Spring Batch) | 5~7h |
| [M6-6](missions/M6-6-daily-closing-reconciliation.md) | 일 마감과 대사 | 4~6h |
| [M6-7](missions/M6-7-interbank-transfer-simulation.md) | 타행이체 시뮬레이션 | 7~9h |
| [M6-8](missions/M6-8-multi-instance-redis-lock.md) | 다중 인스턴스와 Redis 분산락 | 5~7h |

합계 41~57h (주 12h 기준 4주 = 48h).
주별 합계: 1주 9~13h, 2주 11~15h, 3주 9~13h, 4주 12~16h. 4주 차 상한(16h)이 주 15시간을 넘으므로, 4주 차에 15시간을 쓰고도 M6-8이 남으면 Phase 7 시작 전에 1~2일을 더 쓴다.

L3 진행 순서 (모든 미션 공통):
1. 미션 문서의 "직접 작성할 테스트 시나리오"에 있는 "반드시 포함할 경우"를 모두 담아 `workspace/docs/test-scenarios/M6-{N}.md`에 표(번호 / Given / When / Then, Then은 구체 값)를 쓴다.
2. 시나리오 표를 먼저 리뷰받는다. 리뷰에서 빠진 경우가 나오면 표를 고친 뒤 구현으로 넘어간다.
3. 설계 문서가 요구되는 미션은 설계 문서를 쓰고, 테스트 → 구현 순으로 진행한다.
4. PR 본문에 시나리오 표와 완료 기준 체크 결과를 붙인다.

## 읽을거리
- Spring Batch Reference 6.0 (<https://docs.spring.io/spring-batch/reference/>): "What's new in Spring Batch 6", "The Domain Language of Batch", "Configuring and Running a Job" 중 "Configuring a JobRepository", "Running a Job", "Configuring a Step" 중 "Chunk-oriented Processing", "Configuring a Step for Restart", "ItemReaders and ItemWriters" 중 "Database"
- Spring Boot Reference "Spring Batch" 절과 How-to "Batch Applications" (<https://docs.spring.io/spring-boot/how-to/batch.html>)
- Resilience4j 문서 "CircuitBreaker" (<https://resilience4j.readme.io/docs/circuitbreaker>): 상태 3개(`CLOSED`, `OPEN`, `HALF_OPEN`)와 "Create and configure a CircuitBreaker" 표
- Spring Framework Reference "Resilience Features" (`@Retryable`, Spring Framework 7.0부터 코어에 포함)
- Martin Kleppmann, "How to do distributed locking" (2016-02-08, <https://martin.kleppmann.com/2016/02/08/how-to-do-distributed-locking.html>) 전체
- Martin Kleppmann, 『Designing Data-Intensive Applications』 1판 8장 "The Trouble with Distributed Systems"(특히 "Process Pauses", "Fencing tokens"), 9장 "Consistency and Consensus" 중 "Linearizability" 절
- IETF 초안 "The Idempotency-Key HTTP Header Field" (draft-ietf-httpapi-idempotency-key-header) 2절 "The Idempotency-Key HTTP Request Header Field"
- Brandur Leach, "Designing robust and predictable APIs with idempotency" (Stripe 블로그, 2017)
- Redisson 문서 "Locks and synchronizers" 중 "Lock" 절 (`lockWatchdogTimeout`, `leaseTime`)

## 완료 기준
- [ ] `./gradlew test`와 `./gradlew externalTest`(M6-7, 가짜 대외기관을 띄운 뒤 실행)가 통과하고, 위 불변식 INV-1~INV-4를 검사하는 테스트가 각각 1개 이상 있다 (테스트 이름에 `INV-1` 등 번호 포함)
- [ ] M6-4의 동시성 테스트(핫 계좌 입금 1,000건, 랜덤 이체 10,000건)가 끝난 뒤 INV-1, INV-2가 성립한다
- [ ] M6-7의 랜덤 장애 모드 이체 1,000건이 끝나고 `UNKNOWN`을 모두 해소한 뒤 INV-4가 성립하고, 가짜 대외기관의 처리 목록과 당행 `SUCCEEDED` 목록이 1건도 다르지 않다
- [ ] `workspace/docs/`에 이 README "이 Phase의 결과물"에 적힌 설계 문서 9개와 미션별 테스트 시나리오 표 8개가 있다
- [ ] [레벨 진단](../docs/self-check.md) Phase 6 항목을 말로 설명할 수 있다
