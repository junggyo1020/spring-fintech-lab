# 레벨 진단

각 질문에 문서를 보지 않고 말이나 글로 2분 안에 답할 수 있으면 체크한다. 괄호 안에 확인 방법이 있는 질문은 그 방법으로 답이 맞는지 확인한다.

- 한 Phase에서 80% 이상 체크되면: 그 Phase README의 핵심 개념 절은 체크하지 못한 질문과 관련된 절만 읽고, 미션은 모두 푼다.
- 종합 미션(M1-5, M2-7)과 L3 Phase(6~8)의 미션은 체크 비율과 관계없이 모두 푼다.
- 각 Phase의 완료 기준에는 이 문서의 해당 절을 모두 체크하는 것이 포함된다.

---

## Phase 0 — 개발 환경

- [ ] `sdk install java 21-tem`이 실패하는 이유와, 올바른 식별자를 얻는 명령(`sdk list java`)을 말할 수 있다
- [ ] `java -version`이 JDK 21이 아닌 버전을 보여줄 때 확인할 명령 2개(`which java`, `sdk current java`)를 말할 수 있다
- [ ] `implementation`, `testImplementation`, `testRuntimeOnly`에 각각 들어가는 의존성 예를 하나씩 들 수 있다
- [ ] `gradle test`와 `./gradlew test`가 각각 어떤 Gradle 버전으로 실행되는지 설명할 수 있다
- [ ] Wrapper 파일 4개(`gradlew`, `gradlew.bat`, `gradle-wrapper.jar`, `gradle-wrapper.properties`)의 역할과 커밋해야 하는 이유를 말할 수 있다
- [ ] `./gradlew test`를 두 번 연속 실행했을 때 두 번째에 `UP-TO-DATE`가 나오는 조건을 말할 수 있다
- [ ] `platform("org.junit:junit-bom:5.11.4")`를 쓰면 `junit-jupiter`에 버전을 적지 않아도 되는 이유를 말할 수 있다
- [ ] `@NullAndEmptySource`와 `@ValueSource(strings = {" ", "   "})`를 함께 쓰면 테스트가 몇 번 실행되는지 말할 수 있다 (4번)
- [ ] GitHub Actions 워크플로 파일이 레포 루트의 `.github/workflows/`에 있어야 하는 이유를 말할 수 있다
- [ ] `push`와 `pull_request`를 모두 트리거로 둘 때 PR 브랜치에 push하면 워크플로가 몇 번 실행되는지 말할 수 있다
- [ ] CI에서 `./gradlew: Permission denied`가 나올 때 확인 명령(`git ls-files -s`)과 해결 명령(`git update-index --chmod=+x`)을 말할 수 있다

## Phase 1 — Java 기본기 + TDD

### BigDecimal과 반올림
- [ ] `(long) (10_000_000 * 0.0003)`의 결과(2999)와 그 이유를 설명할 수 있다
- [ ] `new BigDecimal(0.1)`, `BigDecimal.valueOf(0.1)`, `new BigDecimal("0.1")`의 값 차이를 말할 수 있다
- [ ] `new BigDecimal("1.0").equals(new BigDecimal("1.00"))`와 `compareTo` 결과를 각각 말할 수 있다
- [ ] `BigDecimal.ONE.divide(new BigDecimal("3"))`가 예외를 던지는 이유와 고치는 방법을 말할 수 있다
- [ ] 0.5, 1.5, 2.5, 3.5를 `HALF_UP`과 `HALF_EVEN`으로 반올림한 합(10, 8)을 계산할 수 있다
- [ ] `new BigDecimal("100.5").setScale(0)`이 던지는 예외와, 이를 `Money.of` 검증에 쓰는 방법을 말할 수 있다
- [ ] `setScale(-1, RoundingMode.DOWN)`이 하는 일을 예(4,027.38 → 4,020)로 설명할 수 있다

### 값 객체·불변·equals
- [ ] `record Money(BigDecimal amount, Currency currency)`에서 정규화를 빼면 `HashSet` 테스트가 실패하는 이유를 설명할 수 있다
- [ ] `equals`만 재정의하고 `hashCode`를 재정의하지 않으면 `HashMap.get`이 실패하는 과정을 버킷 단위로 설명할 수 있다
- [ ] 불변 객체를 만드는 규칙 6가지를 말할 수 있다
- [ ] JLS 17.5의 final 필드 보장이 무엇이고, 생성자에서 `this`가 노출되면 왜 보장이 사라지는지 설명할 수 있다
- [ ] `DecimalFormat` 인스턴스를 enum 필드로 공유하면 안 되는 이유를 Javadoc 문장으로 말할 수 있다
- [ ] `new DecimalFormat("#,##0.00")`이 독일 Locale에서 `1.234,50`을 출력하는 이유와 `DecimalFormatSymbols.getInstance(Locale.ROOT)`로 고치는 방법을 말할 수 있다

