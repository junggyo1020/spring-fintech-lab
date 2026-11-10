# Phase 7: 증권 매매 프로젝트 (4주)

> 가이드 수준: L3, 선행: Phase 6 완료, 이 Phase의 workspace 시작 방법: Spring Initializr로 새로 생성 (루트 패키지 `lab.trading`, Spring Boot + MySQL)

코어뱅킹(Phase 6)이 "돈이 생기거나 사라지지 않는가"의 문제였다면, 증권 매매는 여기에 **순서**(누가 먼저 체결되는가)와 **지연시간**(주문 하나를 몇 µs 안에 처리하는가)이 더해진다.
이 Phase에서는 거래소 1곳의 매칭 엔진과 증권사 계좌를 한 애플리케이션 안에서 시뮬레이션한다.

## 학습 목표
이 Phase를 끝내면 다음을 할 수 있다.
- 동시 매수 주문 100건 중 예수금 한도 안의 주문만 접수되고 홀드 합계가 미체결 주문의 홀드 합계와 같다는 것을 테스트로 보여준다
- 가격-시간 우선 원칙으로 동작하는 호가창과 매칭 엔진을 순수 Java로 만들고, 기대 체결 결과가 정해진 시나리오 12개를 통과시킨다
- 종목별 전용 스레드 매칭 엔진과 락 기반 엔진의 처리량, p99 지연시간을 같은 입력으로 측정해 표로 비교한다
- 체결 1건이 예수금, D+2 예수금, 보유수량, 평균단가, 실현손익에 반영되는 값을 손 계산 결과와 원 단위까지 일치시킨다
- 명령 로그를 재생해 재시작 전과 같은 호가창을 만들고, 두 상태의 SHA-256 해시가 같다는 것을 테스트로 보여준다

## 이 Phase의 범위

| 다룬다 | 다루지 않는다 (이유) |
|---|---|
| KRX 정규시장 접속매매(09:00~15:20)만 시뮬레이션 | 장 시작, 장 마감 동시호가의 단일가 매매: 매칭 규칙이 완전히 다르다. 15:20~15:30 주문은 거부한다 |
| 지정가, 시장가 주문 | 조건부지정가, 최유리, 최우선지정가, IOC/FOK 조건 |
| 원화(KRW), 가격, 수량 모두 정수(`long`) | 소수점 주식, 외화 |
| 거래소 1곳 | 대체거래소(NXT)와의 최선집행 |
| 종목 3개(아래 표), 기준가격 고정 | 일별 기준가격 갱신, 신규상장 종목의 별도 가격제한폭 |
| 계좌 식별은 요청의 `accountId` | 로그인, 인가: Phase 4에서 다뤘으므로 생략한다 |

이 Phase에서 쓰는 종목 (Flyway로 넣는 테스트 데이터, 실제 종목이 아니다):

| 종목코드 | 시장 | 기준가격 | 상한가 | 하한가 |
|---|---|---|---|---|
| `A00001` | KOSPI | 70,000 | 91,000 | 49,000 |
| `A00002` | KOSPI | 10,000 | 13,000 | 7,000 |
| `Q00001` | KOSDAQ | 12,000 | 15,600 | 8,400 |

## 이 Phase의 결과물

```
phase-7-securities-trading/workspace/
├── build.gradle.kts
├── docs/
│   ├── engine-design.md          # M7-4: 단일 스레드를 고른 이유, 큐 용량, 장애 시 동작
│   ├── latency-report.md         # M7-4: 측정표
│   ├── test-scenarios/M7-*.md    # 미션별 직접 작성한 테스트 시나리오 표 (PR 본문에도 첨부)
│   └── recovery-report.md        # M7-8: 복구 시간, fsync 모드별 처리량
└── src/main/java/lab/trading/
    ├── domain/order/      # Order, OrderStatus, OrderSide, OrderType, RejectReason, TickSizePolicy, PriceLimitPolicy
    ├── domain/account/    # TradingAccount, Position, HoldCalculator, FeePolicy, TaxPolicy, SettlementItem
    ├── engine/            # OrderBook, MatchingEngine, 엔진 이벤트(Execution, OrderRested, OrderCancelled ...)
    ├── engine/runtime/    # SymbolEngine(전용 스레드 + 명령 큐)
    ├── engine/journal/    # CommandJournal, SnapshotStore, EngineRecovery (M7-8)
    ├── application/       # OrderService, EngineRegistry, ExecutionHandler, SettlementService, BusinessCalendar
    ├── api/               # OrderController, AccountController
    └── marketdata/        # STOMP 설정, 호가, 체결 브로드캐스트 (M7-7)
```

