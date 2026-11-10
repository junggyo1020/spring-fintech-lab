# Phase 3 — Spring Core: IoC / DI / AOP (2주)

> 가이드 수준: L2 · 선행: Phase 2 완료 · 이 Phase의 workspace 시작 방법: Spring Initializr로 생성 후 Phase 2 도메인 코드 복사

## 학습 목표
이 Phase를 끝내면 다음을 할 수 있다.
- 리플렉션으로 생성자 주입·싱글톤 캐시·순환 참조 감지를 하는 DI 컨테이너를 직접 만들고, Spring `ApplicationContext`와 기능 차이를 표로 비교한다.
- Phase 2 이체 엔진을 Spring Boot 4.1 프로젝트로 옮겨, `main`의 `new` 조립 코드를 0줄로 만들고 순수 단위 테스트와 `@SpringBootTest` 중 무엇을 쓸지 테스트마다 근거를 댄다.
- 가변 필드를 가진 싱글톤 빈의 동시성 버그를 Phase 2의 동시성 테스트 틀로 재현하고, 무상태로 고친 뒤 `@RepeatedTest(50)` 50회 통과로 증명한다.
- 같은 실행 시간 측정 기능을 데코레이터·JDK 동적 프록시·CGLIB 프록시 3가지로 구현하고, final 메서드와 self-invocation이 가로채지지 않는 것을 테스트로 보여준다.
- `@Aspect` 기반 감사 로그와 `@ConfigurationProperties` 검증을 만들고, 설정값이 잘못되면 애플리케이션이 시작되지 않음을 `ApplicationContextRunner` 테스트로 보여준다.

## 이 Phase의 결과물
Phase 2의 `TransferEngine`이 Spring 빈으로 동작하는 웹 없는 Spring Boot 애플리케이션. 이체 호출마다 감사 로그가 남고, 이체 한도·락 타임아웃·시간대는 `application.yml`에서 읽는다. Phase 4는 이 workspace를 복사해 Spring MVC를 붙인다.

```
phase-3-spring-core/workspace/
├── build.gradle.kts, settings.gradle.kts, gradlew      # Spring Initializr 생성물 + 이 README의 build.gradle.kts
├── docs/                                               # 미션별 비교표·측정표 (각 미션의 완료 기준에 파일명 명시)
└── src/
    ├── main/java/lab/bank/
    │   ├── BankApplication.java       # @SpringBootApplication (M3-2)
    │   ├── common/ money/ account/ ledger/ interest/ application/ transfer/   # Phase 2에서 복사 (M3-2)
    │   ├── minidi/                    # MyComponent, MiniContainer, 예외 (M3-1)
    │   ├── config/                    # BankConfig(Clock 빈), TransferProperties (M3-2, M3-6)
    │   ├── lifecycle/                 # LifecycleProbe, RequestTrace, 상태 있는/없는 퍼사드 (M3-3)
    │   ├── proxy/                     # 실행 시간 측정 프록시 3종 (M3-4)
    │   └── audit/                     # Audited, AuditAspect, CallerContext, AuditLogRepository (M3-5)
    ├── main/resources/
    │   ├── application.yml            # M3-6
    │   ├── application-local.yml
    │   └── application-test.yml
    └── test/java/lab/bank/            # 미션별 테스트, test/java/lab/bank/minidi/fixture/ (M3-1 전용 가짜 클래스)
```

---

## 핵심 개념 정리 (미션 전에 읽기)

### 1. IoC와 DI
**IoC(제어의 역전)**: 객체가 자기가 쓸 객체를 직접 만들지 않고, 바깥(컨테이너)이 만들어서 넣어준다. 객체 생성·연결·소멸의 순서를 개발자 코드가 아니라 컨테이너가 결정한다.
**DI(의존성 주입)**: IoC를 구현하는 방법. 의존 객체를 생성자·setter·필드로 넣어준다. 이 Phase는 **생성자 주입만** 쓴다.

