# 상세 로드맵 (주차별)

주 10~15시간 기준. 시간이 더 적으면 기간을 늘리고, **건너뛰지는 않는다.**
각 주의 마지막 날은 "복습 + TIL 정리 + 리뷰 반영"에 쓴다.

---

## Phase 0 — 환경 & 학습 시스템 (0.5주)

| 일 | 할 일 |
|---|---|
| 1 | JDK 21, IntelliJ, Git 설치. IntelliJ 단축키 10개 외우기 |
| 2 | Gradle 프로젝트 직접 만들기, `./gradlew test` 이해하기, 첫 테스트 작성 |
| 3 | GitHub 브랜치 전략 / 커밋 규칙 정하고 첫 PR 올려보기 |

---

## Phase 1 — 금융 도메인을 위한 Java 기본기 (3주)

| 주 | 주제 | 미션 |
|---|---|---|
| 1주 | 값 객체, 불변성, `equals/hashCode`, `BigDecimal`, JUnit5/AssertJ | M1-1 `Money` |
| 2주 | 엔티티 vs 값 객체, 캡슐화, 예외 설계(checked/unchecked), `record`, `enum`, `sealed` | M1-2 `Account`, M1-3 `Ledger` |
| 3주 | 컬렉션/스트림 심화, 반올림 정책, `java.time`, 종합 | M1-4 이자 계산기, M1-5 콘솔 뱅킹 |

**완료 기준:** `double`로 돈을 계산하면 왜 안 되는지, `equals`를 재정의하면 왜 `hashCode`도 해야 하는지,
불변 객체가 동시성에 왜 유리한지 남에게 설명할 수 있다.

---

## Phase 2 — Java 동시성 (3주)

| 주 | 주제 | 미션 |
|---|---|---|
| 1주 | 스레드, 메모리 가시성, 원자성, `synchronized`, `volatile`, happens-before | M2-1, M2-2 |
| 2주 | 데드락 4조건, 락 순서, `ReentrantLock`, `tryLock`, `Condition` | M2-3, M2-4 |
| 3주 | CAS/Atomic, `ConcurrentHashMap`, `ExecutorService`, `CountDownLatch`, 가상 스레드 | M2-5, M2-6, M2-7 |

**완료 기준:** 100개 스레드가 동시에 이체해도 총 잔액이 보존되고 데드락이 없음을 **테스트로 증명**한다.

---

## Phase 3 — Spring Core (2주)

| 주 | 주제 |
|---|---|
| 1주 | Spring 없이 DI 직접 구현 → IoC 컨테이너, 빈 스코프/라이프사이클, 컴포넌트 스캔, `@Configuration` 프록시 |
| 2주 | 프록시 패턴 → JDK 동적 프록시/CGLIB → AOP, `@ConfigurationProperties`, Profile, 테스트 슬라이스 |

---

## Phase 4 — Spring Web MVC (2주)

| 주 | 주제 |
|---|---|
| 1주 | DispatcherServlet 흐름, REST 설계(리소스/상태코드), DTO ↔ 도메인 분리, Bean Validation |
| 2주 | 전역 예외 처리(`ProblemDetail`), 금액/날짜 직렬화, MockMvc 테스트, API 문서화(Spring REST Docs 또는 springdoc) |

---

## Phase 5 — 데이터 접근 & 트랜잭션 (3주)

| 주 | 주제 |
|---|---|
| 1주 | JDBC 직접 → `JdbcTemplate` → JPA. 영속성 컨텍스트, 더티 체킹, Flyway, Testcontainers |
| 2주 | `@Transactional` 내부 동작(프록시), 전파 속성, 롤백 규칙, self-invocation 함정, 격리 수준과 이상현상 |
| 3주 | Lost update 재현 → 비관적 락(`SELECT ... FOR UPDATE`) / 낙관적 락(`@Version`) / 원자적 UPDATE 비교, 데드락 분석, 인덱스/실행계획 |

---

## Phase 6 — 🏦 코어뱅킹 프로젝트 (4주)

| 주 | 주제 |
|---|---|
| 1주 | 도메인 모델링: 고객, 상품, 계좌, 계좌상태 머신, **복식부기 원장**(분개/전표) |
| 2주 | 입금/출금/계좌이체, **멱등성 키**, 일일/1회 이체한도, 동시 이체 정합성 |
| 3주 | 이자 계산 & 일 마감 배치(Spring Batch), 원장-잔액 대사(reconciliation) |
| 4주 | 타행 이체 시뮬레이션(외부 연동 타임아웃·재시도·보상), Redis 분산락, 부하 테스트 |

---

## Phase 7 — 📈 증권 매매 프로젝트 (4주)

| 주 | 주제 |
|---|---|
| 1주 | 도메인: 종목, 주문(지정가/시장가), 주문 상태 머신, 호가 단위, 예수금/잔고 **홀드(가수금)** |
| 2주 | **매칭 엔진**: 가격-시간 우선 호가창(`TreeMap` + 큐), 부분 체결, 단일 스레드 이벤트 루프 |
| 3주 | 정정/취소, 체결 → 잔고/포지션/평균단가 반영, 수수료/세금, 체결 이벤트 |
| 4주 | 시세 브로드캐스트(WebSocket), 주문 폭주 부하 테스트, 매칭엔진 장애 복구(이벤트 소싱 리플레이) |

---

## Phase 8 — 분산 환경 & 운영 수준 (3주+)

| 주 | 주제 |
|---|---|
| 1주 | 서비스 분리(계좌/주문), Transactional Outbox, Kafka, 멱등 컨슈머 |
| 2주 | Saga(오케스트레이션 vs 코레오그래피), 보상 트랜잭션, 정합성 모니터링 |
| 3주 | Micrometer/Prometheus/Grafana, 분산 트레이싱, k6 부하 테스트, 병목 분석 리포트 |