`engine` 패키지(하위 패키지 포함)는 Spring, JPA, `java.time`에 의존하지 않는다. Spring 빈으로 엔진을 띄우는 `EngineRegistry`는 `application`에 둔다. M7-3에서 순수 Java로 만들고 M7-8에서 재생 테스트를 하려면 엔진 안에 외부 상태가 없어야 하기 때문이다.

## 핵심 개념 정리 (미션 전에 읽기)

### 1. 증권계좌 구조
증권계좌는 현금(예수금)과 보유 종목(포지션)으로 나뉜다. 이 Phase에서 쓰는 항목과 계산식은 아래와 같다.

| 항목 | 이 Phase의 정의 |
|---|---|
| 예수금 (`cash`) | 결제가 끝난 현금 |
| 결제 예정 내역 (`SettlementItem`) | 체결됐지만 결제일이 오지 않은 금액. 매수는 음수(`-(체결금액+수수료)`), 매도는 양수(`체결금액-수수료-세금`) |
| D+2 예수금 | 예수금 + 결제 예정 내역 합계. 결제일까지 반영한 예상 현금 |
| 홀드금액 (`holdAmount`) | 미체결 매수 주문이 묶어둔 금액 합계 (5절) |
| 주문가능금액 | D+2 예수금 − 홀드금액 |
| 출금가능금액 | max(0, 예수금 − 미결제 매수 결제금액 합계 − 홀드금액): 이 Phase의 규칙 |
| 보유수량 (`quantity`) | 체결 즉시 늘고 준다 (이 Phase의 규칙: 수량은 체결 기준, 현금만 T+2 결제) |
| 홀드수량 (`holdQuantity`) | 미체결 매도 주문이 묶어둔 수량 |
| 매도가능수량 | 보유수량 − 홀드수량 |
| 평균단가 | 수수료를 뺀 체결가 기준 가중평균 (M7-6) |

주문가능금액에 미결제 매도 대금이 들어가는 이유: 국내 증권사는 결제 전 매도 대금으로 다시 매수하는 것을 허용하고, 출금은 결제일 이후에만 허용한다(`fintech-domain-facts` §4, 확인일 2026-11-10). 그래서 두 금액을 서로 다른 식으로 계산한다.

### 2. 주문 유형과 주문 상태
| 유형 | 가격 입력 | 이 Phase의 처리 규칙 |
|---|---|---|
| 지정가(`LIMIT`) | 필수 | 반대편 호가 중 지정가 이하(매수)/이상(매도)인 호가와 체결하고, 남은 수량은 호가창에 쌓인다 |
| 시장가(`MARKET`) | 넣으면 거부 | 반대편 호가를 좋은 가격부터 소진하며 체결하고, **남은 수량은 즉시 취소한다** (이 Phase의 규칙, IOC와 같은 동작) |

주문 상태는 `RECEIVED`(접수) → `PARTIALLY_FILLED`(부분체결) → `FILLED`(체결완료)로 진행하고, 미체결 수량이 남은 상태에서 `CANCELLED`(취소)로 끝날 수 있다. 검증에 실패한 주문은 처음부터 `REJECTED`(거부)로 저장된다. 전이표는 [M7-1](missions/M7-1-order-domain-tick-size.md)에 있다.
정정은 상태가 아니다. 정정된 주문은 `RECEIVED` 또는 `PARTIALLY_FILLED`를 유지하고 가격, 수량만 바뀐다.

### 3. 가격-시간 우선 원칙
매매 체결은 가격 우선 → 시간 우선으로 정한다(`fintech-domain-facts` §4).
- 매수 호가는 높은 가격이, 매도 호가는 낮은 가격이 먼저 체결된다.
- 같은 가격이면 먼저 들어온 주문이 먼저 체결된다. "먼저"는 엔진이 명령을 꺼낸 순서(시퀀스 번호)로 정하고, 벽시계 시각은 쓰지 않는다.
- 체결가격은 호가창에 먼저 있던 주문(resting order)의 가격이다. 10,050원 매수 호가가 있을 때 9,990원 매도 주문이 들어오면 10,050원에 체결된다.

```
매도 호가 (asks, 오름차순)        매수 호가 (bids, 내림차순)
10,050 | S3(2)                      10,000 | B2(5) B3(5)   ← 같은 가격: B2가 먼저
10,010 | S2(4)                       9,990 | B1(5)
10,000 | S1(3)   ← 최우선 매도호가
```

### 4. 호가가격단위와 가격제한폭
KRX 주식 호가가격단위 (2023-01-25 시행, 코스피, 코스닥 동일, 확인일 2026-11-10):