### 엔티티와 예외
- [ ] `Account`의 `equals`/`hashCode`를 계좌번호로만 계산하는 이유를 `HashSet` 예로 설명할 수 있다
- [ ] `AccountStatus` 3×3 전이 표에서 `true`인 4개 조합을 말할 수 있다
- [ ] `FROZEN` 계좌에 0원을 입금하면 어떤 예외가 나가는지와, 검사 순서를 요구사항으로 고정하는 이유를 말할 수 있다
- [ ] JDK 21에서 enum 생성자 인자로 뒤에 선언된 상수를 참조하면 어떤 컴파일 오류가 나는지, 대안 3가지를 말할 수 있다
- [ ] 도메인 예외를 unchecked로 만드는 이유 2가지(`throws` 전파, Spring `@Transactional` 기본 롤백 규칙)를 말할 수 있다
- [ ] 예외 메시지와 `AccountNumber.toString()`에 마스킹 번호를 쓰는 이유를 말할 수 있다

### 원장과 시간
- [ ] `REVERSAL`의 잔액 방향을 `TransactionType`만으로 정할 수 없는 이유와, `replayBalance`가 원거래를 조회하는 방법을 설명할 수 있다
- [ ] `Clock`과 거래 ID 생성을 `Account`가 아니라 `BankService`에 두는 이유를 말할 수 있다
- [ ] `Clock.fixed(Instant.parse("2026-01-15T10:00:00Z"), ZoneId.of("Asia/Seoul"))`에서 `LocalDateTime.now(clock)`이 19:00을 반환하는 이유를 말할 수 있다
- [ ] 기간 조회에 `[from.atStartOfDay(), to.plusDays(1).atStartOfDay())` 반열린 구간을 쓰는 이유를 말할 수 있다
- [ ] 이체 대상 계좌가 `FROZEN`일 때 출금 계좌가 바뀌지 않게 하는 검사 → 변경 순서를 설명할 수 있다

### 이자와 세금
- [ ] 원금 10,000,000원, 연 3.65%, 2028-01-01 하루 이자가 365일 기준 1,000원, 366일 기준 997원인 계산을 할 수 있다
- [ ] 2027-12-31 ~ 2028-01-02 실제 일수 기준 이자(1,997원)를 손으로 계산할 수 있다
- [ ] 월복리 10,000,000원, 연 3.6%, 3개월 이자(30,000 + 30,090 + 30,180 = 90,270원)를 손으로 계산할 수 있다
- [ ] 이자 28,767원의 소득세(4,020), 지방소득세(400), 세후(24,347)를 계산하고, 15.4%를 한 번에 곱하면 4,430원이 되어 틀리는 이유를 말할 수 있다
- [ ] 지방소득세가 "이자 × 1.4%"가 아니라 "원천징수 소득세 × 10%"인 것을 국세청 예시(10,000원 → 1,400 / 140 / 8,460)로 설명할 수 있다

### 종합과 커버리지
- [ ] `BankService`가 `System.in`/`System.out`을 모르게 만든 구조에서 가짜 `InputView`로 콘솔 흐름을 테스트하는 방법을 설명할 수 있다
- [ ] `./gradlew test jacocoTestReport jacocoTestCoverageVerification`이 하는 일 3가지와 리포트 경로를 말할 수 있다
- [ ] JaCoCo `LINE` 카운터와 `BRANCH` 카운터의 차이를, 라인 100%인데 버그가 남는 예로 설명할 수 있다

## Phase 2 — Java 동시성

### 원자성·가시성·순서
- [ ] `count++`의 바이트코드 명령어(`getfield`, `iconst_1`, `iadd`, `putfield`)를 적고, 스레드 2개가 어느 지점에서 끼어들면 증가 1회가 사라지는지 설명한다 (M2-1)
- [ ] `volatile`이 보장하는 것(가시성, 변수 1개의 읽기·쓰기 원자성 — `long`/`double` 포함)과 보장하지 않는 것(`count++` 같은 복합 연산)을 각각 예로 든다 (README 3절)
- [ ] `volatile` 없는 `while (!stopped)` 루프가 끝나지 않을 수 있는 이유를 JIT의 읽기 끌어올리기(hoisting)와 happens-before 부재로 설명한다 (M2-1)
- [ ] happens-before를 만드는 동작 4가지(`volatile` 쓰기→읽기, 모니터 unlock→lock, `Thread.start()`, `Thread.join()`)를 말한다 (README 1절)
- [ ] 순서 문제의 해결 "도구"와 happens-before "규칙"의 차이를 설명한다 (README 1절)

