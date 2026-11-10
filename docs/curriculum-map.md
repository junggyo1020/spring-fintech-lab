# 커리큘럼 맵 (미션 전체 목록과 연결 관계)

이 문서는 모든 Phase README와 미션 문서의 **기준 문서**다. 미션 이름, 선행 미션, 만드는 코드가
다른 문서와 다르면 이 문서를 기준으로 고친다.

기준 버전 (2026-11-10 확인)

| 범위 | 버전 | 결정 방법 |
|---|---|---|
| Phase 0~2 (직접 만드는 Gradle 프로젝트) | Java 21, Gradle 8.14.3, JUnit 5.11.4, AssertJ 3.27.3 | `build.gradle.kts`에 직접 적는다 |
| Phase 3~8 (Spring Initializr 프로젝트) | Java 21, Spring Boot 4.1.x (Spring Framework 7, Jackson 3, Hibernate 7, Spring Security 7, Spring Batch 6) | Gradle wrapper(9.x)와 JUnit Jupiter(6.x) 버전은 Initializr와 Boot BOM이 정한 값을 그대로 쓴다 |
| 인프라 | MySQL 8.4 LTS, Redis 8, Apache Kafka 4.x (KRaft 모드), k6 | 이미지 태그는 각 Phase README에 적는다 |

정확한 의존성 좌표는 각 Phase README의 "워크스페이스 만들기"에 적는다.

---

## 1. 가이드 수준 (Phase가 올라갈수록 문서가 주는 도움을 줄인다)

| 수준 | 적용 | 문서가 제공하는 것 | 내가 직접 해야 하는 것 |
|---|---|---|---|
| **L1** | Phase 0~1 | 클래스·메서드 시그니처, 기대값이 채워진 테스트 시나리오 표, 힌트 2~3개 | 테스트 코드 작성, 구현 |
| **L2** | Phase 2~5 | 요구사항, 기대값이 채워진 테스트 시나리오 표, 핵심 인터페이스 시그니처만, 힌트 1~2개 | 클래스 설계(필드·메서드 결정), 테스트, 구현, 측정표 |
| **L3** | Phase 6~8 | 요구사항, 완료 기준(반드시 지켜야 할 불변식), 힌트 0~1개 | 테스트 시나리오 표 직접 작성(PR 본문에 첨부), 설계 문서, 구현 |

L3 미션의 테스트 시나리오 표는 PR을 올리기 전에 리뷰를 먼저 받는다. 시나리오가 빠지면 구현 리뷰로 넘어가지 않는다.

---

## 2. 코드 계보 (각 Phase의 workspace가 어디서 시작하는가)

| Phase | workspace 시작 방법 | 루트 패키지 | 실행 형태 |
|---|---|---|---|
| 0 | 빈 디렉터리에서 직접 생성 | `lab.hello` | Gradle 단일 모듈 |
| 1 | 빈 디렉터리에서 직접 생성 | `lab.bank` | 순수 Java, `main` 콘솔 앱 |
| 2 | Phase 1 `src/` 복사 | `lab.bank` | 순수 Java |
| 3 | Spring Initializr로 생성 후 Phase 2 도메인 코드 복사 | `lab.bank` | Spring Boot (웹 없음) |
| 4 | Phase 3 workspace 복사 + Spring MVC·Spring Security 스타터 추가 | `lab.bank` | Spring Boot 웹, 저장소는 메모리 |
| 5 | Phase 4 workspace 복사 + MySQL 8.4, JPA, Flyway 추가 | `lab.bank` | Spring Boot 웹 + MySQL |
| 6 | Spring Initializr로 새로 생성 (Phase 5 코드는 참고만) | `lab.corebank` | Spring Boot + MySQL + Redis |
| 7 | Spring Initializr로 새로 생성 | `lab.trading` | Spring Boot + MySQL |
| 8 | Phase 6, 7을 Gradle 멀티 모듈로 합침 | `lab.corebank`, `lab.trading` | 서비스 2개 + Kafka + 관측 스택 |

Phase 1에서 만든 이름(`Money`, `Currency`, `AccountNumber`, `Account`, `AccountStatus`,
`Transaction`, `TransactionType`, `Ledger`, `BankService`, `BankException`, `ErrorCode`)은
Phase 5까지 같은 이름으로 쓴다. Phase 2의 `TransferEngine`, `TransferCommand`, `TransferResult`도 마찬가지다.

---

## 3. 미션 목록

표의 "선행"은 반드시 먼저 끝내야 하는 미션이다. "만드는 것"은 미션이 끝났을 때 workspace에 있어야 하는 코드·문서다.

### Phase 0 — 개발 환경 (0.5주, L1)

| 미션 | 주제 | 선행 | 만드는 것 |
|---|---|---|---|
| M0-1 | 개발 환경 세팅 | - | JDK 21, IntelliJ, Git, Docker 설치 확인 기록 |
| M0-2 | 첫 Gradle 프로젝트 & 첫 테스트 | M0-1 | `Greeter`, `GreeterTest`, Gradle Wrapper |
| M0-3 | GitHub Actions CI | M0-2 | `.github/workflows/ci.yml` (push·PR마다 `./gradlew test`) |