Phase 2 `main`(또는 테스트 준비 코드)의 조립 코드는 이런 모양이다.
```java
Clock clock = Clock.system(ZoneId.of("Asia/Seoul"));
Ledger ledger = new Ledger();
BankService bankService = new BankService(ledger);
TransferEngine engine = new LockingTransferEngine(bankService, ledger, clock);   // 구현체 이름은 각자 다르다
```
이 코드의 문제 3가지:

| 문제 | 금융 시스템에서 생기는 일 |
|---|---|
| 생성 순서를 사람이 관리한다 | 협력 객체가 10개를 넘으면 `Ledger`를 두 번 `new`해서 원장이 2개로 갈라지는 실수가 생긴다 (이체는 성공했는데 거래내역 조회에 안 보임) |
| 구현체 교체 시 조립 코드를 고친다 | 테스트에서 고정 시각 `Clock`을 쓰려면 조립 코드 전체를 복사해야 한다 |
| 공통 기능(감사 로그, 실행 시간)을 넣을 자리가 없다 | 이체 메서드마다 로그 코드를 직접 넣어야 하고, 1곳이라도 빠지면 감사 누락 |

생성자 주입을 쓰는 이유: 필드를 `final`로 둘 수 있어 생성 후 의존성이 바뀌지 않고, Spring 없이 `new`로 단위 테스트를 만들 수 있으며, 생성자 순환 참조는 시작 시점에 예외로 드러난다 (필드 주입은 런타임까지 숨는다). M3-1에서 이 컨테이너를 직접 만든다.

### 2. 빈 라이프사이클과 스코프
Spring 컨테이너가 싱글톤 빈 하나를 다루는 순서 (Spring Boot 4.1.2 / Spring Framework 7에서 이 순서를 실행해 확인):

```
생성자 호출 → 의존성 주입(setter/필드) → @PostConstruct → InitializingBean.afterPropertiesSet()
  → (모든 싱글톤 생성 완료) ContextRefreshedEvent → ... 사용 ...
  → context.close() → @PreDestroy → DisposableBean.destroy()
```
생성자 주입이면 "생성자 호출"과 "의존성 주입"이 한 단계다. AOP 프록시는 `@PostConstruct` 이후(`BeanPostProcessor.postProcessAfterInitialization`)에 만들어진다. 그래서 `@PostConstruct` 안에서 자기 메서드를 호출하면 프록시를 거치지 않는다.

| 스코프 | 인스턴스 수 | `@PreDestroy` 호출 | 주의 |
|---|---|---|---|
| `singleton` (기본값) | 컨테이너당 1개, 모든 스레드가 공유 | 컨테이너가 호출 | 요청마다 바뀌는 값을 필드에 두면 스레드 간에 섞인다 (M3-3) |
| `prototype` | `getBean`·주입할 때마다 새로 생성 | **호출하지 않는다** (생성 후 관리 안 함) | 싱글톤에 생성자로 주입하면 싱글톤 생성 시 1번만 만들어져 사실상 싱글톤이 된다 → `ObjectProvider<T>.getObject()`로 호출마다 꺼낸다 |
| `request`, `session` | HTTP 요청·세션당 1개 | 컨테이너가 호출 | 웹 환경 전용. Phase 4에서 사용 |

싱글톤 빈은 Phase 2의 "공유 가변 상태"다. 필드가 `final`이고 그 필드가 가리키는 객체도 스레드 안전하면 공유해도 안전하다. 요청마다 다른 값(이체 명령, 계산 중간값)은 **지역 변수나 메서드 인자**로만 다룬다.

### 3. 프록시: JDK 동적 프록시 vs CGLIB
프록시는 진짜 객체(target)와 같은 타입으로 보이면서, 호출을 가로채 앞뒤에 기능을 붙이고 target에 위임하는 객체다.

