# M3-6 설정 외부화와 프로파일

> 가이드 수준: L2 · 예상 시간: 3~4h · 선행: M3-2

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 이체 한도·락 타임아웃·시간대를 코드 상수에서 `application.yml`로 옮기고, `@ConfigurationProperties` record + `@Validated`로 타입과 범위를 검증한다.
- 잘못된 설정값 12가지(시나리오 2·3·5·6·9·10·12·13·14·15·16·17)에 대해 애플리케이션이 시작되지 않는 것을 `ApplicationContextRunner` 테스트로 보여주고, 실패 원인 예외 클래스를 값마다 단언한다.
- `local`/`test` 프로파일과 환경 변수·명령행 인자로 같은 jar의 설정을 바꾸고, 우선순위를 실행 결과로 기록한다.

## 배경
M3-2에서 1일 한도 5,000,000원과 락 타임아웃 3초는 `BankConfig` 안의 상수였다. 한도를 3,000,000원으로 낮추라는 지시가 오면 코드를 고치고 다시 빌드·배포해야 한다. 반대로 설정 파일로 빼기만 하고 검증하지 않으면 더 위험하다. 운영자가 `lock-timeout: 3`이라고 쓰면 단위 없는 숫자는 밀리초로 해석돼 3ms가 되고, 모든 이체가 락 대기 시간 초과로 실패한다. `daily-limit` 키 이름을 `daily-limt`로 잘못 쓰면 Spring은 모르는 키를 무시하므로, 검증이 없으면 한도가 0이나 기본값으로 조용히 바뀐다. 이 미션은 그런 설정으로는 애플리케이션이 아예 시작되지 않게 만든다. README 6절의 `ApplicationContextRunner` 설명을 먼저 읽는다.

## 요구사항
패키지: `lab.bank.config`.

### 1. `TransferProperties`
`@ConfigurationProperties(prefix = "lab.transfer")` + `@Validated`를 붙인 **record**. 컴포넌트 3개:

| 컴포넌트 | 타입 | YAML 키 | 제약 (이 미션의 규칙) | 사용할 제약 애노테이션 |
|---|---|---|---|---|
| `dailyLimit` | `long` (원 단위) | `lab.transfer.daily-limit` | 1 이상 | `jakarta.validation.constraints.Positive` |
| `lockTimeout` | `java.time.Duration` | `lab.transfer.lock-timeout` | 필수, 100ms 이상 10s 이하 (양 끝 포함) | `NotNull`, `org.hibernate.validator.constraints.time.DurationMin(millis = 100)`, `DurationMax(seconds = 10)` |
| `zone` | `java.time.ZoneId` | `lab.transfer.zone` | 필수 | `NotNull` |

- `dailyLimit`이 `long`(기본형)이라 키가 없으면 0으로 바인딩되고 `@Positive`에 걸린다. `Long`(참조형)으로 바꾸지 않는다 — 시나리오 15가 이 동작에 의존한다.
- `lab.bank.config.TransferPropertiesConfig`(`@Configuration` + `@EnableConfigurationProperties(TransferProperties.class)`)로 등록한다. 테스트 시나리오의 `ApplicationContextRunner`는 이 클래스 하나만 띄운다.

### 2. 사용처
1. `BankConfig`의 `Clock` 빈은 `Clock.system(properties.zone())`으로 만든다.
2. 엔진의 1일 한도는 `properties.dailyLimit()`을 Phase 1의 원화 `Money`로 바꿔 넣고, 락 대기 시간은 `properties.lockTimeout()`을 쓴다.
3. M3-2의 상수 5,000,000과 3초는 `src/main/java`에서 삭제한다.
4. `TransferDemo.run()`은 M3-2의 2줄보다 먼저 아래 형식의 1줄을 출력한다 (`Duration.toString()` 형식):
   ```
   설정: dailyLimit=5000000, lockTimeout=PT3S, zone=Asia/Seoul
   ```

### 3. 설정 파일 (아래 내용 그대로 작성)
`src/main/resources/application.yml`
```yaml
spring:
  application:
    name: bank

lab:
  transfer:
    daily-limit: 5000000
    lock-timeout: 3s
    zone: Asia/Seoul
```
`src/main/resources/application-local.yml` — 로컬 디버깅: 브레이크포인트에 멈춘 동안 락 타임아웃이 터지지 않게 길게
```yaml
lab:
  transfer:
    lock-timeout: 5s

logging:
  level:
    lab.bank: DEBUG
```
`src/main/resources/application-test.yml` — 테스트: 락 타임아웃 시나리오가 3초씩 기다리지 않게 짧게
```yaml
lab:
  transfer:
    lock-timeout: 200ms
```
- M3-2~M3-5의 `@SpringBootTest` 클래스 전부에 `@ActiveProfiles("test")`를 붙인다. 프로파일이 다른 테스트 클래스는 컨텍스트 캐시를 공유하지 않는다 (README 6절).
- 프로파일 파일은 기본 `application.yml`을 **덮어쓰는** 값만 적는다. `application-test.yml`에 없는 `daily-limit`은 기본 파일의 5,000,000이 쓰인다.

