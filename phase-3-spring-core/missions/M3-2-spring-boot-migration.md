# M3-2 Spring Boot로 이식

> 가이드 수준: L2 · 예상 시간: 3~4h · 선행: M3-1

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- Phase 2 이체 엔진을 웹 없는 Spring Boot 4.1 애플리케이션으로 옮기고, `BankApplication`의 `new` 키워드를 0개로 만든다.
- 클래스마다 빈으로 등록할지, `@Component`와 `@Bean` 중 무엇으로 등록할지를 표로 정하고 이유를 적는다.
- `@MockitoBean`으로 `Clock` 빈을 바꿔, 한국 시간 자정 경계에서 1일 이체 한도가 초기화되는 것을 테스트로 보여준다.
- 같은 규칙을 순수 단위 테스트와 `@SpringBootTest`로 각각 검증하고, 실행 시간을 측정해 언제 무엇을 쓸지 표로 정한다.

## 배경
M3-1에서 만든 컨테이너가 하던 일(스캔, 생성자 주입, 싱글톤)을 이제 Spring이 한다. 이체 엔진의 1일 한도는 "오늘"이 언제인지에 달려 있다. 서버 기본 시간대가 UTC인 컨테이너에서 `LocalDate.now()`를 쓰면 한국 시간 00:00~08:59 사이 이체가 전날 한도에 합산된다. 고객은 오전 8시에 "한도 초과" 응답을 받고, 은행은 민원과 장애 보고서를 쓴다. 시간을 `Clock` 빈으로 주입받으면 테스트에서 자정 경계를 재현할 수 있고, 운영 시간대도 한 곳에서 정한다. README 1절, 5절, 6절을 먼저 읽는다.

## 요구사항
README "워크스페이스 만들기" 2단계로 Phase 2 코드를 복사한 상태에서 시작한다. 복사 직후 `./gradlew test` 결과의 테스트 개수를 기록해 둔다 (이하 N개).

### 1. 빈 등록 대상 정하기
1. 아래 기준으로 복사한 모든 클래스를 분류해 `docs/M3-2-bean-inventory.md`에 표로 적는다. 열: `클래스 | 빈 여부 | 등록 방법(@Component / @Bean / 해당 없음) | 이유`.
   - 빈으로 등록한다: 애플리케이션 전체에 1개만 있어야 하는 객체 (`TransferEngine` 구현체, `BankService`, 공유 저장소 역할의 `Ledger`, `Clock`, 멱등성 결과 저장소처럼 Phase 2에서 여러 객체가 같은 인스턴스를 공유하던 것)
   - 빈으로 등록하지 않는다: 요청마다 새로 만드는 값·엔티티 (`Money`, `AccountNumber`, `Account`, `Transaction`, `TransferCommand`, `TransferResult`, 예외)
2. 같은 문서 아래에 "조립 코드 비교" 절을 두고, Phase 2에서 조립에 쓰던 `new` 줄 수(이식 전)와 `BankApplication`의 `new` 줄 수(이식 후, 0)를 적는다.

### 2. 등록 방법
1. `lab.bank.BankApplication`에 `@SpringBootApplication`. 컴포넌트 스캔 범위는 `lab.bank`와 그 하위 패키지다.
2. 내 코드이고 생성자 파라미터가 전부 다른 빈 타입인 클래스는 `@Component`(또는 `@Service`)로 등록한다.
3. `Clock`은 JDK 클래스라 애노테이션을 붙일 수 없으므로 `lab.bank.config.BankConfig`(`@Configuration`)의 `@Bean` 메서드로 등록한다. 값: `Clock.system(ZoneId.of("Asia/Seoul"))`.
4. 생성자에 빈이 아닌 값 파라미터(예: `Money dailyLimit`, `Duration lockTimeout`)가 있는 클래스에 `@Component`를 붙이면 그 타입의 빈이 없어 시작이 `UnsatisfiedDependencyException`으로 실패한다. 이런 클래스는 `BankConfig`의 `@Bean` 메서드에서 값을 넣어 생성한다. 이 미션에서 한도 5,000,000원과 락 타임아웃 3초는 `BankConfig` 안의 상수로 둔다 (M3-6에서 `application.yml`로 옮긴다).
5. 주입은 생성자 주입만 쓴다. 의존성 필드는 모두 `private final`. 생성자가 1개면 `@Autowired`를 붙이지 않는다 (Spring 4.3부터 단일 생성자는 자동으로 주입 대상).
6. `TransferEngine` 타입 빈은 정확히 1개다.
7. 엔진이 내부에 `ExecutorService`를 가지고 있으면 `@PreDestroy` 메서드(또는 `@Bean`의 소멸 메서드)에서 `shutdown()`한다. 안 하면 3번의 `main`이 끝나도 JVM이 종료되지 않는다.

