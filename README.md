# Spring Fintech Lab

> Java 기본기에서 시작해 **코어뱅킹**과 **증권 매매 시스템**을 직접 구현하면서
> **동시성 제어, 트랜잭션, 정합성, 분산 환경 운영**까지 다루는 27.5주 실습 커리큘럼.

이 레포에는 **정답 코드가 없다.** 개념 정리, 미션 명세(요구사항 + 테스트 시나리오 + 완료 기준), 힌트만 있고
코드는 전부 내가 설계하고 타이핑한다. Phase가 올라갈수록 문서가 주는 도움이 줄어들어,
마지막 Phase에서는 요구사항만 보고 테스트 시나리오와 설계 문서까지 직접 작성한다.

---

## 최종 목표 (Phase 8을 끝냈을 때 할 수 있는 것)

| 영역 | 완료 시점에 할 수 있는 것 | 확인하는 미션 |
|---|---|---|
| Java | `BigDecimal` 기반 값 객체, 불변 객체, 도메인 예외 계층을 설계하고 JUnit 5 테스트를 먼저 작성한다 | M1-5 |
| 동시성 | lost update와 데드락을 테스트로 재현하고, `synchronized`, `ReentrantLock`, CAS로 고친 뒤 스레드 10,000개 테스트로 총액 보존을 증명한다 | M2-7 |
| Spring | DI 컨테이너를 리플렉션으로 직접 만들고, `@Transactional`, AOP가 프록시로 동작한다는 것을 self-invocation 테스트로 보여준다 | M3-1, M3-5 |
| API, 보안 | REST API, `ProblemDetail` 에러 응답, `Idempotency-Key`, 커서 페이지네이션, Spring Security 인증, 인가를 구현하고 `@WebMvcTest`로 검증한다 | M4-8 |
| DB | SQL을 직접 작성하고, 격리 수준별 이상현상을 두 세션으로 재현하며, 비관적 락, 낙관적 락, 조건부 UPDATE의 처리량을 측정해 선택 근거를 댄다 | M5-8, M5-9 |
| 코어뱅킹 | 복식부기 원장, 멱등 이체, 한도, Spring Batch 이자 배치, 원장-잔액 대사, 타행이체 타임아웃 처리를 구현한다 | M6-1 ~ M6-8 |
| 증권 | 호가단위 검증, 예수금, 수량 홀드, 가격-시간 우선 매칭 엔진, 정정, 취소, T+2 결제 반영, 이벤트 소싱 복구를 구현한다 | M7-1 ~ M7-8 |
| 분산, 운영 | Docker Compose로 전체 스택을 띄우고, Outbox, 멱등 컨슈머, Saga를 구현하며, Prometheus, Grafana 지표와 k6 부하 테스트로 병목을 찾는다 | M8-1 ~ M8-7 |

---

## 로드맵 (27.5주, 주 10~15시간 기준)

| Phase | 주제 | 기간 | 가이드 수준 | 산출물 |
|---|---|---|---|---|
| [0](phase-0-setup/README.md) | 개발 환경, Gradle, CI | 0.5주 | L1 | 첫 테스트, GitHub Actions CI |
| [1](phase-1-java-foundation/README.md) | 금융 도메인을 위한 Java 기본기 + TDD | 3주 | L1 | 순수 Java `Money`, `Account`, `Ledger`, 콘솔 뱅킹 |
| [2](phase-2-java-concurrency/README.md) | Java 동시성 | 3주 | L2 | 스레드 안전한 메모리 이체 엔진 |
| [3](phase-3-spring-core/README.md) | Spring Core (IoC/DI/AOP) | 2주 | L2 | 직접 만든 DI 컨테이너, Spring Boot 이식, 감사 로그 AOP |
| [4](phase-4-spring-web/README.md) | Spring Web MVC, API 설계, Spring Security | 3주 | L2 | 인증이 붙은 계좌, 이체 REST API |
| [5](phase-5-data-transaction/README.md) | SQL, JDBC, JPA, 트랜잭션, DB 락 | 4주 | L2 | MySQL 기반 계좌, 원장, DB 동시성 비교표 |
| [6](phase-6-core-banking/README.md) | 코어뱅킹 프로젝트 | 4주 | L3 | 미니 코어뱅킹 시스템 |
| [7](phase-7-securities-trading/README.md) | 증권 매매 프로젝트 | 4주 | L3 | 매칭 엔진을 포함한 미니 거래소, 증권계좌 |
| [8](phase-8-advanced/README.md) | 분산 환경과 운영 | 4주 | L3 | 서비스 2개 + Kafka + 관측 스택 + 부하 테스트 리포트 |