## 테스트 시나리오
시나리오 1~17은 `new ApplicationContextRunner().withUserConfiguration(TransferPropertiesConfig.class).withPropertyValues(...)`로 실행한다. "기본 3개"는 `lab.transfer.daily-limit=5000000`, `lab.transfer.lock-timeout=3s`, `lab.transfer.zone=Asia/Seoul`이고, 각 행은 기본 3개에서 해당 키 하나만 바꾸거나 뺀다. "실패"는 `context.getStartupFailure()`가 `null`이 아니라는 뜻이고, "최하위 원인"은 AssertJ `assertThat(context.getStartupFailure()).rootCause()`의 타입이다. 실패 메시지의 한국어/영어 문구는 JVM 로케일에 따라 달라지므로 문구 대신 필드 이름만 단언한다.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 기본 3개 | 컨텍스트 시작 | 성공. `dailyLimit()=5000000`, `lockTimeout()=Duration.ofSeconds(3)`, `zone()=ZoneId.of("Asia/Seoul")` |
| 2 | `daily-limit=0` | 시작 | 실패. 최하위 원인 `BindValidationException`, 메시지에 `dailyLimit` 포함 |
| 3 | `daily-limit=-1` | 시작 | 실패. 최하위 원인 `BindValidationException` |
| 4 | `daily-limit=1` | 시작 | 성공. `dailyLimit()=1` (경계값) |
| 5 | `daily-limit=5000000.5` | 시작 | 실패. 최하위 원인 `NumberFormatException` (검증 전에 타입 변환에서 실패) |
| 6 | `lock-timeout=99ms` | 시작 | 실패. 최하위 원인 `BindValidationException`, 메시지에 `lockTimeout` 포함 |
| 7 | `lock-timeout=100ms` | 시작 | 성공. `Duration.ofMillis(100)` (하한 경계) |
| 8 | `lock-timeout=10s` | 시작 | 성공. `Duration.ofSeconds(10)` (상한 경계) |
| 9 | `lock-timeout=10001ms` | 시작 | 실패. 최하위 원인 `BindValidationException` |
| 10 | `lock-timeout=3` (단위 없음) | 시작 | 실패. 단위 없는 숫자는 밀리초(3ms)로 해석돼 하한 미달. 최하위 원인 `BindValidationException` |
| 11 | `lock-timeout=PT3S` (ISO-8601) | 시작 | 성공. `Duration.ofSeconds(3)` |
| 12 | `lock-timeout=-1s` | 시작 | 실패 |
| 13 | `lock-timeout` 키 없음 | 시작 | 실패. 최하위 원인 `BindValidationException`, 메시지에 `lockTimeout` 포함 |
| 14 | `zone=Mars/Base` | 시작 | 실패. 최하위 원인 `java.time.zone.ZoneRulesException` |
| 15 | `daily-limit` 키 없음 | 시작 | 실패. 최하위 원인 `BindValidationException`, 메시지에 `dailyLimit` 포함 |
| 16 | `daily-limit` 대신 오타 키 `daily-limt=5000000` | 시작 | 실패. 15번과 같은 원인 (모르는 키는 무시되고 `dailyLimit`은 0) |
| 17 | `zone` 키 없음 | 시작 | 실패. 최하위 원인 `BindValidationException`, 메시지에 `zone` 포함 |
| 18 | `@SpringBootTest` (프로파일 지정 없음) | `TransferProperties.lockTimeout()` | `Duration.ofSeconds(3)` |
| 19 | `@SpringBootTest` + `@ActiveProfiles("test")` | `lockTimeout()`, `dailyLimit()` | `Duration.ofMillis(200)`, `5000000` |
| 20 | `@SpringBootTest` + `@ActiveProfiles("local")` | `lockTimeout()` | `Duration.ofSeconds(5)` |
| 21 | `@SpringBootTest(properties = "lab.transfer.daily-limit=3000000")` + `@ActiveProfiles("test")`, `800-0000-0001`(10,000,000원) → `800-0000-0002` | 3,000,000원 이체 후 1원 이체 | 첫 이체 성공, 두 번째는 M2-7의 한도 초과 예외. `800-0000-0001` 잔액 7,000,000원 |
| 22 | `./gradlew bootJar` 후 | `java -jar build/libs/bank-0.0.1-SNAPSHOT.jar` | 첫 줄 `설정: dailyLimit=5000000, lockTimeout=PT3S, zone=Asia/Seoul` |
| 23 | 22번과 같은 jar | `LAB_TRANSFER_DAILY_LIMIT=3000000 java -jar build/libs/bank-0.0.1-SNAPSHOT.jar --spring.profiles.active=local` | `설정: dailyLimit=3000000, lockTimeout=PT5S, zone=Asia/Seoul` |
| 24 | 22번과 같은 jar | `java -jar build/libs/bank-0.0.1-SNAPSHOT.jar --lab.transfer.lock-timeout=99ms` | 표준 출력에 `APPLICATION FAILED TO START`와 `Property: lab.transfer.lockTimeout`, 종료 코드 1 (`echo $?`) |

