# Phase 8: 분산 환경과 운영 (4주)

> 가이드 수준: L3, 선행: Phase 7 완료, 이 Phase의 workspace 시작 방법: Phase 6, 7을 Gradle 멀티 모듈로 합침

## 학습 목표
이 Phase를 끝내면 다음을 할 수 있다.
- `docker compose up -d` 한 번으로 MySQL, Redis, Kafka, corebank, trading, Prometheus, Grafana, Jaeger 8개 컨테이너를 띄우고, 두 서비스의 `/actuator/health`가 120초 안에 200을 돌려주는 것을 스크립트로 보여준다
- DB 커밋과 Kafka 발행을 따로 하면 이벤트가 유실되거나 유령 이벤트가 생기는 것을 Testcontainers 테스트로 재현하고, Transactional Outbox와 멱등 컨슈머로 두 경우를 모두 0건으로 만든다
- 매수 주문 Saga(홀드 → 매칭 → 체결 확정)의 단계별 실패를 주입하는 테스트 12개 이상으로 "홀드 누수 0원, 생성된 돈 0원"을 증명한다
- Grafana 패널 12개(PromQL 포함)와 Jaeger 트레이스로 이체 p99, 커넥션 풀 대기, 락 대기를 수치로 읽고, k6로 500 req/s 5분 부하를 걸어 병목 1개 이상을 근거 지표와 함께 찾아 전후 비교표로 남긴다
- 아키텍처 다이어그램, ADR 5개 이상, 트러블슈팅 기록 3개로 지난 27.5주의 설계 결정을 문서로 설명한다

## 이 Phase의 결과물

Phase 6의 corebank와 Phase 7의 trading을 하나의 Gradle 멀티 모듈 프로젝트로 합친다. 두 서비스는 별도 프로세스, 별도 DB 스키마로 실행되고, Kafka 토픽으로만 대화한다.

```
phase-8-advanced/workspace/
├── settings.gradle.kts          include("common", "corebank", "trading")
├── build.gradle.kts             공통 플러그인 버전 선언 (apply false)
├── gradle/wrapper/              Gradle 9.8.2 Wrapper (Phase 6 corebank에서 옮긴 Initializr 생성분)
├── common/                      (선택) 서비스 간 메시지 record만. 패키지 lab.common.event
├── corebank/                    Phase 6 코드. 패키지 lab.corebank
│   ├── Dockerfile
│   └── src/main/java/lab/corebank/
│       ├── ...                  Phase 6 패키지 그대로
│       ├── outbox/              M8-3: OutboxEvent, OutboxRelay
│       ├── messaging/           M8-3: 멱등 컨슈머, processed_message
│       └── hold/                M8-4: 매수 대금 홀드, 확정, 해제 명령 처리
├── trading/                     Phase 7 코드. 패키지 lab.trading
│   ├── Dockerfile
│   └── src/main/java/lab/trading/
│       ├── ...                  Phase 7 패키지 그대로
│       ├── outbox/  messaging/  M8-3
│       └── saga/                M8-4: BuyOrderSaga 상태 머신, saga_instance
├── compose.yaml                 M8-1, M8-5
├── docker/
│   ├── mysql/init/01-databases.sql
│   ├── prometheus/prometheus.yml
│   └── grafana/                 데이터소스, 대시보드 프로비저닝
├── load-test/transfer.js        M8-6 k6 스크립트
├── scripts/wait-healthy.sh      M8-1
└── docs/
    ├── adr/                     M8-7: 0001-....md ~ 0005-....md 이상
    ├── troubleshooting/         M8-7: 사례 3개
    ├── compose-verification.md  M8-1 (image-comparison.md 포함)
    ├── dual-write-report.md     M8-2
    ├── outbox-design.md         M8-3
    ├── saga-design.md           M8-4
    ├── observability.md         M8-5
    └── load-test-report.md      M8-6
```

## 핵심 개념 정리 (미션 전에 읽기)