| 주가 구간 | 호가단위 |
|---|---|
| 2,000원 미만 | 1원 |
| 2,000원 이상 ~ 5,000원 미만 | 5원 |
| 5,000원 이상 ~ 20,000원 미만 | 10원 |
| 20,000원 이상 ~ 50,000원 미만 | 50원 |
| 50,000원 이상 ~ 200,000원 미만 | 100원 |
| 200,000원 이상 ~ 500,000원 미만 | 500원 |
| 500,000원 이상 | 1,000원 |

가격제한폭은 기준가격 대비 ±30%다(2015-06-15 시행). 상한가, 하한가를 호가단위에 맞추는 방법은 공식 규정 원문을 확인하지 못했으므로 **이 Phase의 규칙으로 정한다**:
- 상한가 = 기준가격 × 1.3을 그 값이 속한 구간의 호가단위로 **내림**
- 하한가 = 기준가격 × 0.7을 그 값이 속한 구간의 호가단위로 **올림**
- 예: 기준가격 15,430 → 20,059 → 50원 단위 내림 → 상한가 20,050 / 10,801 → 10원 단위 올림 → 하한가 10,810

### 5. 홀드 (주문가능금액, 매도가능수량 차감)
홀드는 미체결 주문이 쓸 돈과 주식을 미리 묶어 두는 것이다. 홀드가 없으면 예수금 100만 원으로 100만 원짜리 매수 주문을 10건 낼 수 있고, 모두 체결되면 결제일에 900만 원이 부족해진다.
- 매수 주문의 홀드금액 = 홀드기준가 × 미체결수량 + 수수료(홀드기준가 × 미체결수량). 홀드기준가는 지정가 주문이면 지정가, 시장가 주문이면 상한가다 (이 Phase의 규칙).
- 매도 주문의 홀드수량 = 미체결수량.
- 체결, 취소, 정정이 일어날 때마다 위 식으로 다시 계산하고, 줄어든 만큼 해제한다.
- 홀드는 회계의 "가수금"과 다르다. 가수금은 성격이 확정되지 않은 입금을 임시로 처리하는 회계 계정이고, 주문 홀드를 가리키는 말이 아니다(`fintech-domain-facts` §5).

### 6. 체결과 결제 (T+2), 수수료와 세금
체결(execution)은 매수, 매도 주문이 가격과 수량에 합의한 사건이고, 결제(settlement)는 현금과 주식이 실제로 오가는 사건이다. KRX 주식은 T+2, 즉 체결일 포함 3영업일째에 결제한다. 월요일 체결 → 수요일 결제, 금요일 체결 → 다음 주 화요일 결제(공휴일 없을 때).

| 항목 | 값 | 근거 |
|---|---|---|
| 위탁수수료 | 체결금액 × 0.015%, 원 미만 절사, 매수, 매도 모두, 체결 1건마다 | 이 Phase의 규칙 (증권사마다 다르다) |
| 증권거래세 + 농어촌특별세 (KOSPI) | 0.05% + 0.15% = 0.20%, 매도만 | `fintech-domain-facts` §2 (2026년 기준, 확인일 2026-11-10) |
| 증권거래세 (KOSDAQ) | 0.20%, 매도만 | 같은 출처 |
| 세금 끝수 | 세목별로 각각 원 미만 절사 | 이 Phase의 규칙 |

KOSPI에서 세목별로 절사하면 0.20%를 한 번에 곱한 값과 1원 차이가 날 수 있다. 예: 체결금액 69,930원 → 거래세 34원 + 농특세 104원 = 138원, 한 번에 계산하면 139원.

### 7. 매칭 엔진을 단일 스레드로 두는 이유
호가창(`TreeMap` + 가격별 큐)은 주문 하나를 처리할 때 여러 가격 레벨과 여러 주문을 연달아 바꾼다. 여러 스레드가 동시에 바꾸면 이 모든 변경을 하나의 락으로 묶어야 하고, 결국 한 번에 한 스레드만 일한다.
그래서 종목마다 스레드 1개가 명령 큐에서 명령을 하나씩 꺼내 처리한다.
- 락이 없다: 매칭 코드는 일반 단일 스레드 코드와 같다.
- 처리 순서가 큐 순서로 하나로 정해진다: 엔진이 꺼낸 순서대로 시퀀스 번호를 붙여 기록하면, 같은 순서로 다시 넣었을 때 같은 결과가 나온다(8절).
- 종목끼리는 상태를 공유하지 않으므로 종목 수만큼 병렬로 처리한다.
- 대가: 엔진 스레드에서 DB 호출처럼 블로킹 작업을 하면 그 종목 전체가 멈춘다. 계좌 반영은 엔진 밖 다른 스레드에서 한다.