시나리오 1~17, 22~24의 결과는 Spring Boot 4.1.2, JDK 21.0.8에서 실행해 확인했다.
시나리오 21 계산: 10,000,000 − 3,000,000 = 7,000,000. 그날 누적 3,000,000원에 1원을 더하면 3,000,001원 > 3,000,000원이라 거절.

## 제약
- `@Value("${lab.transfer.daily-limit}")`로 값을 하나씩 주입하지 않는다 — 검증을 한곳에 모을 수 없고, 키 오타가 시작 시점에 드러나지 않는다.
- `TransferProperties`에 setter나 가변 필드를 두지 않는다 (record) — 실행 중 설정이 바뀌면 이체 스레드마다 다른 한도를 볼 수 있다.
- 비밀번호·토큰 같은 비밀 값은 이 미션의 `application.yml`에 넣지 않는다. 이 미션에는 비밀 값이 없다.
- 시나리오 2~17에서 `@SpringBootTest`를 쓰지 않는다 — 실패하는 컨텍스트를 12번 띄우는 데 걸리는 시간과, 실패 원인 단언의 편의를 `ApplicationContextRunner`와 비교해 생각해볼 질문 1에 적는다.

## 힌트
<details>
<summary>힌트 1: 실패한 컨텍스트 검사하기</summary>

`ApplicationContextRunner.run(context -> ...)`의 `context`는 `AssertableApplicationContext`다. `assertThat(context).hasFailed()`, `assertThat(context.getStartupFailure()).rootCause().isInstanceOf(...)`, `.hasMessageContaining(...)`을 확인한다. 실패한 이유를 처음 볼 때는 `context.getStartupFailure()`의 원인 체인을 `getCause()`로 따라가며 클래스 이름을 출력해 보면 시나리오 5와 6의 체인이 어디서 갈라지는지 보인다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 시나리오 1~21과 기존 M3-1~M3-5 테스트가 모두 통과한다
- [ ] `grep -rnE "5_?000_?000|ofSeconds\(3\)" src/main/java` 결과가 0줄이다
- [ ] `./gradlew build` 후 `build/classes/java/main/META-INF/spring-configuration-metadata.json`에 `lab.transfer.daily-limit`, `lab.transfer.lock-timeout`, `lab.transfer.zone` 3개 이름이 있다 (`spring-boot-configuration-processor`가 생성)
- [ ] 시나리오 22~24의 실제 출력이 TIL에 있고, 명령행 인자·환경 변수·프로파일 파일·기본 `application.yml`의 우선순위를 23번 결과로 설명했다

## 생각해볼 질문
1. 시나리오 2~17을 `@SpringBootTest`로 쓰면 무엇이 달라지는가? `./gradlew test --rerun-tasks`로 `ApplicationContextRunner` 테스트 클래스의 실행 시간을 측정하고, M3-2의 `docs/M3-2-test-timing.md`에 1행을 추가해 비교하라.
2. 시나리오 10처럼 단위 없는 `3`이 3ms가 되는 것을 막는 방법 2가지(검증 범위, `@DurationUnit`)를 비교하라. `@DurationUnit(ChronoUnit.SECONDS)`를 붙이면 `3`은 무엇이 되고, 운영자가 `3000`이라고 쓰면 어떻게 되는가?
3. 한도를 바꾸려면 지금은 재시작이 필요하다. 재시작 없이 바꾸려면 값을 어디에 둬야 하고, 이체 중간에 한도가 바뀌면 어떤 경합이 생기는가? (Phase 6 M6-4의 "한도 테이블"과 연결)
4. (Phase 4 연결) Phase 4에서 `spring-boot-starter-webmvc`를 추가하면 `server.port` 같은 설정이 생긴다. 포트 설정과 이체 한도 설정을 같은 `application.yml`에 두되 `lab.*`과 `server.*` 접두어로 나누는 이유를, `@ConfigurationProperties`의 `prefix`와 연결해 적어라.