### 1. 이중 쓰기(dual write) 문제
DB와 Kafka는 서로 다른 시스템이고, 둘을 한 번에 커밋하는 공통 트랜잭션 관리자가 없다. 이체 서비스가 "DB에 이체 기록 + Kafka에 `TransferCompleted` 발행"을 하면 순서를 어떻게 잡아도 한쪽만 성공하는 구간이 생긴다.

| 순서 | 실패 지점 | 결과 | 고객이 겪는 일 |
|---|---|---|---|
| DB 커밋 → Kafka 발행 | 커밋 직후 브로커 장애, 프로세스 종료 | 이벤트 유실 | 돈은 나갔는데 입금 알림이 오지 않음 |
| Kafka 발행 → DB 커밋 | 발행 직후 한도 초과 예외, 커밋 실패 | 유령 이벤트 | 입금 알림은 왔는데 잔액은 그대로 |
| `@TransactionalEventListener(AFTER_COMMIT)`에서 발행 | 리스너 실행 중 브로커 장애 | 이벤트 유실 | 첫 번째 줄과 같음 |

`AFTER_COMMIT` 리스너는 "커밋이 성공한 다음에만 발행"을 보장할 뿐 "커밋했으면 반드시 발행"은 보장하지 않는다. Kafka 트랜잭션과 DB 트랜잭션을 차례로 커밋하는 방식(best-effort 1PC)도 두 커밋 사이에 프로세스가 죽으면 같은 문제가 남는다. M8-2에서 세 경우를 모두 테스트로 재현한다.

### 2. Transactional Outbox
해법은 "발행할 메시지"를 업무 데이터와 **같은 DB, 같은 트랜잭션**에 행으로 저장하는 것이다. 이체 기록과 `outbox` 행은 함께 커밋되거나 함께 롤백된다. 별도 스레드(릴레이)가 `outbox`에서 아직 발행하지 않은 행을 읽어 Kafka로 보내고, 브로커가 `acks=all`로 응답하면 `published_at`을 채운다.

```
[이체 트랜잭션]  UPDATE account ... ; INSERT journal_entry ... ; INSERT outbox(...)  → COMMIT
[릴레이 500ms마다] SELECT ... FROM outbox WHERE published_at IS NULL ORDER BY seq LIMIT 100 FOR UPDATE SKIP LOCKED
                 (seq = M8-3의 단조 증가 순서 열. id는 UUID라 순서 기준이 될 수 없다)
                → Kafka send (동기 대기) → UPDATE outbox SET published_at = now() → COMMIT
```

- 릴레이가 Kafka 전송 성공 후 `published_at` 갱신 전에 죽으면 같은 메시지를 다시 보낸다. Outbox는 **유실 0**을 주는 대신 **중복 가능**을 남긴다(at-least-once).
- `FOR UPDATE SKIP LOCKED`는 MySQL 8.0부터 지원한다. 릴레이 인스턴스가 2개일 때 다른 인스턴스가 잠근 행을 건너뛰어 같은 행을 동시에 보내지 않게 한다.
- 대안은 CDC(Change Data Capture)다. Debezium이 MySQL binlog를 읽어 `outbox` 테이블 변경을 Kafka로 옮긴다. 폴링 지연과 DB 부하가 줄지만 Kafka Connect 클러스터를 운영해야 한다. 이 Phase는 폴링 릴레이만 구현하고 CDC는 M8-7 ADR에서 비교만 한다.

### 3. at-least-once와 멱등 컨슈머
메시지 전달 보장은 세 단계로 나뉜다.

| 보장 | 뜻 | 생기는 일 |
|---|---|---|
| at-most-once | 0번 또는 1번 | 처리 전에 오프셋을 커밋하면 처리 중 장애 시 유실 |
| at-least-once | 1번 이상 | 처리 후 오프셋을 커밋하면 커밋 전 장애 시 재처리(중복) |
| exactly-once | 정확히 1번 | Kafka 트랜잭션은 Kafka → Kafka 구간만 보장. 외부 DB 부수효과에는 적용되지 않음 |