| 항목 | 데코레이터 (직접 작성) | JDK 동적 프록시 | CGLIB (Spring `ProxyFactory`) |
|---|---|---|---|
| 만드는 방법 | 같은 인터페이스를 구현한 클래스를 손으로 작성 | `java.lang.reflect.Proxy.newProxyInstance` + `InvocationHandler` | 런타임에 target 클래스의 **하위 클래스**를 생성 |
| 인터페이스 필요 | 필요 | **필요** (인터페이스 타입으로만 캐스팅 가능) | 불필요 |
| 생성되는 클래스 이름 예 | `TimedTransferEngine` | `$Proxy` + 번호 (public 인터페이스면 `jdk.proxy2.$Proxy12`처럼 `jdk.proxy` 패키지, package-private 인터페이스면 그 인터페이스의 패키지) | `FeeCalculator$$SpringCGLIB$$0` |
| 가로채지 못하는 것 | 손으로 안 쓴 메서드 | 인터페이스에 없는 메서드 | `final` 메서드, `final` 클래스(프록시 생성 자체가 실패), `private` 메서드 |
| 메서드 10개 추가 시 | 프록시 코드도 10개 추가 | 수정 없음 | 수정 없음 |

CGLIB는 원래 별도 라이브러리(`cglib:cglib`)지만 JDK 17 이후 모듈 접근 제한 때문에 원본 라이브러리는 `--add-opens` 없이 동작하지 않는 경우가 있다. Spring은 CGLIB를 `org.springframework.cglib` 패키지로 재패키징해 `spring-core`에 넣었다. 이 Phase는 원본 CGLIB를 쓰지 않고 Spring의 `ProxyFactory`로 CGLIB 프록시를 만든다.
Spring은 CGLIB 프록시 인스턴스를 Objenesis로 생성해 **target의 생성자를 호출하지 않는다**. 그래서 프록시 객체 자신의 필드는 모두 `null`/0이다. `final` 메서드는 오버라이드되지 않아 프록시 객체 자신의 메서드가 실행되고, 그 메서드가 필드를 읽으면 `null`을 얻는다. Spring은 이때 `Public final method [...] cannot get proxied via CGLIB` 경고 로그를 남긴다 (Spring Boot 4.1.2에서 확인).

**self-invocation**: target 안에서 `this.otherMethod()`를 호출하면 `this`는 프록시가 아니라 target이므로 프록시 기능이 적용되지 않는다. 3가지 방식 모두 같다.

### 4. AOP 용어
| 용어 | 정의 | M3-5에서 대응하는 것 |
|---|---|---|
| Aspect | 여러 클래스에 흩어진 공통 관심사를 모은 모듈 | `AuditAspect` (`@Aspect` + `@Component`) |
| JoinPoint | Advice를 끼울 수 있는 실행 지점. Spring AOP에서는 **메서드 실행만** 해당 | `TransferEngine` 구현체의 `transfer(...)` 실행 |
| Pointcut | 어떤 JoinPoint를 고를지 정하는 식 | `@annotation(lab.bank.audit.Audited)` |
| Advice | JoinPoint에서 실행할 코드와 시점 (`@Before`, `@AfterReturning`, `@AfterThrowing`, `@After`, `@Around`) | `@Around` 메서드 (호출 전 시각 기록 → `proceed()` → 결과/예외 기록) |
| Target | Advice가 적용되는 원래 객체 | `TransferEngine` 구현체 인스턴스 |
| Weaving | Aspect를 target에 연결하는 과정 | Spring은 런타임에 프록시를 만들어 연결 (컴파일 시점 위빙이 아님) |

Spring Boot는 기본으로 CGLIB 프록시를 만든다 (`spring.aop.proxy-target-class` 기본값 `true`). 인터페이스가 있는 빈도 하위 클래스 프록시가 된다. 그래서 AOP를 적용할 빈 클래스에 `final`을 붙이면 시작 시점에 `BeanCreationException`(원인 `AopConfigException: Could not generate CGLIB subclass of class ...`)으로 실패한다 (Spring Boot 4.1.2에서 확인).
Spring Boot 4.0부터 AOP 스타터 이름이 `spring-boot-starter-aop`에서 `spring-boot-starter-aspectj`로 바뀌었다.