### 3. 시간 의존 코드
1. "오늘 날짜"와 "현재 시각"은 주입받은 `Clock`으로만 구한다 (`LocalDate.now(clock)`, `Instant.now(clock)`, `clock.instant()`). 인자 없는 `now()` 호출은 `src/main/java`에 0개.
2. 1일 한도의 "하루"는 **`Clock`의 시간대(Asia/Seoul) 기준 날짜**다. 2026-11-10 23:59:59 KST의 이체와 2026-11-11 00:00:00 KST의 이체는 서로 다른 날 한도에 합산된다. (이 미션의 규칙으로 정한다.)
3. 한도 규칙은 M2-7 그대로다: 계좌별 그날 누적 이체 금액이 5,000,000원을 **초과**하면 M2-7의 한도 초과 예외를 던지고 잔액은 바뀌지 않는다. 누적이 정확히 5,000,000원이면 성공이다.

### 4. 실행 진입점
1. `BankApplication.main`은 `SpringApplication.run`이 돌려준 `ConfigurableApplicationContext`를 try-with-resources로 열고, `TransferDemo` 빈을 꺼내 `run()`을 호출한 뒤 닫는다. `main`에는 `new`가 없다.
2. `lab.bank.TransferDemo`(`@Component`)의 `run()`은 M2-7의 계좌 등록 메서드 `addAccount(Account.open(...))`로 `110-1234-5678`과 `220-1234-5678`을 등록하고 `deposit`으로 `110-1234-5678`에 100,000원을 입금하고(`openAccount`는 번호를 자동 발급하므로 쓰지 않는다), `TransferEngine`으로 30,000원을 이체한 뒤 아래 2줄을 표준 출력에 찍는다. 형식: `{마스킹된 계좌번호} 잔액 {원 단위 정수}`
   ```
   110-****-5678 잔액 70000
   220-****-5678 잔액 30000
   ```
3. `./gradlew bootRun`은 위 2줄을 출력하고 종료 코드 0으로 끝난다.

## 테스트 시나리오
시나리오 5~7은 한 테스트 클래스(`DailyLimitClockSpringTest`, `@SpringBootTest` + `@MockitoBean Clock clock`) 안에서 한 테스트 메서드로 순서대로 실행한다. 목 `Clock`은 `getZone()`이 `ZoneId.of("Asia/Seoul")`, `instant()`가 각 단계의 시각을 반환하도록 스텁한다. 계좌는 `500-0000-0001`(시작 잔액 20,000,000원)에서 `500-0000-0002`(0원)로 이체한다.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | Phase 2에서 복사한 테스트 N개, 이 미션 코드 변경 후 | `./gradlew test` | 복사한 N개가 테스트 코드 수정 없이 통과 (생성자 시그니처를 바꿨으면 테스트의 `new` 호출만 고친다) |
| 2 | `@SpringBootTest` | `ApplicationContext.getBeansOfType(TransferEngine.class)` | 크기 1 |
| 3 | `@SpringBootTest` | `getBean(TransferEngine.class)` 2번 | 같은 인스턴스(`isSameAs`) |
| 4 | `@SpringBootTest` (목 없음) | `getBean(Clock.class).getZone()` | `ZoneId.of("Asia/Seoul")` |
| 5 | `instant()` = `2026-11-10T14:59:59Z` (= 2026-11-10 23:59:59 KST) | 5,000,000원 이체 | 성공. `500-0000-0001` 잔액 15,000,000원 |
| 6 | 5번 직후, 같은 시각 | 1원 이체 | M2-7의 한도 초과 예외. `500-0000-0001` 잔액 15,000,000원 그대로 |
| 7 | `instant()` = `2026-11-10T15:00:00Z` (= 2026-11-11 00:00:00 KST) | 5,000,000원 이체 | 성공. `500-0000-0001` 잔액 10,000,000원, `500-0000-0002` 잔액 10,000,000원 |
| 8 | Spring 없이 `new`로 엔진 조립, 테스트 소스의 `MutableClock`(직접 작성한 `Clock` 하위 클래스, 시각을 바꾸는 메서드 보유) 사용, 시간대 Asia/Seoul | 5~7번과 같은 3단계 | 5~7번과 같은 결과 |
| 9 | 8번과 같은 조립, `MutableClock` = 2026-11-10 08:59:59 KST, 같은 날 그 전에 4,000,000원 이체해 둠 | 1,000,000원 이체 | 성공 (누적 정확히 5,000,000원 — 경계값) |
| 10 | 9번 직후 | 1원 이체 | 한도 초과 예외 |
| 11 | 워크스페이스 루트 | `./gradlew bootRun` | 표준 출력에 `110-****-5678 잔액 70000`, `220-****-5678 잔액 30000` 2줄, 종료 코드 0 |