금융 시스템은 유실을 허용하지 않으므로 at-least-once를 고르고, 중복은 컨슈머가 걸러낸다. 멱등 컨슈머는 `processed_message` 테이블(PK: 컨슈머 이름 + `message_id`)에 메시지 ID를 INSERT하는 것과 부수효과(알림 저장, 홀드 생성)를 **같은 DB 트랜잭션**에서 한다. 두 번째 같은 메시지는 PK 중복으로 INSERT가 실패하므로 부수효과도 롤백된다. 메시지 ID는 발행 측 `outbox.id`(UUID)를 Kafka 헤더로 실어 보낸다. Kafka 오프셋(파티션 내 위치)은 재발행되면 바뀌므로 메시지 ID로 쓰지 않는다.

Phase 4 M4-4의 `Idempotency-Key`와 Phase 6 M6-3의 `idempotency_key` 유니크 제약이 같은 원리다. 그때는 클라이언트 재시도를 막았고, 여기서는 브로커 재전달을 막는다.

### 4. Kafka 파티션과 순서 보장 범위
- 토픽은 파티션 여러 개로 나뉜다. Kafka는 **한 파티션 안에서만** 순서를 보장한다. 토픽 전체 순서는 보장하지 않는다.
- 프로듀서는 메시지 키의 해시로 파티션을 고른다. 같은 키 = 같은 파티션 = 같은 순서. 계좌 이벤트는 계좌번호, 주문 이벤트는 주문 ID(또는 Saga ID)를 키로 쓴다.
- 컨슈머 그룹 안에서 한 파티션은 한 컨슈머 인스턴스에만 배정된다. 파티션 3개에 인스턴스 4개를 띄우면 1개는 놀게 된다.
- 오프셋은 "이 그룹이 이 파티션에서 어디까지 처리했는가"다. 처리 완료 후 커밋해야 at-least-once가 된다. Spring for Apache Kafka는 `enable.auto.commit=false`를 기본으로 두고 리스너 컨테이너가 `ack-mode`에 따라 커밋한다.
- 프로듀서 재시도는 `enable.idempotence=true`(Kafka 3.0부터 기본값)일 때 파티션 내 순서와 중복 없는 쓰기를 유지한다.

예: 계좌 `110-001`에 "출금 10,000원" → "입금 3,000원" 이벤트가 키 `110-001`로 발행되면 같은 파티션에 들어가 컨슈머도 이 순서로 받는다. 키 없이 발행하면 두 이벤트가 다른 파티션에 들어가 역순으로 처리될 수 있다.

### 5. Saga
Saga는 여러 서비스에 걸친 업무를 **각 서비스의 로컬 트랜잭션 여러 개**로 나누고, 중간에 실패하면 이미 끝난 단계를 되돌리는 **보상 트랜잭션**을 실행하는 패턴이다. 분산 트랜잭션(2PC)처럼 모든 참여자를 잠가 두지 않는다. 대신 중간 상태(홀드는 걸렸는데 주문은 아직 호가창에 없음)가 외부에 보인다.

| 단계 | 서비스 | 로컬 트랜잭션 | 보상 |
|---|---|---|---|
| 1 | trading | 주문 생성 (`PENDING`) | 주문 취소 |
| 2 | corebank | 매수 대금 홀드 | 홀드 해제 |
| 3 | trading | 매칭 엔진 제출 → 체결 | 없음 (체결은 시장에서 일어난 사실이라 되돌릴 수 없다) |
| 4 | corebank | 체결분 홀드 확정 | 없음, 성공할 때까지 재시도 |

3단계처럼 되돌릴 수 없는 단계를 **피벗(pivot) 트랜잭션**이라 한다. 피벗 전 단계는 보상 가능해야 하고, 피벗 후 단계는 재시도로 반드시 성공해야 한다. 조정 방식은 두 가지다. **오케스트레이션**은 Saga 상태 머신을 가진 조정자가 명령을 보낸다. **코레오그래피**는 각 서비스가 이벤트를 구독해 다음 단계를 스스로 실행한다. M8-4는 오케스트레이션으로 구현하고 두 방식을 표로 비교한다.