### 5. `@Configuration`의 CGLIB 프록시
```java
@Configuration                       // proxyBeanMethods = true 가 기본값
public class BankConfig {
    @Bean Clock clock() { ... }
    @Bean A a() { return new A(clock()); }
    @Bean B b() { return new B(clock()); }
}
```
`a()`와 `b()`가 `clock()`을 각각 호출하는데도 `A`와 `B`가 받은 `Clock`은 같은 인스턴스다. Spring이 `BankConfig`의 CGLIB 하위 클래스(`BankConfig$$SpringCGLIB$$0`)를 빈으로 등록하고, 그 하위 클래스의 `clock()`이 "이미 만든 `clock` 빈이 있으면 그것을 반환"하도록 오버라이드하기 때문이다 (Spring Boot 4.1.2에서 `a.clock() == b.clock()`이 `true`, 설정 클래스의 `getClass().getName()`이 `...BankConfig$$SpringCGLIB$$0`인 것을 확인).
`@Configuration(proxyBeanMethods = false)`이면 프록시를 만들지 않아 `clock()` 호출마다 새 `Clock`이 생긴다. 대신 시작이 빠르고 `final` 클래스도 쓸 수 있다. Spring Boot의 자동 설정 클래스는 `false`를 쓰고, 빈끼리는 `@Bean` 메서드 **파라미터**로 주입받는다.
같은 원리로 `@Bean` 메서드를 `final`이나 `private`로 만들면 오버라이드가 안 돼 위 보장이 깨진다.

### 6. 테스트 종류
| 테스트 | 무엇을 띄우나 | 실행 시간 | 이 Phase에서 쓰는 곳 |
|---|---|---|---|
| 순수 단위 테스트 (`new`로 생성) | 없음 | M3-2에서 측정해 `docs/M3-2-test-timing.md`에 기록 | 도메인 규칙, 한도 계산, 프록시 동작 |
| `ApplicationContextRunner` | 지정한 설정 클래스만으로 만든 컨텍스트 | M3-6에서 측정 | 설정 바인딩·검증 실패 (M3-6) |
| `@SpringBootTest` | 애플리케이션 전체 컨텍스트 | M3-2에서 측정 (같은 설정의 2번째 테스트 클래스부터는 캐시된 컨텍스트를 재사용) | 빈 연결, AOP 적용 여부, 프로파일 |
| 슬라이스 테스트 (`@WebMvcTest`, `@DataJpaTest` 등) | 한 계층에 필요한 빈만 | Phase 4·5에서 측정 | Phase 4(M4-8), Phase 5 |

- `@SpringBootTest`는 같은 설정(같은 `@MockitoBean` 조합, 같은 프로파일, 같은 `properties`)을 쓰는 테스트 클래스끼리 컨텍스트를 **캐시해서 공유**한다. 싱글톤 빈의 상태(계좌, 감사 로그)도 테스트 클래스 사이에 남는다. 테스트마다 다른 계좌번호를 쓰거나 `@BeforeEach`에서 저장소를 비운다.
- Spring Boot 4.0에서 `@MockBean`·`@SpyBean`은 삭제됐다. 대신 Spring Framework의 `@MockitoBean`·`@MockitoSpyBean`(`org.springframework.test.context.bean.override.mockito` 패키지)을 쓴다. 블로그의 `@MockBean` 예제를 그대로 옮기면 컴파일되지 않는다.
- Spring Boot 4.1.2가 관리하는 JUnit은 JUnit 6(Jupiter 6.0.3)이다. 테스트 작성법(`org.junit.jupiter.api` 패키지)은 Phase 2와 같다.
- Spring Boot 4부터 테스트 스타터도 기술별로 나뉜다 (`spring-boot-starter-<기술>-test`). 이 Phase는 웹·DB가 없으므로 `spring-boot-starter-test` 하나로 충분하다.

---

## 워크스페이스 만들기

### 1단계: Spring Initializr로 생성 (M3-1 시작 전)
2026-11-10 기준 start.spring.io의 기본 버전은 Spring Boot 4.1.2다. 더 높은 4.1.x 패치가 나왔으면 `bootVersion`만 바꾼다. 4.2.x와 SNAPSHOT·RC는 쓰지 않는다.