LMAX 거래소는 이 구조(입력 디스럽터 → 단일 스레드 Business Logic Processor → 출력 디스럽터)로 Business Logic Processor 스레드 1개에서 초당 600만 건의 주문을 처리했다고 보고했다(읽을거리의 Fowler 글 첫 문단, 측정 하드웨어는 각주 4). LMAX는 모든 종목을 스레드 1개로 처리했고, 이 Phase는 종목마다 스레드 1개를 둔다.

### 8. 이벤트 소싱과 결정성
이벤트 소싱은 현재 상태 대신 상태를 바꾼 입력의 순서 목록을 원본으로 저장하고, 상태는 그 목록을 처음부터 재생해 만드는 방식이다.
매칭 엔진은 메모리에만 상태가 있으므로, 프로세스가 죽으면 호가창이 사라진다. 엔진이 명령을 처리하기 **전에** 명령 로그에 추가(append)해 두면, 재시작 후 로그를 재생해 같은 호가창을 만든다.
이것이 성립하려면 엔진이 결정적이어야 한다. 같은 명령 순서 → 같은 체결 → 같은 호가창.
결정성을 깨는 것: 엔진 안에서 `LocalDateTime.now()` 호출, `Random`, `HashMap` 순회 순서에 의존하는 로직, 스레드 간 경쟁. 시각은 명령에 실어 로그에 같이 남긴다.
로그가 길어지면 재생 시간이 늘어나므로 N건마다 스냅샷(호가창 전체 + 마지막 시퀀스)을 저장하고, 복구는 "최신 스냅샷 + 그 뒤 로그"로 한다.

## 워크스페이스 만들기

```bash
cd phase-7-securities-trading/workspace
curl https://start.spring.io/starter.zip \
  -d type=gradle-project-kotlin -d language=java -d javaVersion=21 \
  -d bootVersion=4.1.2 -d groupId=lab -d artifactId=trading -d packageName=lab.trading \
  -d dependencies=web,data-jpa,mysql,flyway,validation,websocket,testcontainers \
  -o trading.zip && unzip trading.zip && rm trading.zip
```

start.spring.io 기본값이 2026-11-10 기준 4.1.2다. 생성된 `build.gradle.kts`의 `dependencies`는 아래와 같다(2026-11-10 생성 결과). 여기에 HdrHistogram 한 줄을 추가하고, 생성된 `tasks.withType<Test> { useJUnitPlatform() }` 블록을 아래 두 블록으로 바꾼다. HdrHistogram 외의 버전은 Spring Boot BOM이 관리한다.

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-flyway")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    implementation("org.springframework.boot:spring-boot-starter-webmvc")
    implementation("org.springframework.boot:spring-boot-starter-websocket")
    implementation("org.flywaydb:flyway-mysql")
    runtimeOnly("com.mysql:mysql-connector-j")
    testImplementation("org.springframework.boot:spring-boot-starter-data-jpa-test")
    testImplementation("org.springframework.boot:spring-boot-starter-flyway-test")
    testImplementation("org.springframework.boot:spring-boot-starter-validation-test")
    testImplementation("org.springframework.boot:spring-boot-starter-webmvc-test")
    testImplementation("org.springframework.boot:spring-boot-starter-websocket-test")
    testImplementation("org.springframework.boot:spring-boot-testcontainers")
    testImplementation("org.testcontainers:testcontainers-junit-jupiter")
    testImplementation("org.testcontainers:testcontainers-mysql")
    testImplementation("org.hdrhistogram:HdrHistogram:2.2.2")   // 추가: M7-4 지연시간 측정
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform { excludeTags("benchmark") }
}

tasks.register<Test>("benchmark") {
    useJUnitPlatform { includeTags("benchmark") }
    testClassesDirs = sourceSets["test"].output.classesDirs
    classpath = sourceSets["test"].runtimeClasspath
    maxHeapSize = "2g"
}
```

Initializr가 만든 Gradle Wrapper는 9.8.2다(2026-11-10 생성 결과). Phase 0~2의 Gradle 8.14.3과 다르지만, [커리큘럼 맵](../docs/curriculum-map.md)의 Phase 3~8 기준("Gradle wrapper는 Initializr가 정한 9.x를 그대로 쓴다")과 같다. 이 Wrapper를 바꾸지 않는다.

로컬 MySQL:

```bash
docker run -d --name trading-mysql -p 3307:3306 \
  -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=trading mysql:8.4