### 6. 관측성의 세 기둥
| 기둥 | 답하는 질문 | 이 Phase의 도구 | 예 |
|---|---|---|---|
| 메트릭 | 지금 얼마나, 몇 %인가 (집계 수치) | Micrometer → `/actuator/prometheus` → Prometheus → Grafana | 이체 p99 = 182ms, 커넥션 대기 7개 |
| 로그 | 이 요청에서 무슨 일이 있었나 (개별 사건) | Logback 콘솔 로그 + MDC `traceId`, `spanId` | `[traceId-spanId] 이체 실패: LIMIT_EXCEEDED` |
| 트레이스 | 한 요청이 어느 서비스, 구간에서 시간을 썼나 | Micrometer Tracing + OpenTelemetry → OTLP → Jaeger | HTTP 12ms → DB 40ms → Kafka → corebank 컨슈머 25ms |

세 가지는 `traceId`로 연결한다. Grafana에서 p99가 튄 시점을 찾고, 그 시점 로그에서 `traceId`를 찾고, Jaeger에서 그 트레이스를 열어 느린 구간을 찾는다. Google SRE 책 6장은 사용자 관점 지표로 지연(latency), 트래픽(traffic), 에러(errors), 포화도(saturation)의 네 가지 골든 시그널을 든다. M8-5 대시보드의 패널은 이 네 분류로 나눈다.

### 7. 부하 테스트 지표: 처리량, p50/p95/p99, 에러율
- 처리량: 초당 완료 요청 수(req/s). 목표 부하를 "초당 요청 수"로 고정하는 방식(open model, k6 `constant-arrival-rate`)과 "동시 사용자 수"로 고정하는 방식(closed model)이 있다. closed model은 서버가 느려지면 요청도 줄어 지연이 숨겨진다. 이 Phase는 open model을 쓴다.
- 백분위: 응답 시간을 정렬했을 때 p99 = 상위 1%가 넘는 경계. 평균은 소수의 느린 요청을 가린다. 요청 1,000개 중 985개가 10ms, 15개가 2,000ms면 평균은 39.85ms지만 p95는 10ms, p99는 2,000ms다(nearest-rank 방식: p99 = 정렬했을 때 990번째 값).
- Prometheus 히스토그램의 `histogram_quantile`은 버킷 경계 사이를 선형 보간한 **추정값**이다. k6가 직접 계산한 p99와 몇 ms 차이가 날 수 있고, 리포트에는 둘을 따로 적는다.
- 에러율: 이 Phase에서는 HTTP 5xx와 연결 실패만 에러로 센다. 잔액 부족(4xx) 같은 업무 거절은 테스트 데이터로 발생하지 않게 만든다.

### 8. 리틀의 법칙(Little's law)
안정 상태의 시스템에서 `L = λ × W`가 성립한다. L은 시스템 안에 동시에 있는 요청 수, λ는 도착률(req/s), W는 요청 하나가 머무는 평균 시간이다.

| 예 | 계산 | 결론 |
|---|---|---|
| 500 req/s, 평균 응답 50ms | L = 500 × 0.05 = 25 | 서버 안에 평균 25개 요청이 동시에 있다 |
| 이체 1건이 DB 커넥션을 30ms 점유, 500 req/s | 필요 커넥션 = 500 × 0.03 = 15 | HikariCP 기본 풀 크기 10으로는 부족하다 |
| 풀 10개, 점유 30ms | 최대 처리량 = 10 / 0.03 ≈ 333 req/s | 이 이상 요청이 오면 `hikaricp_connections_pending`이 쌓이고 지연이 늘어난다 |