### 락과 데드락
- [ ] 잔액 100,000원에서 3,000원 출금 50건이 동시에 오면 성공 33건, 실패 17건, 잔액 1,000원이 되는 계산을 보인다 (M2-2)
- [ ] 전역 락과 계좌별 락의 처리량 차이를 내 측정표 숫자로 설명하고, 계좌별 작업(W1)에서 락 없는 버전도 정합성이 맞는 이유를 말한다 (M2-2)
- [ ] `CopyOnWriteArrayList`에 100,000건을 추가할 때 복사되는 원소 참조 수(5,000,050,000개)를 계산하고, 거래내역 저장에 쓰지 않는 이유를 말한다 (M2-2)
- [ ] 데드락 4조건을 말하고, 락 순서가 깨는 조건(순환 대기)과 `tryLock` 타임아웃이 깨는 조건(점유 대기)을 구분한다 (README 4절, M2-3, M2-4)
- [ ] `synchronized`에서 데드락에 빠진 스레드가 `interrupt()`와 `shutdownNow()`로 풀리지 않는 이유와, 그래서 재현 테스트를 데몬 스레드 + `@Tag("deadlock-demo")`로 격리한 이유를 설명한다 (M2-3)
- [ ] `jstack` 출력의 `Found one Java-level deadlock:` 절에서 스레드별로 쥔 모니터와 기다리는 모니터를 읽어 낸다 (M2-3)
- [ ] `AccountNumber`의 문자열 순서가 숫자 순서와 같은 이유(자리수 고정 형식)와, `identityHashCode`로 락 순서를 정하면 생기는 문제를 말한다 (M2-3)

### `ReentrantLock`
- [ ] `synchronized`와 `ReentrantLock`의 차이 4가지(타임아웃, 인터럽트 가능 대기, 공정성, `Condition`)를 말한다 (M2-4)
- [ ] `tryLock`이 `false`를 반환했을 때 `unlock()`을 호출하면 무슨 예외가 나는지 말한다 (`IllegalMonitorStateException`) (M2-4)
- [ ] 두 락을 합계 시간 제한 안에서 얻는 방법(남은 시간 계산)과 실패 시 먼저 얻은 락을 푸는 이유를 설명한다 (M2-4)
- [ ] 락 순서 없는 `tryLock` 재시도에서 라이브락이 생기는 순서를 그리고, 1~10ms 랜덤 백오프가 재시도 횟수를 줄인 정도를 내 측정표 숫자로 말한다 (M2-4)
- [ ] 인자 없는 `tryLock()`이 공정 락에서도 대기열을 무시한다는 점과, 공정 락과 비공정 락의 처리량 차이를 내 측정표 숫자로 말한다 (M2-4)

### CAS
- [ ] CAS 재시도 루프의 흐름(읽기 → 검사 → 새 값 계산 → `compareAndSet` → 실패 시 다시 읽기)을 의사 코드로 쓴다 (M2-5)
- [ ] `AtomicReference.compareAndSet`이 `equals`가 아니라 `==`로 비교한다는 점이 `get()`으로 얻은 참조를 쓸 때 문제가 되지 않는 이유를 말한다 (M2-5)
- [ ] 스레드 100개가 각 1회씩 변경할 때 재시도가 최대 99회인 이유를 설명한다 (M2-5)
- [ ] ABA 문제를 `AtomicLong` 잔액 10,000 → 5,000 → 10,000 예로 설명하고, `version`/스탬프가 막는 원리를 말한다 (M2-5)
- [ ] `LongAdder`가 스레드 64개에서 `AtomicInteger`보다 빠른 이유(셀 분산)와 대가(`sum()`이 정확한 순간값이 아님)를 말한다 (M2-5)
- [ ] CAS로 두 계좌 이체를 원자적으로 만들 수 없는 이유를 말한다 (M2-5)
- [ ] JPA `@Version`과 M2-5 3단계의 같은 점(버전 비교 후 교체)과 다른 점(`UPDATE ... WHERE version = ?`의 영향받은 행 수로 실패 감지)을 말한다 (M2-5)