### Phase 1 — Java 기본기 + TDD (3주, L1)

| 미션 | 주제 | 선행 | 만드는 것 |
|---|---|---|---|
| M1-1 | `Money` 값 객체 | M0-2 | `Money`, `Currency`, `CurrencyMismatchException` |
| M1-2 | `Account` 엔티티와 도메인 예외 | M1-1 | `AccountNumber`, `AccountStatus`, `Account`, `BankException` 계층, `ErrorCode` |
| M1-3 | 거래내역과 `Ledger` | M1-2 | `Transaction`, `TransactionType`, `Ledger`, `BankService` |
| M1-4 | 이자 계산기와 반올림 정책 | M1-1 | `InterestPolicy` 구현체 3개, `TaxCalculator` |
| M1-5 | [종합] 콘솔 뱅킹 | M1-3, M1-4 | `console` 패키지, JaCoCo 리포트 |

### Phase 2 — Java 동시성 (3주, L2)

| 미션 | 주제 | 선행 | 만드는 것 |
|---|---|---|---|
| M2-1 | Race condition 재현 | M1-5 | `UnsafeCounter`, lost update 재현 테스트 |
| M2-2 | `synchronized`로 계좌 보호 | M2-1 | 락 범위 3버전 측정표 |
| M2-3 | 이체와 데드락 | M2-2 | 락 순서 이체, 스레드 덤프 분석 TIL |
| M2-4 | `ReentrantLock`, `tryLock`, 타임아웃 | M2-3 | 타임아웃 이체, 공정성 측정표 |
| M2-5 | Atomic/CAS와 낙관적 동시성 | M2-2 | CAS 계좌, 버전 기반 업데이트 |
| M2-6 | `ExecutorService`와 가상 스레드 | M2-4 | 풀 종류별 측정표 |
| M2-7 | [종합] 스레드 안전한 이체 엔진 | M2-4, M2-5, M2-6 | `TransferEngine`, `DESIGN.md` |

### Phase 3 — Spring Core (2주, L2)

| 미션 | 주제 | 선행 | 만드는 것 |
|---|---|---|---|
| M3-1 | 나만의 DI 컨테이너 | M2-7 | `@MyComponent`, `MiniContainer` (생성자 주입, 순환 참조 감지) |
| M3-2 | Spring Boot로 이식 | M3-1 | Spring Boot 프로젝트, `TransferEngine` 빈 |
| M3-3 | 빈 스코프·라이프사이클과 싱글톤 상태 문제 | M3-2 | 상태를 가진 싱글톤 빈의 동시성 버그 재현 테스트 |
| M3-4 | 프록시 직접 만들기 | M3-2 | 실행 시간 측정 프록시 3종 (데코레이터, JDK 동적 프록시, CGLIB) |
| M3-5 | 감사 로그 AOP | M3-4 | `@Audited`, `AuditAspect`, self-invocation 재현 테스트 |
| M3-6 | 설정 외부화와 프로파일 | M3-2 | `TransferProperties` (`@ConfigurationProperties` + 검증), `local`/`test` 프로파일 |

### Phase 4 — Spring Web, API 설계, 보안 (3주, L2)

| 미션 | 주제 | 선행 | 만드는 것 |
|---|---|---|---|
| M4-1 | HTTP와 첫 컨트롤러 | M3-6 | `HealthController`, curl로 관찰한 요청·응답 기록 |
| M4-2 | 계좌 API와 입력 검증 | M4-1 | `AccountController`, 요청/응답 DTO(`record`), Bean Validation |
| M4-3 | 에러 응답 표준화 | M4-2 | `@RestControllerAdvice`, `ErrorCode` → HTTP 상태 + `ProblemDetail` |
| M4-4 | 이체 API와 `Idempotency-Key` | M4-3 | `TransferController`, 멱등 처리 |
| M4-5 | 거래내역 조회와 커서 페이지네이션 | M4-3 | `GET /accounts/{number}/transactions` |
| M4-6 | 금액·날짜 직렬화 | M4-2 | Jackson 3 커스텀 직렬화 (금액 → 문자열) |
| M4-7 | Spring Security 인증·인가 | M4-4 | `SecurityFilterChain`, 계좌 소유자 검증 |
| M4-8 | API 테스트와 요청 추적 로그 | M4-7 | `@WebMvcTest` 테스트, MDC 요청 ID 필터 |

### Phase 5 — SQL, JDBC, JPA, 트랜잭션, DB 락 (4주, L2)

