# Spring Fintech Lab

> Java/Spring 기초부터 시작해 **코어뱅킹**과 **증권 매매 시스템**의 비즈니스 로직을 직접 구현하고,
> **동시성 제어 · 트랜잭션 · 정합성**까지 다룰 수 있는 개발자가 되기 위한 실습 레포지토리.

이 레포에는 **정답 코드가 없습니다.** 개념 정리, 실습 가이드, 과제 명세(요구사항 + 검증 기준)만 있고,
코드는 전부 내가 직접 타이핑합니다. 막히면 힌트를 보고, 그래도 막히면 리뷰를 요청합니다.

---

## 최종 목표

| 영역 | 도달 수준 |
|---|---|
| Java | 불변 객체, 값 객체, 예외 설계, 컬렉션/스트림, 테스트 주도 개발을 자연스럽게 쓴다 |
| 동시성 | Race condition을 **재현 → 원인 설명 → 해결 → 테스트로 증명**할 수 있다 |
| Spring | DI/AOP/트랜잭션이 **내부적으로 어떻게 동작하는지** 설명할 수 있다 |
| DB | 격리수준, 락(비관/낙관), 인덱스, 실행계획을 근거로 설계를 선택한다 |
| 코어뱅킹 | 계좌·원장(복식부기)·이체·한도·멱등성·이자·마감을 구현한다 |
| 증권 | 주문·호가창·매칭엔진·체결·예수금/잔고 홀드·정정/취소를 구현한다 |
| 아키텍처 | Outbox, Saga, 이벤트, 분산락, 관측성, 부하 테스트까지 경험한다 |

---

## 로드맵 (약 24주, 주 10~15시간 기준)

| Phase | 주제 | 기간 | 산출물 |
|---|---|---|---|
| [0](phase-0-setup/README.md) | 개발 환경 & 학습 시스템 구축 | 0.5주 | 환경 세팅, 첫 Gradle 프로젝트, 학습 루틴 |
| [1](phase-1-java-foundation/README.md) | 금융 도메인을 위한 Java 기본기 + TDD | 3주 | 순수 Java `Money`, `Account`, `Ledger` |
| [2](phase-2-java-concurrency/README.md) | Java 동시성 기초 | 3주 | 스레드 안전한 메모리 이체 엔진 |
| [3](phase-3-spring-core/README.md) | Spring Core (IoC/DI/AOP) | 2주 | 스프링으로 이식한 이체 서비스 + 감사 로그 AOP |
| [4](phase-4-spring-web/README.md) | Spring Web MVC & API 설계 | 2주 | 계좌 REST API |
| [5](phase-5-data-transaction/README.md) | JDBC → JPA, 트랜잭션, DB 락 | 3주 | DB 기반 계좌/원장, 동시성 테스트 |
| [6](phase-6-core-banking/README.md) | 🏦 코어뱅킹 프로젝트 | 4주 | 미니 코어뱅킹 시스템 |
| [7](phase-7-securities-trading/README.md) | 📈 증권 매매 프로젝트 | 4주 | 매칭엔진 포함 미니 거래소/증권사 |
| [8](phase-8-advanced/README.md) | 분산 환경 & 운영 수준 | 3주+ | Outbox/Saga/Kafka/Redis/관측성/부하테스트 |

자세한 주차별 계획: [docs/roadmap.md](docs/roadmap.md)

```
Phase 0 → 1 → 2 ──┐
                  ├→ 3 → 4 → 5 → 6 (코어뱅킹) → 7 (증권) → 8 (분산/운영)
   (Java 동시성)  ┘
```

> **왜 Spring보다 순수 Java 동시성을 먼저 하나요?**
> `@Transactional`이나 DB 락은 "동시성 문제를 DB에 위임"하는 방법입니다. 위임하기 전에
> 메모리에서 직접 race condition을 겪어보고 해결해봐야, 나중에 DB 락/분산락을 **왜** 쓰는지 체감할 수 있습니다.

---

## 학습 방법

- [docs/study-method.md](docs/study-method.md) — 하루 루틴, 커밋 규칙, TIL 작성법, 리뷰 받는 법
- [docs/self-check.md](docs/self-check.md) — 레벨 진단 (이미 아는 Phase는 과제만 풀고 건너뛰기)

### 각 Phase 폴더 구성

```
phase-N-xxx/
├── README.md          # 학습 목표, 개념 정리, 읽을거리, 체크리스트
├── missions/          # 과제 명세 (요구사항, 검증 기준, 힌트)
│   ├── M1-xxx.md
│   └── ...
└── workspace/         # ← 내가 직접 코드를 작성하는 곳 (Gradle 프로젝트)
```

### 과제 진행 규칙

1. 미션 문서의 **요구사항**을 읽는다.
2. **테스트를 먼저** 작성한다 (미션에 제공된 테스트 시나리오 표를 코드로 옮긴다).
3. 구현해서 테스트를 통과시킨다.
4. 미션의 **생각해볼 질문**에 대한 답을 `til/`에 적는다.
5. 브랜치에 커밋 → 리뷰 요청 → 피드백 반영 → `main`에 머지.
6. 아래 진행 현황 체크박스를 체크한다.

---

## 진행 현황

### Phase 0 — 환경
- [ ] M0-1 개발 환경 세팅
- [ ] M0-2 첫 Gradle 프로젝트 & 첫 테스트

### Phase 1 — Java 기본기
- [ ] M1-1 `Money` 값 객체
- [ ] M1-2 `Account` 엔티티와 도메인 예외
- [ ] M1-3 거래내역과 `Ledger` (컬렉션/스트림)
- [ ] M1-4 이자 계산기 (BigDecimal 반올림 정책)
- [ ] M1-5 [종합] 콘솔 뱅킹 애플리케이션

### Phase 2 — Java 동시성
- [ ] M2-1 Race condition 재현하기
- [ ] M2-2 `synchronized`로 계좌 보호
- [ ] M2-3 이체와 데드락 (락 순서)
- [ ] M2-4 `ReentrantLock`, `tryLock`, 타임아웃
- [ ] M2-5 Atomic/CAS와 낙관적 동시성
- [ ] M2-6 `ExecutorService`와 가상 스레드로 부하 테스트
- [ ] M2-7 [종합] 스레드 안전한 메모리 이체 엔진

### Phase 3 ~ 8
- [ ] Phase 3 — Spring Core
- [ ] Phase 4 — Spring Web
- [ ] Phase 5 — 데이터 & 트랜잭션
- [ ] Phase 6 — 코어뱅킹
- [ ] Phase 7 — 증권 매매
- [ ] Phase 8 — 분산/운영

> Phase 3 이후의 미션 문서는 진행 상황과 앞 Phase에서 드러난 약점에 맞춰 **그때그때 구체화**합니다.
> (각 Phase README에는 목표·주제·미션 목록·완료 기준이 미리 정리되어 있습니다.)

---

## 기술 스택

- Java 21 (record, sealed, pattern matching, virtual threads)
- Gradle (Kotlin DSL)
- JUnit 5, AssertJ, Mockito
- Spring Boot 3.x — Phase 3부터
- MySQL 8 / PostgreSQL, Flyway, Testcontainers — Phase 5부터
- Redis, Kafka, Docker Compose — Phase 6~8
- k6, Micrometer/Prometheus/Grafana — Phase 8