### 스레드 풀과 가상 스레드
- [ ] 고정 풀(100)에 100ms 작업 10,000개를 넣으면 약 10초, 단일 스레드 풀에 100개면 약 10초가 걸리는 계산을 보인다 (M2-6)
- [ ] `ThreadPoolExecutor(2, 4, 큐 10)`에 1초 작업 20개를 넣으면 6개가 거절되는 순서(core → 큐 → max → 거절)를 설명한다 (M2-6)
- [ ] 플랫폼 스레드 수를 `ThreadMXBean.getPeakThreadCount()`로 재는 이유와 `Thread.activeCount()`의 한계를 말한다 (M2-6)
- [ ] `orTimeout`과 `completeOnTimeout`의 차이, `orTimeout` 이후에도 이미 실행 중인 앞 단계 작업이 계속 실행되는 이유를 말한다 (M2-6)
- [ ] JDK 21에서 `synchronized` 안의 `Thread.sleep(50)`이 가상 스레드 1,000개 실행 시간을 약 ⌈1,000 ÷ 코어 수⌉ × 50ms로 늘리는 이유(pinning)를 설명한다 (M2-6)
- [ ] pinning 관찰 방법을 JDK 버전별로 말한다: JDK 21~23은 `-Djdk.tracePinnedThreads`, JDK 21 이상 공통은 JFR `jdk.VirtualThreadPinned`, JDK 24부터는 JEP 491로 `synchronized` pinning 해소 (M2-6)
- [ ] `InterruptedException`을 잡았을 때 해야 하는 두 가지 중 하나(플래그 복구 또는 다시 던지기)와 삼키면 생기는 문제를 말한다 (M2-6)

### 이체 엔진
- [ ] 1일 한도 확인과 출금을 같은 출금 계좌 락 안에서 해야 하는 이유를, 동시 10건 중 5건만 성공해야 하는 시나리오로 설명한다 (M2-7)
- [ ] 한도 날짜를 주입한 `Clock`(Asia/Seoul)으로 계산해야 자정 경계 테스트가 가능한 이유를 말한다 (M2-7)
- [ ] 같은 `requestId`가 (1) 동시에 100건 (2) 다른 내용으로 (3) 첫 요청 처리 중에 올 때 각각의 동작을 말한다 (M2-7)
- [ ] `LockAcquisitionTimeoutException`을 멱등성 저장 대상에서 뺀 이유를 말한다 (M2-7)
- [ ] 서버를 2대로 늘리면 `ConcurrentHashMap` 멱등성 저장소와 계좌별 `ReentrantLock`이 각각 무엇을 보장하지 못하는지 말한다 (M2-7 → Phase 5~8)

### 측정
- [ ] README 6절 성능 측정 규칙(워밍업 3회, 측정 5회, 중앙값, JDK 버전·코어 수·OS 기록)을 말하고, 각 규칙이 없으면 생기는 왜곡을 하나씩 든다
- [ ] JMH가 직접 만든 `System.nanoTime()` 측정보다 정확한 이유 하나(죽은 코드 제거 방지 등)를 말한다

## Phase 3 — Spring Core

### IoC / DI
- [ ] Spring 없이 생성자 주입 컨테이너를 만들 때 필요한 단계 4가지(패키지 스캔 → 생성자 선택 → 파라미터 타입으로 빈 찾기 → 싱글톤 캐시)를 순서대로 말할 수 있다 (확인: M3-1 `MiniContainer` 코드와 대조)
- [ ] `A(B)`, `B(A)` 생성자 순환 참조가 시작 시점에 실패하는 이유와, Spring에서 최하위 원인 예외 클래스 이름(`BeanCurrentlyInCreationException`)을 말할 수 있다 (확인: M3-1 완료 기준 테스트)
- [ ] 인터페이스 타입 주입에서 구현체가 0개일 때와 2개일 때 Spring이 던지는 예외 이름(`NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException`)과 2개일 때 해결 수단 2가지(`@Primary`, `@Qualifier`)를 말할 수 있다
- [ ] 필드 주입 대신 생성자 주입을 쓰는 이유 3가지(불변 필드, Spring 없이 `new`로 테스트, 순환 참조 조기 발견)를 말할 수 있다