M8-6에서 병목 가설을 세울 때 이 계산을 먼저 하고, 측정값(`hikaricp_connections_active`, `hikaricp_connections_usage_seconds`)으로 맞는지 확인한다.

## 워크스페이스 만들기

```bash
cd phase-8-advanced
mkdir -p workspace && cd workspace
cp -r ../../phase-6-core-banking/workspace/corebank ./corebank   # Phase 6 빌드 파일은 workspace/corebank/에 있다
cp -r ../../phase-7-securities-trading/workspace ./trading
mkdir -p common   # Gradle 9는 include한 프로젝트의 디렉터리가 없으면 빌드를 실패시킨다
# 모듈 안의 settings.gradle.kts, gradlew, gradlew.bat, gradle/ 를 지우고 루트로 옮긴다
mv corebank/gradlew corebank/gradlew.bat corebank/gradle .
rm -f corebank/settings.gradle.kts trading/settings.gradle.kts trading/gradlew trading/gradlew.bat
rm -rf trading/gradle
```

Phase 6, 7 workspace의 `build.gradle.kts`는 각 모듈 디렉터리에 그대로 두고, `plugins` 블록의 버전만 지운다(루트에서 선언). `./gradlew :corebank:test :trading:test`가 둘 다 통과하면 합치기가 끝난 것이다.

`settings.gradle.kts`:
```kotlin
rootProject.name = "fintech-platform"
include("common", "corebank", "trading")
```

루트 `build.gradle.kts` (플러그인 버전을 한 곳에서 관리하고 각 모듈에서 적용):
```kotlin
plugins {
    id("org.springframework.boot") version "4.1.2" apply false
    id("io.spring.dependency-management") version "1.1.7" apply false
}
```

이 Phase에서 추가하는 의존성 좌표 (버전은 Spring Boot BOM이 관리, 2026-11-10 확인):

| 용도 | 좌표 | 미션 |
|---|---|---|
| Kafka | `org.springframework.boot:spring-boot-starter-kafka` | M8-2 |
| Kafka 테스트 | `org.springframework.boot:spring-boot-starter-kafka-test` | M8-2 |
| Testcontainers Kafka | `org.testcontainers:testcontainers-kafka` (Testcontainers 2.x, 클래스 `org.testcontainers.kafka.KafkaContainer`) | M8-2 |
| Testcontainers Toxiproxy | `org.testcontainers:testcontainers-toxiproxy` | M8-2 (선택) |
| Actuator | `org.springframework.boot:spring-boot-starter-actuator` | M8-1 |
| Prometheus 레지스트리 | `io.micrometer:micrometer-registry-prometheus` | M8-5 |
| OpenTelemetry 트레이싱 | `org.springframework.boot:spring-boot-starter-opentelemetry` | M8-5 |

Testcontainers 2.0부터 모듈 이름에 `testcontainers-` 접두사가 붙었다(1.x의 `org.testcontainers:kafka`는 2.x에서 `org.testcontainers:testcontainers-kafka`). 1.x 기준 블로그 예제를 옮길 때 좌표와 패키지를 확인한다.

## 주차별 계획
| 주 | 미션 | 개념 학습 범위 |
|---|---|---|
| 1주 | M8-1, M8-2 | 이 README 1절, Kafka 공식 문서 "Design" 장의 Motivation, Persistence, The Producer, The Consumer, Message Delivery Semantics 절 |
| 2주 | M8-3, M8-5 요구사항 1~6(메트릭, 대시보드) | 2~4절, microservices.io Transactional outbox, Idempotent Consumer, DDIA 11장 |
| 3주 | M8-4, M8-5 요구사항 7~9(트레이스, 로그) | 5~6절, microservices.io Saga, Google SRE 책 6장 |
| 4주 | M8-6, M8-7 | 7~8절, k6 문서 Scenarios |