시나리오 5~7 계산: 20,000,000 − 5,000,000 = 15,000,000 → 6번은 그날 누적 5,000,001원이 되어 거절 → 날짜가 바뀌어 누적 0에서 다시 시작, 15,000,000 − 5,000,000 = 10,000,000.

## 제약
- 필드 주입(`@Autowired private X x;`) 금지 — README 1절. 테스트 클래스에서 `@Autowired` 필드로 빈을 받는 것은 허용한다.
- `src/main/java`에서 인자 없는 `LocalDate.now()`, `LocalDateTime.now()`, `Instant.now()`, `System.currentTimeMillis()`를 날짜·한도 계산에 쓰지 않는다 — 시간대가 서버 설정에 따라 달라진다. 실행 시간 측정용 `System.nanoTime()`은 허용한다.
- `@SpringBootTest` 테스트 클래스는 서로 다른 계좌번호 대역을 쓴다 (이 미션은 `500-0000-xxxx`). 같은 설정의 테스트 클래스끼리 컨텍스트와 싱글톤 빈의 상태를 공유하기 때문이다 (README 6절).
- `@MockBean`은 Spring Boot 4.0에서 삭제됐다. `org.springframework.test.context.bean.override.mockito.MockitoBean`을 쓴다.
- `spring-boot-starter-web`(또는 `webmvc`)을 추가하지 않는다 — 웹은 Phase 4.

## 힌트
<details>
<summary>힌트 1: 테스트 실행 시간 측정 위치</summary>

`./gradlew test` 후 `build/reports/tests/test/index.html`을 브라우저로 열면 "Classes" 탭에 테스트 클래스별 소요 시간이 있다. 측정 전 `./gradlew clean`을 하지 않으면 Gradle이 테스트를 건너뛰어(UP-TO-DATE) 이전 결과가 보인다. `./gradlew test --rerun-tasks`를 쓴다. 같은 설정의 `@SpringBootTest` 클래스가 2개 이상이면 두 번째 클래스는 컨텍스트 캐시 덕에 짧게 나온다. 왜 그런지 표에 한 줄로 적는다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 Phase 2에서 복사한 N개 + 시나리오 2~10 테스트가 모두 통과한다
- [ ] `grep -c "new " src/main/java/lab/bank/BankApplication.java` 결과가 `0`이다
- [ ] `grep -rnE "(LocalDate|LocalDateTime|Instant)\.now\(\)" src/main/java` 결과가 0줄이다
- [ ] `./gradlew bootRun` 출력에 시나리오 11의 2줄이 있고 프로세스가 스스로 종료된다
- [ ] `docs/M3-2-bean-inventory.md`에 요구사항 1의 표와 "조립 코드 비교" 절이 있다
- [ ] `docs/M3-2-test-timing.md`에 열 `테스트 클래스 | 종류(단위 / @SpringBootTest) | 테스트 수 | 실행 시간(초) | 이 종류를 고른 이유`인 표가 있고, 시나리오 5~7 클래스와 시나리오 8~10 클래스의 실행 시간이 둘 다 적혀 있다 (`./gradlew test --rerun-tasks` 1회 기준)

## 생각해볼 질문
1. 시나리오 5~7과 8~10은 같은 규칙을 검증한다. 두 테스트 중 하나만 남긴다면 무엇을 남기고, `@SpringBootTest`로만 잡을 수 있는 버그는 어떤 종류인가? (예: `Clock` 빈이 2개 등록됨, 엔진이 다른 `Clock`을 받음)
2. `BankConfig`에서 엔진을 `@Bean`으로 만들 때 `clock()` 메서드를 직접 호출하는 방식과 `@Bean` 메서드 파라미터로 `Clock`을 받는 방식이 있다. `@Configuration(proxyBeanMethods = false)`로 바꾸면 두 방식의 결과가 각각 어떻게 달라지는가? (README 5절)
3. 이 애플리케이션에서 `TransferEngine` 빈은 모든 스레드가 공유하는 싱글톤이다. Phase 2에서 엔진을 스레드 안전하게 만들었으니 문제없는가? 엔진이 아닌 다른 빈에 요청별 값을 필드로 저장하면 어떤 일이 생기는지 예측해 적고, M3-3에서 확인한다.
4. (Phase 4 연결) Phase 4에서 `spring-boot-starter-webmvc`를 추가하면 `TransferDemo` 대신 무엇이 `TransferEngine`을 호출하게 되나? 그때 요청 스레드는 몇 개이고, 그 스레드들이 같은 엔진 인스턴스를 쓰는가?