### 빈 스코프·라이프사이클
- [ ] 싱글톤 빈의 콜백 순서 `생성자 → setter 주입 → @PostConstruct → afterPropertiesSet → ContextRefreshedEvent → (close) → @PreDestroy → destroy`를 보지 않고 쓸 수 있다 (확인: M3-3 시나리오 1)
- [ ] 프로토타입 빈을 싱글톤에 생성자로 주입하면 인스턴스가 몇 개 생기는지, `ObjectProvider.getObject()`를 쓰면 어떻게 달라지는지 말할 수 있다 (확인: M3-3 시나리오 3·4)
- [ ] 프로토타입 빈의 `@PreDestroy`가 호출되지 않는 이유를 말할 수 있다
- [ ] 요청별 값을 필드에 저장한 싱글톤 빈이 동시 요청에서 일으키는 결과(다른 요청의 명령 실행, 총액은 보존되지만 계좌별 잔액 불일치)를 예시 숫자로 설명할 수 있다 (확인: `docs/M3-3-singleton-state.md`)

### 프록시
- [ ] JDK 동적 프록시와 CGLIB 프록시의 차이 3가지(인터페이스 필요 여부, 생성 클래스 형태, final 메서드 처리)를 말할 수 있다
- [ ] JDK 동적 프록시의 `InvocationHandler`에서 `InvocationTargetException`을 풀지 않으면 호출자가 받는 예외(`UndeclaredThrowableException`)를 말할 수 있다 (확인: M3-4 시나리오 3)
- [ ] CGLIB 프록시에서 `final` 메서드가 필드 값 대신 `null`을 반환하는 이유(Objenesis로 생성자 미호출 + 오버라이드 불가)를 말할 수 있다 (확인: M3-4 시나리오 13)
- [ ] `final` 클래스에 Spring AOP를 적용하면 언제 어떤 예외로 실패하는지(시작 시점, `AopConfigException: Could not generate CGLIB subclass`) 말할 수 있다

### AOP
- [ ] Aspect, JoinPoint, Pointcut, Advice를 M3-5의 `AuditAspect` 코드 위치로 하나씩 가리킬 수 있다
- [ ] Spring AOP에서 같은 클래스 내부 메서드 호출에 어드바이스가 적용되지 않는 이유를 "`this`는 프록시가 아니라 target"이라는 문장으로 설명하고, 해결책 2가지(빈 분리, `@Lazy` 자기 주입)의 단점을 각각 1개씩 말할 수 있다 (확인: `docs/M3-5-self-invocation-fixes.md`)
- [ ] `ThreadLocal`을 `finally`에서 정리하지 않으면 스레드 풀에서 생기는 일을 1스레드 풀 예시로 설명할 수 있다 (확인: M3-5 시나리오 6)
- [ ] `@Configuration` 클래스의 `@Bean` 메서드를 두 번 호출해도 같은 객체가 나오는 이유와, `proxyBeanMethods = false`일 때 달라지는 점을 말할 수 있다

### 설정과 테스트
- [ ] `@ConfigurationProperties` record에 `@Validated`를 붙였을 때 잘못된 값이 언제(애플리케이션 시작 시) 어떤 예외(`BindValidationException`)로 드러나는지 말할 수 있다
- [ ] `Duration` 설정에 단위 없이 `3`을 쓰면 어떻게 해석되는지(3ms) 말할 수 있다 (확인: M3-6 시나리오 10)
- [ ] 명령행 인자, 환경 변수, 프로파일별 YAML, 기본 `application.yml`의 우선순위를 높은 순서로 말할 수 있다 (확인: M3-6 시나리오 23)
- [ ] 순수 단위 테스트, `ApplicationContextRunner`, `@SpringBootTest` 중 어느 것을 쓸지 고르는 기준을 M3-2·M3-6에서 측정한 실행 시간과 함께 말할 수 있다
- [ ] Spring Boot 4에서 `@MockBean` 대신 쓰는 애노테이션 이름(`@MockitoBean`)과 패키지(`org.springframework.test.context.bean.override.mockito`)를 말할 수 있다
- [ ] `@SpringBootTest` 컨텍스트 캐시 때문에 테스트 클래스 사이에 싱글톤 빈 상태가 공유되는 것을 예로 들고, 이를 피하는 방법 2가지(테스트별 데이터 대역, `@BeforeEach` 정리)를 말할 수 있다

## Phase 4 — Spring Web, API, 보안