```bash
cd phase-3-spring-core/workspace
curl -s -o bank.zip "https://start.spring.io/starter.zip?type=gradle-project-kotlin&language=java&bootVersion=4.1.2&javaVersion=21&groupId=lab&artifactId=bank&name=bank&packageName=lab.bank&dependencies=validation,configuration-processor"
unzip bank.zip && rm bank.zip
rm src/main/resources/application.properties src/test/java/lab/bank/BankApplicationTests.java
mkdir -p docs
```
zip 안에는 최상위 폴더가 없어 `workspace/` 바로 아래에 `build.gradle.kts`, `gradlew`, `src/`가 생긴다. Gradle Wrapper는 Initializr가 넣어준 버전(2026-11-10 기준 9.8.2)을 그대로 쓴다.

`build.gradle.kts`를 아래 내용으로 바꾼다 (Initializr 생성물에 AOP 스타터, 코어 스타터, 테스트 스타터를 더한 것):
```kotlin
plugins {
    java
    id("org.springframework.boot") version "4.1.2"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "lab"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")              // 코어: 컨테이너, 로깅, YAML
    implementation("org.springframework.boot:spring-boot-starter-aspectj")      // M3-5 (@Aspect). Boot 3의 starter-aop
    implementation("org.springframework.boot:spring-boot-starter-validation")   // M3-6 (jakarta.validation + Hibernate Validator)
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")   // M3-6 설정 메타데이터
    testImplementation("org.springframework.boot:spring-boot-starter-test")     // JUnit 6, AssertJ, Mockito, Spring Test
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test> {
    useJUnitPlatform()
    testLogging {
        events("passed", "failed", "skipped")
    }
}
```
`settings.gradle.kts`는 생성된 그대로 둔다 (`rootProject.name = "bank"`).

확인: `./gradlew build`가 `BUILD SUCCESSFUL`로 끝난다 (JDK 21.0.8, Gradle 9.8.2, Spring Boot 4.1.2에서 확인).
테스트 실행 시 `Mockito is currently self-attaching to enable the inline-mock-maker` 경고가 stderr에 나온다. 테스트 실패가 아니며 이 Phase에서는 그대로 둔다.

### 2단계: Phase 2 도메인 코드 복사 (M3-2 시작 시)
```bash
cd phase-3-spring-core/workspace
P2=../../phase-2-java-concurrency/workspace/src
for pkg in common money account ledger interest application transfer; do
  mkdir -p src/main/java/lab/bank/$pkg src/test/java/lab/bank/$pkg
  rsync -a $P2/main/java/lab/bank/$pkg/ src/main/java/lab/bank/$pkg/
  [ -d $P2/test/java/lab/bank/$pkg ] && rsync -a $P2/test/java/lab/bank/$pkg/ src/test/java/lab/bank/$pkg/
done
```
`console`, `concurrency`, `experiment` 패키지는 복사하지 않는다. `common`(`BankException`, `ErrorCode`)과 `interest`(`BankService` 생성자가 받는 `InterestPolicy`, `TaxCalculator`)를 빼면 컴파일되지 않는다. `@Tag("deadlock-demo")`가 붙은 M2-3 테스트가 복사됐으면 삭제한다 (Phase 3 `build.gradle.kts`에는 태그 제외 설정이 없다). 복사 직후 `./gradlew test`가 통과해야 M3-2를 시작한다.

## 주차별 계획
| 주 | 미션 | 개념 학습 범위 |
|---|---|---|
| 1주 | M3-1, M3-2, M3-3 | 이 README 1·2·5·6절 · Spring Framework Reference "The IoC Container"의 "Introduction to the Spring IoC Container and Beans", "Dependencies", "Bean Scopes", "Customizing the Nature of a Bean" 절 · 『토비의 스프링 3.1』 Vol.1 1장 |
| 2주 | M3-4, M3-5, M3-6 | 이 README 3·4절 · Spring Framework Reference "Aspect Oriented Programming with Spring"의 "AOP Concepts", "@AspectJ support", "Proxying Mechanisms" 절 · Spring Boot Reference "Externalized Configuration"의 "Type-safe Configuration Properties" 절 · 『토비의 스프링 3.1』 Vol.1 6장 |

1주차 예상 시간 11~14h, 2주차 11~15h.