```
Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 (코어뱅킹) → 7 (증권) → 8 (분산, 운영)
```

- 미션 전체 목록, 선행 관계, 각 Phase의 workspace 시작 방법: [docs/curriculum-map.md](docs/curriculum-map.md)
- 주차별 계획: [docs/roadmap.md](docs/roadmap.md)

### 가이드 수준

| 수준 | Phase | 문서가 주는 것 | 내가 하는 것 |
|---|---|---|---|
| L1 | 0~1 | 시그니처, 기대값이 채워진 테스트 표, 힌트 2~3개 | 테스트 작성, 구현 |
| L2 | 2~5 | 요구사항, 기대값이 채워진 테스트 표, 핵심 인터페이스만, 힌트 1~2개 | 클래스 설계, 테스트, 구현, 측정 |
| L3 | 6~8 | 요구사항, 완료 기준(불변식), 힌트 0~1개 | 테스트 시나리오 표 작성, 설계 문서, 구현 |

> **왜 Spring보다 순수 Java 동시성을 먼저 하나?**
> `@Transactional`과 DB 락은 동시성 제어를 DB에 맡기는 방법이다. Phase 2에서 메모리 위의 lost update를
> 직접 재현하고 락으로 고쳐 보면, Phase 5에서 `SELECT ... FOR UPDATE`가 어떤 인터리빙을 막는지
> 같은 테스트 구조로 비교할 수 있다.

---

## 학습 방법

- [docs/study-method.md](docs/study-method.md): 하루 루틴, 막혔을 때 규칙, 브랜치, 커밋 규칙, TIL, 리뷰 요청 방법
- [docs/self-check.md](docs/self-check.md): Phase별 레벨 진단 질문

### 각 Phase 폴더 구성

```
phase-N-xxx/
├── README.md          # 학습 목표, 핵심 개념, 주차별 계획, 미션 표, 읽을거리, 완료 기준
├── missions/          # 미션 명세 (목표, 요구사항, 테스트 시나리오, 제약, 힌트, 완료 기준, 질문)
└── workspace/         # 내가 코드를 작성하는 Gradle 프로젝트
```

### 미션 진행 순서

1. 미션 문서의 **목표, 요구사항, 제약**을 읽는다. Phase README의 핵심 개념 절을 먼저 읽었는지 확인한다.
2. 미션 이슈 본문의 "작업 브랜치" 이름으로 브랜치를 만든다 (예: `phase1/m1-1-money`). 이슈는 `mission_issue.py`로 만든다 (docs/study-method.md 1단계).
3. **테스트를 먼저** 작성한다. L1, L2는 문서의 테스트 시나리오 표를 코드로 옮기고, L3는 시나리오 표를 직접 작성해 리뷰를 받은 뒤 코드로 옮긴다.
4. 테스트가 실패하는 것을 확인한 뒤 구현해 통과시킨다.
5. **완료 기준** 체크박스를 하나씩 확인한다.
6. **생각해볼 질문**의 답을 `til/`에 쓴다.
7. PR을 올리고 리뷰를 요청한다 → 피드백 반영 → `main`에 머지.
8. 아래 진행 현황을 체크한다.

---

## 진행 현황

### Phase 0: 개발 환경
- [ ] M0-1 개발 환경 세팅
- [ ] M0-2 첫 Gradle 프로젝트 & 첫 테스트
- [ ] M0-3 GitHub Actions CI

### Phase 1: Java 기본기
- [ ] M1-1 `Money` 값 객체
- [ ] M1-2 `Account` 엔티티와 도메인 예외
- [ ] M1-3 거래내역과 `Ledger`
- [ ] M1-4 이자 계산기와 반올림 정책
- [ ] M1-5 [종합] 콘솔 뱅킹

### Phase 2: Java 동시성
- [ ] M2-1 Race condition 재현
- [ ] M2-2 `synchronized`로 계좌 보호
- [ ] M2-3 이체와 데드락
- [ ] M2-4 `ReentrantLock`, `tryLock`, 타임아웃
- [ ] M2-5 Atomic/CAS와 낙관적 동시성
- [ ] M2-6 `ExecutorService`와 가상 스레드
- [ ] M2-7 [종합] 스레드 안전한 이체 엔진