```

## 주차별 계획
| 주 | 미션 | 개념 학습 범위 |
|---|---|---|
| 1주 | M7-1, M7-2 | 핵심 개념 1~5절, Phase 5 M5-8(조건부 UPDATE) 복습 |
| 2주 | M7-3, M7-4 | 핵심 개념 3절, 7절, Fowler "The LMAX Architecture" 전체, Disruptor 논문 2절 |
| 3주 | M7-5, M7-6 | 핵심 개념 1절, 5절, 6절 |
| 4주 | M7-7, M7-8 | 핵심 개념 8절, Spring Framework 레퍼런스 "STOMP" 장 |

## 미션
| 미션 | 주제 | 예상 시간 |
|---|---|---|
| [M7-1](missions/M7-1-order-domain-tick-size.md) | 주문 도메인과 호가 단위 | 5~6h |
| [M7-2](missions/M7-2-cash-quantity-hold.md) | 예수금, 수량 홀드 | 6~7h |
| [M7-3](missions/M7-3-order-book-matching-engine.md) | 호가창과 매칭 엔진 | 8~9h |
| [M7-4](missions/M7-4-single-thread-event-loop.md) | 단일 스레드 이벤트 루프 | 5~6h |
| [M7-5](missions/M7-5-amend-cancel.md) | 정정, 취소 | 5~6h |
| [M7-6](missions/M7-6-execution-settlement.md) | 체결 반영, 평균단가, 수수료, 세금, T+2 결제 | 7~8h |
| [M7-7](missions/M7-7-realtime-websocket.md) | 실시간 시세 WebSocket | 4~5h |
| [M7-8](missions/M7-8-event-sourcing-recovery.md) | 이벤트 소싱 복구 | 6~7h |

합계 46~54h (주 12h 기준 4주).

L3 미션은 구현 전에 `docs/test-scenarios/M7-{N}.md`에 테스트 시나리오 표(# / 준비 / 실행 / 기대 결과)를 먼저 쓰고 리뷰를 받는다. 시나리오 표가 리뷰를 통과하지 않으면 구현 리뷰로 넘어가지 않는다.

## 읽을거리
- Martin Fowler, "The LMAX Architecture" (2011): https://martinfowler.com/articles/lmax.html: "Overall Structure", "Business Logic Processor", "Input and Output Disruptors" 절
- Thompson 외, "LMAX Disruptor: High performance alternative to bounded queues for exchanging data between concurrent threads": https://lmax-exchange.github.io/disruptor/disruptor.html: 2절 "The Complexities of Concurrency", 3.3절 "Sequencing"
- Martin Fowler, "Event Sourcing": https://martinfowler.com/eaaDev/EventSourcing.html
- HdrHistogram README "Corrected vs. Raw value recording calls" 절 (요청 간격보다 긴 응답이 측정에서 빠지는 문제): https://github.com/HdrHistogram/HdrHistogram
- Spring Framework 레퍼런스, Web on Servlet Stack → WebSockets → "STOMP" 장: "Enable STOMP", "Simple Broker", "Order of Messages", "STOMP Client", "Performance" 절
- 한국거래소 법규서비스(https://law.krx.co.kr)의 "유가증권시장 업무규정"과 "유가증권시장 업무규정 시행세칙": 호가가격단위와 가격제한폭 조항. 이 문서 작성 시 조 번호와 상, 하한가 끝수 처리 문구는 확인하지 못했으므로, 직접 찾아 4절의 "이 Phase의 규칙"과 비교해 TIL에 적는다

## 완료 기준
- [ ] `./gradlew test`가 통과하고, M7-1~M7-8 각 미션의 완료 기준 체크박스가 모두 체크돼 있다
- [ ] 동시 매수 100건 테스트에서 접수 14건, 거부 86건, 홀드금액 9,801,470원이 10회 반복 실행 모두 같다 (M7-2)
- [ ] 매칭 엔진 참조 시나리오 12개와 직접 작성한 시나리오 8개 이상이 통과한다 (M7-3)
- [ ] 모든 통합 테스트 종료 시점에 `계좌 holdAmount == Σ 미체결 매수 주문 홀드 + Σ 처리 대기 중인 정정 예약 홀드`(M7-5), `Σ 매수 체결수량 == Σ 매도 체결수량`이 성립한다
- [ ] 명령 10만 건 실행 후 전체 재생, 스냅샷+꼬리 재생 두 방법으로 복구한 호가창 해시가 원본과 같다 (M7-8)
- [ ] `docs/engine-design.md`에 단일 스레드를 고른 이유, 큐가 가득 찼을 때의 동작, 프로세스 종료 시 복구 방법이 있다
- [ ] [레벨 진단](../docs/self-check.md) Phase 7 항목을 말로 설명할 수 있다