- [ ] `curl -v` 출력에서 요청 줄, 요청 헤더, 상태 줄, 응답 헤더, 본문을 각각 짚을 수 있다
- [ ] 요청이 `DispatcherServlet` → `HandlerMapping` → `HandlerAdapter` → `HandlerMethodArgumentResolver` → 컨트롤러 → `HttpMessageConverter` 순서로 처리되는 과정을 그림 없이 말할 수 있다
- [ ] 이 레포의 상태 코드 규칙에서 400, 404, 409, 422, 503을 각각 어떤 경우에 쓰는지 예를 하나씩 들 수 있다
- [ ] `POST /accounts` 성공 응답이 201과 `Location` 헤더를 돌려주는 이유를 말할 수 있다
- [ ] `ProblemDetail`의 표준 필드 5개(`type`, `title`, `status`, `detail`, `instance`)와 이 레포가 추가한 `code` 필드의 용도를 말할 수 있다
- [ ] 같은 `Idempotency-Key`로 (1) 같은 본문 재요청, (2) 다른 본문 요청, (3) 첫 요청 처리 중 재요청이 왔을 때 각각의 응답을 말할 수 있다
- [ ] 오프셋 페이지네이션이 새 거래가 추가될 때 중복·누락을 만드는 예를 숫자로 들고, 커서 페이지네이션이 이를 막는 이유를 말할 수 있다
- [ ] JavaScript `Number.MAX_SAFE_INTEGER`(2^53 − 1) 때문에 금액을 JSON 문자열로 보내는 이유를 예시 숫자로 설명할 수 있다
- [ ] 401과 403의 차이를 Spring Security가 각각 어느 컴포넌트(`AuthenticationEntryPoint`, `AccessDeniedHandler`)에서 만드는지와 함께 말할 수 있다
- [ ] 다른 사람의 계좌 조회에 403 대신 404를 돌려주는 이유를 말할 수 있다
- [ ] 이 API에서 CSRF 보호를 끈 근거(무상태, 쿠키 미사용)와, 쿠키 세션을 쓰면 다시 켜야 하는 이유를 말할 수 있다
- [ ] MDC에 넣은 요청 ID를 `finally`에서 지워야 하는 이유를 스레드 풀 재사용과 연결해 말할 수 있다

## Phase 5 — SQL, JDBC, JPA, 트랜잭션

- [ ] `INNER JOIN`과 `LEFT JOIN`의 결과 행 수가 달라지는 데이터 예를 직접 만들 수 있다
- [ ] 복합 인덱스 `(account_id, occurred_at)`가 `WHERE occurred_at > ?`만 있는 쿼리에 쓰이지 않는 이유를 말할 수 있다
- [ ] 순수 JDBC로 이체를 구현할 때 `setAutoCommit(false)`, `commit()`, `rollback()`, `close()`를 어디에 두는지 말할 수 있다
- [ ] 영속성 컨텍스트의 1차 캐시, 더티 체킹, 플러시 시점 3가지를 예시 코드 흐름으로 설명할 수 있다
- [ ] N+1 문제를 쿼리 개수로 보여주고, fetch join, `@EntityGraph`, `default_batch_fetch_size`가 각각 쿼리 개수를 몇 개로 바꾸는지 말할 수 있다
- [ ] `@Transactional`이 프록시 + `PlatformTransactionManager` + `TransactionSynchronizationManager`(스레드에 묶인 커넥션)로 동작하는 순서를 말할 수 있다
- [ ] checked 예외가 기본 설정에서 롤백되지 않는다는 것과 `rollbackFor`로 바꾸는 방법을 말할 수 있다
- [ ] `REQUIRES_NEW` 안쪽 예외를 바깥에서 잡았을 때와 `REQUIRED` 안쪽 예외를 바깥에서 잡았을 때 결과(`UnexpectedRollbackException` 포함)의 차이를 말할 수 있다
- [ ] MySQL REPEATABLE READ에서 일반 `SELECT`에는 팬텀이 보이지 않지만 `SELECT ... FOR UPDATE`는 최신 커밋 행을 읽는 이유를 MVCC 스냅샷으로 설명할 수 있다
- [ ] 레코드 락, 갭 락, 넥스트 키 락의 차이를 `performance_schema.data_locks`의 `LOCK_MODE` 값과 연결해 말할 수 있다
- [ ] `@Transactional`만 붙인 출금 코드가 lost update를 막지 못하는 이유를 인터리빙으로 설명할 수 있다
- [ ] 비관적 락, 낙관적 락(`@Version`), 조건부 UPDATE 중 하나를 고를 때 충돌 빈도, 재시도 비용, 처리량 기준으로 판단 근거를 말할 수 있다
- [ ] InnoDB 데드락 로그에서 두 트랜잭션이 각각 보유한 락과 기다린 락을 찾아 읽을 수 있다
- [ ] 트랜잭션 안에서 외부 API를 호출하면 커넥션 풀이 고갈되는 과정을 `maximumPoolSize`와 함께 설명할 수 있다