### Phase 3: Spring Core
- [ ] M3-1 나만의 DI 컨테이너
- [ ] M3-2 Spring Boot로 이식
- [ ] M3-3 빈 스코프, 라이프사이클과 싱글톤 상태 문제
- [ ] M3-4 프록시 직접 만들기
- [ ] M3-5 감사 로그 AOP
- [ ] M3-6 설정 외부화와 프로파일

### Phase 4: Spring Web, API, 보안
- [ ] M4-1 HTTP와 첫 컨트롤러
- [ ] M4-2 계좌 API와 입력 검증
- [ ] M4-3 에러 응답 표준화
- [ ] M4-4 이체 API와 `Idempotency-Key`
- [ ] M4-5 거래내역 조회와 커서 페이지네이션
- [ ] M4-6 금액, 날짜 직렬화
- [ ] M4-7 Spring Security 인증, 인가
- [ ] M4-8 API 테스트와 요청 추적 로그

### Phase 5: SQL, JDBC, JPA, 트랜잭션
- [ ] M5-1 SQL 기초
- [ ] M5-2 JDBC 맨손 구현
- [ ] M5-3 JdbcTemplate, Flyway, Testcontainers
- [ ] M5-4 JPA 전환과 영속성 컨텍스트
- [ ] M5-5 N+1 문제
- [ ] M5-6 트랜잭션 함정
- [ ] M5-7 격리 수준 실험실
- [ ] M5-8 DB 동시성 제어 3종 비교
- [ ] M5-9 DB 데드락과 인덱스, 실행계획

### Phase 6: 코어뱅킹
- [ ] M6-1 요구사항, ERD, 상태 머신 설계
- [ ] M6-2 복식부기 분개 엔진
- [ ] M6-3 입출금, 당행이체와 멱등성
- [ ] M6-4 이체 한도, 비밀번호 오류 정지, 동시성 검증
- [ ] M6-5 이자 배치
- [ ] M6-6 일 마감과 대사
- [ ] M6-7 타행이체 시뮬레이션
- [ ] M6-8 다중 인스턴스와 Redis 분산락

### Phase 7: 증권 매매
- [ ] M7-1 주문 도메인과 호가 단위
- [ ] M7-2 예수금, 수량 홀드
- [ ] M7-3 호가창과 매칭 엔진
- [ ] M7-4 단일 스레드 이벤트 루프
- [ ] M7-5 정정, 취소
- [ ] M7-6 체결 반영, 평균단가, 수수료, 세금, T+2 결제
- [ ] M7-7 실시간 시세 WebSocket
- [ ] M7-8 이벤트 소싱 복구

### Phase 8: 분산 환경과 운영
- [ ] M8-1 컨테이너 이미지와 Compose 전체 실행
- [ ] M8-2 이중 쓰기 문제 재현
- [ ] M8-3 Transactional Outbox와 멱등 컨슈머
- [ ] M8-4 Saga
- [ ] M8-5 관측성
- [ ] M8-6 부하 테스트와 튜닝 리포트
- [ ] M8-7 포트폴리오 정리

---

## 기술 스택 (기준 버전 확인일 2026-11-10)

| 영역 | 기술 | 시작 Phase |
|---|---|---|
| 언어, 빌드 | Java 21 (LTS), Gradle 8.14.3 (Kotlin DSL) | 0 |
| 테스트 | JUnit 5.11, AssertJ 3.27, JaCoCo | 0~1 |
| CI | GitHub Actions | 0 |
| 프레임워크 | Spring Boot 4.1.x (Spring Framework 7, Jackson 3) | 3 |
| 보안 | Spring Security 7 | 4 |
| DB | MySQL 8.4 LTS, JDBC, Spring Data JPA (Hibernate 7), Flyway, Testcontainers | 5 |
| 배치, 연동 | Spring Batch, Resilience4j, Redis 8 + Redisson | 6 |
| 실시간 | WebSocket (STOMP) | 7 |
| 분산, 운영 | Docker Compose, Apache Kafka 4.x, Micrometer, Prometheus, Grafana, OpenTelemetry, k6 | 8 |

Spring Boot 3.5의 OSS 지원은 2026-06-30에 끝났고, MySQL 8.0은 2026년 4월에 지원이 종료됐다. 그래서 이 레포는 Boot 4.1과 MySQL 8.4를 기준으로 한다.
Java는 Phase 2의 가상 스레드 pinning 실험(JDK 24에서 JEP 491로 해소)을 재현하기 위해 21을 기준으로 둔다.