M8-5의 선행은 M8-1뿐이지만, 트레이스 요구사항은 서비스 두 개를 오가는 M8-4 Saga 흐름을 대상으로 하므로 3주 차에 마친다.
M8-5(6~8h)를 요구사항 1~6에 3~4h, 7~9에 3~4h로 나누면 주별 합계는 1주 11~15h, 2주 11~14h, 3주 12~15h, 4주 10~14h다.

## 미션
| 미션 | 주제 | 예상 시간 |
|---|---|---|
| [M8-1](missions/M8-1-container-compose.md) | 컨테이너 이미지와 Compose 전체 실행 | 6~8h |
| [M8-2](missions/M8-2-dual-write-problem.md) | 이중 쓰기 문제 재현 | 5~7h |
| [M8-3](missions/M8-3-outbox-idempotent-consumer.md) | Transactional Outbox와 멱등 컨슈머 | 8~10h |
| [M8-4](missions/M8-4-saga.md) | Saga | 9~11h |
| [M8-5](missions/M8-5-observability.md) | 관측성 | 6~8h |
| [M8-6](missions/M8-6-load-test-tuning.md) | 부하 테스트와 튜닝 리포트 | 6~8h |
| [M8-7](missions/M8-7-portfolio.md) | 포트폴리오 정리 | 4~6h |

합계 44~58h (주 12h × 4주 = 48h 기준).

## 읽을거리
- microservices.io 패턴 페이지 3개: "Pattern: Transactional outbox", "Pattern: Saga", "Pattern: Idempotent Consumer" (https://microservices.io/patterns/)
- Apache Kafka 공식 문서 "Design" 장: Motivation, Persistence, The Producer, The Consumer, Message Delivery Semantics, Replication 절 (Efficiency 절은 건너뛴다) (https://kafka.apache.org/documentation/#design)
- Martin Kleppmann, 『Designing Data-Intensive Applications』 1판 11장 "Stream Processing": "Transmitting Event Streams", "Databases and Streams"(Keeping Systems in Sync, Change Data Capture) 절
- Grafana k6 문서 "Scenarios": Executors 중 constant-arrival-rate, "Thresholds" (https://grafana.com/docs/k6/latest/using-k6/scenarios/)
- Google 『Site Reliability Engineering』 6장 "Monitoring Distributed Systems": "The Four Golden Signals" 절 (https://sre.google/sre-book/monitoring-distributed-systems/)
- Spring Boot 4.1 레퍼런스 "Observability", "Metrics", "Tracing" 장 (https://docs.spring.io/spring-boot/reference/actuator/)

## 완료 기준
- [ ] `docker compose down -v && docker compose up -d` 후 `scripts/wait-healthy.sh`가 120초 안에 corebank, trading 모두 200을 받고 종료 코드 0으로 끝난다
- [ ] `./gradlew test`가 통과하고, 그중 M8-2의 이중 쓰기 재현 테스트가 Outbox 적용 후 "유실 0건, 유령 0건"을 단언한다
- [ ] 같은 메시지를 2번 이상 재전달해도 부수효과가 1번만 반영되는 것을 단언하는 테스트가 corebank, trading 컨슈머마다 1개 이상 있다
- [ ] M8-4 Saga 실패 주입 테스트 12개 이상이 통과하고, 각 테스트가 끝날 때 corebank의 홀드 금액 합계와 Saga 장부상 미정산 홀드 합계가 같다
- [ ] Grafana 대시보드 JSON이 `docker/grafana/`에 있고, 패널 12개 이상이 PromQL로 정의되어 있다
- [ ] `docs/load-test-report.md`에 변경 1가지씩 최소 3회의 전후 측정 행이 있고, 마지막 행이 "500 req/s, p99 < 300ms, 에러율 < 0.1%"를 만족하거나 만족하지 못한 이유를 지표 값으로 적었다
- [ ] `docs/adr/`에 ADR 5개 이상, `docs/troubleshooting/`에 사례 3개, 레포 README에 Mermaid 아키텍처 다이어그램이 있다
- [ ] [레벨 진단](../docs/self-check.md) Phase 8 항목을 말로 설명할 수 있다