## Phase 6 — 코어뱅킹

### 설계·상태 머신
- [ ] 계좌 상태 4개(`ACTIVE`, `SUSPENDED`, `DORMANT`, `CLOSED`)와 허용 전이 7개를 보지 않고 쓰고, 표에 없는 전이 3개를 예로 들 수 있다 (확인: M6-1 `state-machine.md`)
- [ ] 휴면 판정 규칙 `L + 365일 < D`에서 L = 2025-11-10일 때 휴면이 되는 첫 날짜(2026-11-11)를 말할 수 있다 (확인: M6-1 시나리오 4)
- [ ] 고객 거래내역 테이블 이름을 `transaction`으로 하지 않은 이유(MySQL 키워드)를 말할 수 있다

### 복식부기
- [ ] 은행 입장에서 고객예금이 부채인 이유와, 자산·부채·비용 계정의 증가가 각각 차변/대변 중 어디인지 말할 수 있다 (확인: `fintech-domain-facts` 6절)
- [ ] 이자 10,000원 지급, 원천징수 1,540원 분개의 차변·대변 4줄을 금액까지 쓸 수 있다 (이자비용 10,000 / 고객예금 8,460, 예수소득세 1,400, 예수지방소득세 140)
- [ ] 잘못 기록한 분개를 UPDATE하지 않고 반대 분개로 바로잡는 이유를 감사 관점에서 말할 수 있다
- [ ] 불균형 분개를 팩터리·서비스·DB 트리거 중 어디서 막는지와 각 위치가 막는 경로를 말할 수 있다 (확인: M6-2 `ledger-design.md`)

### 멱등성·동시성
- [ ] 멱등 레코드 상태 3개(`IN_PROGRESS`, `COMPLETED`, `FAILED`)와 같은 키 재요청 4가지 경우(처음, 완료+같은 본문, 처리 중, 완료+다른 본문)의 응답 코드를 말할 수 있다 (확인: M6-3 3절)
- [ ] "SELECT로 확인 후 INSERT"만으로 중복 요청을 막을 수 없는 이유를 두 요청의 실행 순서로 설명할 수 있다
- [ ] 오래된 `IN_PROGRESS`를 이어받을 때 `owner_token` 비교가 없으면 돈이 두 번 움직이는 순서를 단계별로 말할 수 있다 (확인: M6-3 시나리오 15)
- [ ] 비밀번호 오류 횟수 증가가 422 응답과 함께 롤백되면 생기는 보안 문제와, 이를 막는 트랜잭션 전파 설정을 말할 수 있다 (확인: M6-4 힌트 1)
- [ ] 1일 한도 날짜를 JVM 기본 시간대로 구하면 한국 시각 몇 시~몇 시 이체가 전날로 집계되는지 말할 수 있다 (JVM 기본 시간대가 UTC일 때 한국 시각 00:00:00~08:59:59)

### 배치·대사
- [ ] `JobInstance`와 `JobExecution`의 차이를 재시작 예시(1,000계좌, 청크 100, 250번째 실패)로 설명하고, 재시작 시 읽는 건수(800)를 말할 수 있다 (확인: M6-5 시나리오 10)
- [ ] Spring Batch 6의 기본 `JobRepository`가 `ResourcelessJobRepository`라는 것과, 재시작이 필요한 Job에서 JDBC 저장소를 쓰는 이유를 말할 수 있다
- [ ] 이자 28,767원의 소득세·지방소득세·실지급액(4,020 / 400 / 24,347)을 계산 순서대로 구하고, 15.4%를 한 번에 곱하면 왜 다른지 말할 수 있다 (확인: `fintech-domain-facts` 1절)
- [ ] 대사 규칙 R2에서 `balance`와 분개 합계를 같은 트랜잭션에서 읽어야 하는 이유를 동시 이체 예시로 설명할 수 있다 (확인: M6-6 시나리오 7)
- [ ] 대사 Job이 불일치를 자동으로 고치지 않는 이유를 말할 수 있다

### 대외 연동
- [ ] 타임아웃 후 실제로 일어났을 수 있는 3가지 경우와, 각 경우에 "실패"로 보고 환불하면 생기는 사고를 말할 수 있다 (확인: README 7절)
- [ ] 재시도해도 되는 실패(연결 실패, 503)와 재시도하면 안 되는 실패(읽기 타임아웃)를 구분하는 기준을 말할 수 있다
- [ ] 서킷 브레이커 상태 3개와, `OPEN`일 때 출금 전에 거절하는 이유를 INV-4로 설명할 수 있다 (확인: M6-7 시나리오 10)