| 미션 | 주제 | 선행 | 만드는 것 |
|---|---|---|---|
| M5-1 | SQL 기초 | M4-8 | Docker MySQL 8.4, `sql/` 폴더의 DDL·DML·JOIN·집계 쿼리 |
| M5-2 | JDBC 맨손 구현 | M5-1 | `JdbcAccountRepository` (`Connection`, `PreparedStatement`, 수동 트랜잭션) |
| M5-3 | JdbcTemplate, Flyway, Testcontainers | M5-2 | Flyway 마이그레이션 `V1__...sql`, Testcontainers 통합 테스트 |
| M5-4 | JPA 전환과 영속성 컨텍스트 | M5-3 | JPA 엔티티, Spring Data 리포지토리 |
| M5-5 | N+1 문제 | M5-4 | fetch join / `@EntityGraph` / batch size 비교표 |
| M5-6 | 트랜잭션 함정 | M5-4 | 전파·롤백 규칙·self-invocation 재현 테스트 |
| M5-7 | 격리 수준 실험실 | M5-3 | 두 커넥션 교차 실행 기록표 |
| M5-8 | DB 동시성 제어 3종 비교 | M5-6 | 비관적 락 / 낙관적 락 / 조건부 UPDATE 비교표 |
| M5-9 | DB 데드락과 인덱스·실행계획 | M5-8 | `SHOW ENGINE INNODB STATUS` 분석, `EXPLAIN` 기록 |

### Phase 6 — 코어뱅킹 프로젝트 (4주, L3)

| 미션 | 주제 | 선행 | 만드는 것 |
|---|---|---|---|
| M6-1 | 요구사항·ERD·상태 머신 설계 | M5-9 | `docs/requirements.md`, ERD, 계좌 상태 머신 |
| M6-2 | 복식부기 분개 엔진 | M6-1 | `JournalEntry`, `JournalLine`, 계정과목 |
| M6-3 | 입출금·당행이체와 멱등성 | M6-2 | 이체 API, `idempotency_key` 유니크 제약 |
| M6-4 | 이체 한도, 비밀번호 오류 정지, 동시성 검증 | M6-3 | 한도 테이블, 동시성 통합 테스트 |
| M6-5 | 이자 배치 (Spring Batch) | M6-3 | 일 이자 계산·지급 Job |
| M6-6 | 일 마감과 대사 | M6-5 | 잔액 스냅샷, 원장-잔액 대사 Job, 불일치 리포트 |
| M6-7 | 타행이체 시뮬레이션 | M6-3, M6-4 | 가짜 대외기관 서버, 타임아웃·결과 미확정·보상 처리 |
| M6-8 | 다중 인스턴스와 Redis 분산락 | M6-4 | 인스턴스 2대 실행 시나리오, Redisson 락 vs DB 락 비교 |

### Phase 7 — 증권 매매 프로젝트 (4주, L3)

| 미션 | 주제 | 선행 | 만드는 것 |
|---|---|---|---|
| M7-1 | 주문 도메인과 호가 단위 | M6-8 | `Order`, 주문 상태 머신, `TickSizePolicy` |
| M7-2 | 예수금·수량 홀드 | M7-1 | 주문가능금액·매도가능수량 차감, 동시 주문 테스트 |
| M7-3 | 호가창과 매칭 엔진 | M7-1 | `OrderBook`, `MatchingEngine` (순수 Java) |
| M7-4 | 단일 스레드 이벤트 루프 | M7-3 | 종목별 명령 큐 + 전용 스레드 |
| M7-5 | 정정·취소 | M7-4 | 정정/취소 명령, 체결과의 경합 테스트 |
| M7-6 | 체결 반영, 평균단가, 수수료·세금, T+2 결제 | M7-2, M7-5 | 체결 이벤트 처리기, 결제 예정 내역 |
| M7-7 | 실시간 시세 WebSocket | M7-4 | STOMP 호가/체결 브로드캐스트 |
| M7-8 | 이벤트 소싱 복구 | M7-5 | 명령 로그 재생으로 호가창 복구 테스트 |

### Phase 8 — 분산 환경과 운영 (4주, L3)

| 미션 | 주제 | 선행 | 만드는 것 |
|---|---|---|---|
| M8-1 | 컨테이너 이미지와 Compose 전체 실행 | M7-8 | `Dockerfile`, `compose.yaml`, CI에 이미지 빌드 추가 |
| M8-2 | 이중 쓰기 문제 재현 | M8-1 | DB 커밋과 Kafka 발행 불일치 재현 테스트 |
| M8-3 | Transactional Outbox와 멱등 컨슈머 | M8-2 | `outbox` 테이블, 릴레이, `processed_message` 테이블 |
| M8-4 | Saga | M8-3 | 주문-계좌 서비스 간 Saga, 단계별 실패 주입 테스트 |
| M8-5 | 관측성 | M8-1 | Micrometer 메트릭, Prometheus, Grafana 대시보드, OpenTelemetry 트레이스 |
| M8-6 | 부하 테스트와 튜닝 리포트 | M8-5 | k6 스크립트, 측정 전후 비교 리포트 |
| M8-7 | 포트폴리오 정리 | M8-6 | 아키텍처 다이어그램, ADR 5개 이상, 트러블슈팅 사례 3개 |

---

## 4. 기간 합계

| Phase | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 합계 |
|---|---|---|---|---|---|---|---|---|---|---|
| 주 | 0.5 | 3 | 3 | 2 | 3 | 4 | 4 | 4 | 4 | **27.5주** |

주 10~15시간 기준. 미션 문서의 "예상 시간"을 합한 값이 이 기간을 넘으면 기간 쪽을 늘린다. 미션은 건너뛰지 않는다.