## 미션
| 미션 | 주제 | 예상 시간 |
|---|---|---|
| [M3-1](missions/M3-1-mini-di-container.md) | 나만의 DI 컨테이너 | 5~6h |
| [M3-2](missions/M3-2-spring-boot-migration.md) | Spring Boot로 이식 | 3~4h |
| [M3-3](missions/M3-3-bean-scope-lifecycle.md) | 빈 스코프·라이프사이클과 싱글톤 상태 문제 | 3~4h |
| [M3-4](missions/M3-4-proxy-by-hand.md) | 프록시 직접 만들기 | 4~5h |
| [M3-5](missions/M3-5-audit-aop.md) | 감사 로그 AOP | 4~6h |
| [M3-6](missions/M3-6-externalized-config.md) | 설정 외부화와 프로파일 | 3~4h |

합계 22~29h (2주 × 주 12h 기준 24h).

## 읽을거리
- Spring Framework Reference (7.0) — Core Technologies › "The IoC Container": "Introduction to the Spring IoC Container and Beans", "Dependencies"(Dependency Injection, Circular dependencies 단락), "Bean Scopes"(Singleton Beans with Prototype-bean Dependencies 단락), "Customizing the Nature of a Bean"(Lifecycle Callbacks, Combining Lifecycle Mechanisms 단락), "Java-based Container Configuration"(Full @Configuration vs "lite" @Bean mode 단락)
- Spring Framework Reference (7.0) — Core Technologies › "Aspect Oriented Programming with Spring": "AOP Concepts", "Spring AOP Capabilities and Goals", "AOP Proxies", "@AspectJ support"(Declaring a Pointcut, Around Advice 단락), "Proxying Mechanisms"(Understanding AOP Proxies 단락 — self-invocation 설명)
- Spring Framework Reference (7.0) — Testing › "Bean Overriding in Tests"(`@MockitoBean`)
- Spring Boot Reference (4.1) — "Externalized Configuration"(Profile-specific Files, Type-safe Configuration Properties, @ConfigurationProperties Validation 단락), "Profiles", "Testing Spring Boot Applications"(Detecting Test Configuration, Context Caching 단락), "Creating Your Own Auto-configuration"의 "Testing your Auto-configuration" 단락 (`ApplicationContextRunner`)
- Spring Boot 4.0 Migration Guide (GitHub wiki `spring-projects/spring-boot`) — "Starters" 절, `@MockBean` 삭제 단락
- 『토비의 스프링 3.1』 Vol.1 (이일민) — 1장 "오브젝트와 의존관계"(1.4 제어의 역전, 1.6 싱글톤 레지스트리와 오브젝트 스코프, 1.7 의존관계 주입), 6장 "AOP" 6.3 다이내믹 프록시와 팩토리 빈 ~ 6.5 스프링 AOP (6.1·6.2는 선택)

## 완료 기준
- [ ] `./gradlew test`가 통과하고, M3-1~M3-6 각 미션의 테스트 시나리오 번호가 테스트 메서드의 `@DisplayName`에 들어 있다 (예: `"M3-1 #7 순환 참조 A -> B -> A"`)
- [ ] `src/main/java/lab/bank/BankApplication.java`에 `new` 키워드가 0개다 (`grep -c "new " src/main/java/lab/bank/BankApplication.java` 결과 `0`)
- [ ] M3-5의 self-invocation 재현 테스트가 "감사 로그 0건"을 단언하고, 고친 2가지 버전 테스트가 "감사 로그 3건"을 단언하며 모두 통과한다
- [ ] `lab.transfer.lock-timeout=99ms`로 실행하면 시작이 실패하는 테스트가 통과한다
- [ ] `docs/` 아래에 M3-1~M3-5 완료 기준에 적힌 파일 6개(`M3-1-mini-vs-spring.md`, `M3-2-bean-inventory.md`, `M3-2-test-timing.md`, `M3-3-singleton-state.md`, `M3-4-proxy-comparison.md`, `M3-5-self-invocation-fixes.md`)가 있다
- [ ] [레벨 진단](../docs/self-check.md) Phase 3 항목을 말로 설명할 수 있다