### 분산락
- [ ] 인스턴스 2대에서 `ReentrantLock`이 lost update를 막지 못하는 이유와 E1 실험 결과 숫자를 말할 수 있다 (확인: M6-8 `distributed-lock-report.md`)
- [ ] Redis 락의 lease 만료와 프로세스 정지(`kill -STOP`)가 같은 계좌에 "락 보유자 2명"을 만드는 순서를 설명하고, 펜싱 토큰(`version` 조건부 UPDATE)이 그 쓰기를 거부하는 원리를 말할 수 있다 (확인: M6-8 E4)

## Phase 7 — 증권 매매

- [ ] 예수금, D+2 예수금, 주문가능금액, 보유수량, 매도가능수량의 차이를 매수 주문 1건이 체결·결제될 때까지의 값 변화로 설명할 수 있다
- [ ] KRX 호가단위 표 7개 구간을 보지 않고 쓰고, 2,001원과 20,010원이 무효인 이유를 말할 수 있다
- [ ] 가격-시간 우선 원칙과 체결 가격이 대기 주문(resting order)의 가격으로 정해지는 이유를 예시 호가창으로 설명할 수 있다
- [ ] 홀드와 가수금이 다른 개념인 이유를 말할 수 있다
- [ ] 매수 주문 접수, 부분 체결, 취소 각각에서 홀드 금액이 얼마나 바뀌는지 숫자 예로 계산할 수 있다
- [ ] 증권거래세가 매도에만 붙고, 2026년 기준 코스피는 거래세 0.05% + 농어촌특별세 0.15%, 코스닥은 0.20%라는 것을 말할 수 있다
- [ ] 월요일 체결이 수요일에, 금요일 체결이 다음 주 화요일에 결제되는 이유(T+2 영업일)를 말할 수 있다
- [ ] 매수 체결 시 평균단가가 바뀌고 매도 체결 시 평균단가는 그대로이며 실현손익이 생기는 계산을 직접 할 수 있다
- [ ] 매칭 엔진을 락 대신 종목별 단일 스레드로 돌리면 결정성과 지연시간에서 얻는 것을 말할 수 있다
- [ ] 취소 요청과 체결이 경합할 때 이 레포의 규칙상 결과가 어떻게 정해지는지 말할 수 있다
- [ ] 이벤트 소싱으로 호가창을 복구할 때 스냅샷과 이후 이벤트 재생이 필요한 이유, 재생 결과가 같다는 것을 확인하는 방법을 말할 수 있다

## Phase 8 — 분산 환경과 운영

- [ ] DB 커밋 후 Kafka 발행 실패, Kafka 발행 후 DB 롤백 두 경우에 각각 어떤 불일치가 생기는지 말할 수 있다
- [ ] Transactional Outbox가 이중 쓰기 문제를 푸는 방법과, 릴레이가 같은 메시지를 두 번 보낼 수 있는 이유를 말할 수 있다
- [ ] 멱등 컨슈머가 처리 기록 테이블과 비즈니스 변경을 같은 트랜잭션에 넣어야 하는 이유를 말할 수 있다
- [ ] Kafka의 순서 보장 범위가 파티션 하나라는 것과 메시지 키를 계좌번호·주문 ID로 정하는 이유를 말할 수 있다
- [ ] 오케스트레이션 Saga와 코레오그래피 Saga의 차이를 상태 관리 위치, 장애 추적, 결합도 기준으로 말할 수 있다
- [ ] Saga에서 되돌릴 수 없는 단계(체결) 이후 실패를 보상 대신 재시도로 처리하는 이유를 말할 수 있다
- [ ] 메트릭, 로그, 트레이스가 각각 답하는 질문과 이 레포에서 쓰는 도구(Prometheus, 로그 + MDC, OpenTelemetry)를 짝지을 수 있다
- [ ] `histogram_quantile(0.99, ...)` PromQL이 계산하는 값과 평균 응답시간 대신 p99를 보는 이유를 말할 수 있다
- [ ] 리틀의 법칙(L = λ × W)으로 초당 500건, 평균 200ms일 때 동시에 처리 중인 요청 수(100)를 계산할 수 있다
- [ ] 부하 테스트에서 한 번에 한 가지만 바꾸고 측정해야 하는 이유를 말할 수 있다

