# M3-1 나만의 DI 컨테이너

> 가이드 수준: L2 · 예상 시간: 5~6h · 선행: M2-7

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 패키지를 스캔해 `@MyComponent` 클래스를 찾고, 단일 생성자의 파라미터 타입으로 의존 객체를 찾아 주입하는 컨테이너를 JDK 리플렉션만으로 구현한다.
- 순환 참조를 생성 시점에 감지하고, 예외 메시지에 순환 경로(`A -> B -> A`)를 정확히 출력하는 테스트 6개를 통과시킨다.
- 인터페이스 타입 주입에서 구현체 0개·1개·2개 이상일 때의 동작을 테스트로 보여준다.
- 직접 만든 컨테이너와 Spring `ApplicationContext`의 기능 차이 8가지를 표로 정리한다.

## 배경
M2-7에서 `TransferEngine`을 쓰려면 `Clock`, `Ledger`, `BankService`를 순서대로 `new`해서 넘겨야 했다. 협력 객체가 늘면 같은 `Ledger`를 두 번 만들어 원장이 갈라지는 실수가 생기고, 이체는 성공했는데 거래내역에는 보이지 않는 사고로 이어진다. Spring은 이 조립을 컨테이너에 맡기는데, 학습자 대부분은 "애노테이션을 붙이면 주입된다"에서 멈춘다. 그러면 Spring 시작 시 나오는 `UnsatisfiedDependencyException`, `NoUniqueBeanDefinitionException`, `BeanCurrentlyInCreationException`의 원인을 스택 트레이스에서 찾지 못한다. 이 미션은 그 3가지 실패를 직접 만드는 컨테이너에서 먼저 재현한다. README 1절을 먼저 읽는다.

## 요구사항
패키지: `lab.bank.minidi`. Spring 클래스(`org.springframework.*`)를 import하지 않는다. 테스트용 가짜 클래스는 `src/test/java/lab/bank/minidi/fixture/` 아래 시나리오별 하위 패키지에 둔다.

### 제공하는 핵심 시그니처
```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface MyComponent {}

public final class MiniContainer {
    public MiniContainer(String basePackage)        // 스캔 + 모든 빈 즉시 생성
    public <T> T getBean(Class<T> type)
    public int beanCount()                           // 생성된 빈 개수
}
```
예외 클래스 5개는 모두 `lab.bank.minidi`에 둔다: `MiniContainerException`(부모, `RuntimeException` 상속), `NoSuchBeanException`, `NoUniqueBeanException`, `CircularDependencyException`, `BeanCreationException` (4개 모두 `MiniContainerException` 상속). 필드와 생성자는 직접 설계한다.

### 1. 스캔 규칙
1. `basePackage`가 `null`이거나 공백 문자열(`""`, `"  "`)이면 `IllegalArgumentException`.
2. `basePackage`와 그 하위 패키지 전체를 스캔한다. `lab.bank.minidi.fixture.cycle`을 주면 `lab.bank.minidi.fixture.cycle.three`도 포함한다.
3. 클래스 파일은 클래스패스의 디렉터리(URL 프로토콜 `file`)에서만 찾는다. `jar` 등 다른 프로토콜을 만나면 `MiniContainerException`을 던지고 메시지에 프로토콜 이름을 넣는다.
4. 파일 이름에 `$`가 들어간 클래스(내부 클래스, 익명 클래스)는 건너뛴다.
5. `@MyComponent`가 붙은 클래스만 등록한다. 애노테이션이 없는 클래스는 같은 패키지에 있어도 등록하지 않는다.
6. `@MyComponent`가 인터페이스나 추상 클래스에 붙어 있으면 `BeanCreationException`. 메시지에 클래스 simple name을 넣는다.
7. 존재하지 않는 패키지이거나 `@MyComponent` 클래스가 0개인 패키지면 예외 없이 `beanCount() == 0`인 컨테이너가 된다.

### 2. 생성 규칙
1. 생성 순서: 등록된 클래스를 **전체 클래스 이름(FQCN) 알파벳 오름차순**으로 하나씩 생성한다. 이미 다른 빈의 의존성으로 생성된 클래스는 건너뛴다. 이 순서가 있어야 순환 경로 메시지가 실행마다 같다.
2. 생성자: `getDeclaredConstructors()` 결과가 정확히 1개여야 한다. 0개는 생길 수 없고, 2개 이상이면 `BeanCreationException`. 메시지에 클래스 simple name과 생성자 개수를 넣는다 (예: `"TwoCtors: 생성자가 2개입니다. 1개만 허용합니다"`). 생성자의 접근 제한자는 무엇이든 허용한다(`setAccessible(true)`).
3. 파라미터 타입마다 아래 "타입 해석 규칙"으로 빈을 찾아, 없으면 먼저 생성한 뒤 넘긴다.
4. 생성자가 예외를 던지면 `BeanCreationException`으로 감싸 던진다. `getCause()`는 **생성자가 던진 원래 예외**여야 한다 (리플렉션이 감싼 `InvocationTargetException`이 아니다). 메시지에 클래스 simple name을 넣는다.
5. 싱글톤: 클래스 하나당 인스턴스는 정확히 1개. 같은 의존성을 요구하는 빈이 여러 개여도 생성자는 1번만 호출된다.

### 3. 타입 해석 규칙 (`getBean`과 생성자 파라미터에 같은 규칙)
1. 후보 = 등록된 클래스 중 `요청타입.isAssignableFrom(후보클래스)`인 것 전부. 요청 타입이 구체 클래스여도 같은 규칙이다 (등록된 하위 클래스도 후보).
2. 후보 1개 → 그 빈.
3. 후보 0개 → `NoSuchBeanException`. 메시지에 요청 타입 simple name을 넣는다. 생성자 파라미터를 해석하다 실패했으면 그 생성자의 클래스 simple name도 넣는다 (예: `"Notifier 타입의 빈이 없습니다 (요청: PaymentService)"`).
4. 후보 2개 이상 → `NoUniqueBeanException`. 메시지에 후보 클래스 simple name을 **알파벳 오름차순, 쉼표+공백 구분**으로 넣는다 (예: `"Notifier 타입 후보 2개: EmailNotifier, SmsNotifier"`).
5. `getBean(null)` → `IllegalArgumentException`.

### 4. 순환 참조 감지
1. 지금 생성 중인 클래스들을 생성 시작 순서대로 기억한다. 생성 중인 클래스를 다시 요청하면 `CircularDependencyException`.
2. 메시지 형식: `"순환 참조: " + 경로`. 경로는 **순환에 포함된 클래스만** simple name으로, 처음 다시 요청된 클래스에서 시작해 그 클래스로 끝나며 ` -> `(공백-화살표-공백)로 잇는다.
3. 인터페이스를 거친 순환은 인터페이스가 아니라 실제 생성 중인 **구현 클래스** 이름으로 적는다.
4. 순환 감지 후 컨테이너 생성 자체가 실패한다 (생성자가 예외를 던진다).

## 테스트 시나리오
"fixture 패키지" 열은 `lab.bank.minidi.fixture.` 뒤에 붙는 이름이다. 화살표 `X(Y)`는 "X의 유일한 생성자가 Y 타입 파라미터 1개를 받는다"는 뜻이다. 모든 fixture 클래스는 `public` top-level 클래스이고, 이 표에 적지 않은 클래스는 만들지 않는다.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | `simple`: `@MyComponent Repo()`, `@MyComponent Service(Repo)`, 애노테이션 없는 `PlainHelper()` | `new MiniContainer("lab.bank.minidi.fixture.simple")` | `beanCount() == 2`, `getBean(Service.class)`가 가진 `Repo`와 `getBean(Repo.class)`가 같은 인스턴스(`isSameAs`) |
| 2 | 1번과 같음 | `getBean(PlainHelper.class)` | `NoSuchBeanException`, 메시지에 `PlainHelper` 포함 |
| 3 | 1번과 같음 | `getBean(Service.class)`를 2번 호출 | 두 결과가 같은 인스턴스 |
| 4 | `shared`: `Counted()` (생성자에서 static `AtomicInteger CREATED`를 1 증가), `UserA(Counted)`, `UserB(Counted)` 모두 `@MyComponent`. 테스트 시작 시 `CREATED.set(0)` | 컨테이너 생성 | `CREATED.get() == 1`, `beanCount() == 3` |
| 5 | `iface.single`: 인터페이스 `Notifier`, `@MyComponent SmsNotifier implements Notifier`, `@MyComponent PaymentService(Notifier)` | 컨테이너 생성 후 `getBean(Notifier.class)` | `SmsNotifier` 인스턴스이고 `PaymentService`에 주입된 것과 같은 인스턴스 |
| 6 | `iface.none`: 인터페이스 `Notifier`(구현체 없음), `@MyComponent PaymentService(Notifier)` | 컨테이너 생성 | `NoSuchBeanException`, 메시지에 `Notifier`와 `PaymentService` 둘 다 포함 |
| 7 | `iface.multiple`: `Notifier`, `@MyComponent SmsNotifier`, `@MyComponent EmailNotifier` (둘 다 `Notifier` 구현), `@MyComponent PaymentService(Notifier)` | 컨테이너 생성 | `NoUniqueBeanException`, 메시지에 `EmailNotifier, SmsNotifier` (이 순서 그대로) 포함 |
| 8 | `cycle.two`: `@MyComponent A(B)`, `@MyComponent B(A)` | 컨테이너 생성 | `CircularDependencyException`, 메시지가 정확히 `순환 참조: A -> B -> A` |
| 9 | `cycle.three`: `@MyComponent Alpha(Beta)`, `@MyComponent Beta(Gamma)`, `@MyComponent Gamma(Alpha)` | 컨테이너 생성 | 메시지가 정확히 `순환 참조: Alpha -> Beta -> Gamma -> Alpha` |
| 10 | `cycle.self`: `@MyComponent Selfish(Selfish)` | 컨테이너 생성 | 메시지가 정확히 `순환 참조: Selfish -> Selfish` |
| 11 | `cycle.tail`: `@MyComponent Entry(Loop1)`, `@MyComponent Loop1(Loop2)`, `@MyComponent Loop2(Loop1)` | 컨테이너 생성 | 메시지가 정확히 `순환 참조: Loop1 -> Loop2 -> Loop1` (`Entry`는 순환 밖이라 포함하지 않음) |
| 12 | `cycle.iface`: 인터페이스 `Notifier`, `@MyComponent OrderService(Notifier)`, `@MyComponent PushNotifier(OrderService) implements Notifier` | 컨테이너 생성 | 메시지가 정확히 `순환 참조: OrderService -> PushNotifier -> OrderService` |
| 13 | `ctor.two`: `@MyComponent TwoCtors`에 `TwoCtors()`와 `TwoCtors(String)` 2개 | 컨테이너 생성 | `BeanCreationException`, 메시지에 `TwoCtors`와 `2` 포함 |
| 14 | `ctor.fail`: `@MyComponent Exploding()` — 생성자가 `new IllegalStateException("boom")`을 던진다 | 컨테이너 생성 | `BeanCreationException`, `getCause()`가 `IllegalStateException`이고 메시지 `"boom"`, 예외 메시지에 `Exploding` 포함 |
| 15 | `ctor.unknown`: `@MyComponent NeedsString(String)` | 컨테이너 생성 | `NoSuchBeanException`, 메시지에 `String`과 `NeedsString` 포함 |
| 16 | `abstracttype`: `@MyComponent`가 붙은 추상 클래스 `BaseRepo` | 컨테이너 생성 | `BeanCreationException`, 메시지에 `BaseRepo` 포함 |
| 17 | 없음 | `new MiniContainer("lab.bank.minidi.fixture.doesnotexist")` | 예외 없음, `beanCount() == 0`, 이후 `getBean(Object.class)`는 `NoSuchBeanException` |
| 18 | 없음 | `new MiniContainer(null)`, `new MiniContainer("")`, `new MiniContainer("  ")` | 3개 모두 `IllegalArgumentException` (`@ParameterizedTest` + `@NullSource` + `@ValueSource`) |
| 19 | 1번과 같음 | `getBean(null)` | `IllegalArgumentException` |

시나리오 8~12의 "정확히"는 `hasMessage(...)`로 문자열 전체를 비교한다는 뜻이다. `contains`로 쓰지 않는다.

## 제약
- `org.springframework.*`, Reflections·ClassGraph 같은 스캔 라이브러리 금지 — 클래스패스 스캔과 리플렉션 호출을 직접 작성하는 것이 이 미션의 목표다.
- 필드 주입·setter 주입은 구현하지 않는다 — README 1절의 생성자 주입 이유를 따른다.
- 테스트 하나가 다른 시나리오의 fixture를 읽지 않도록 시나리오마다 하위 패키지를 나눈다. 같은 패키지를 스캔하면 7번의 `EmailNotifier`가 5번 테스트를 깨뜨린다.
- 순환 감지에 "재귀 깊이 N 초과" 같은 휴리스틱을 쓰지 않는다 — 깊이 제한은 경로를 알려주지 못한다.

## 힌트
<details>
<summary>힌트 1: 클래스패스에서 패키지 디렉터리 찾기</summary>

`Thread.currentThread().getContextClassLoader().getResources("lab/bank/minidi/fixture/simple")`는 `Enumeration<URL>`을 반환한다. 단수형 `getResource`를 쓰면 안 되는 이유: Gradle 테스트 실행 시 `build/classes/java/main`과 `build/classes/java/test`가 별개 디렉터리라 같은 패키지 경로가 2곳 이상 나올 수 있다. `URL.toURI()` → `Path.of(uri)` → `Files.walk(...)`로 `.class` 파일을 찾고, 경로를 패키지 이름으로 바꾼 뒤 `Class.forName(name, false, loader)`로 로드한다.
</details>

<details>
<summary>힌트 2: 순환 경로를 뽑는 자료구조</summary>

"생성 중" 집합에 순서가 필요하다. `LinkedHashSet<Class<?>>`나 `ArrayDeque<Class<?>>`를 생각해 보라. 다시 요청된 클래스가 집합의 몇 번째에 있는지 찾으면, 그 위치부터 끝까지가 순환이다. 생성이 끝나거나 예외가 나면 집합에서 빼야 하는 이유는 시나리오 11에서 드러난다.
</details>

## 완료 기준
- [ ] `./gradlew test --tests 'lab.bank.minidi.*'`에서 시나리오 1~19의 테스트가 모두 통과한다 (시나리오 18은 3케이스)
- [ ] `grep -rn "org.springframework" src/main/java/lab/bank/minidi` 결과가 0줄이다
- [ ] `docs/M3-1-mini-vs-spring.md`에 열 `기능 | MiniContainer | Spring ApplicationContext | Spring에서 확인한 방법(공식 문서 절 이름 또는 직접 실행한 코드)`인 표가 있고, 행은 최소 8개: 생성자 주입, 필드/setter 주입, 후보 2개 이상일 때(`@Primary`, `@Qualifier`), 순환 참조(생성자 vs setter), 스코프, 지연 생성(`@Lazy`), 라이프사이클 콜백, 프록시(AOP)
- [ ] 시나리오 8을 Spring으로 똑같이 만들었을 때(테스트 클래스 안에 `@Component`가 붙은 static 중첩 클래스 `A(B)`, `B(A)`를 만들고 `new AnnotationConfigApplicationContext(A.class, B.class)`. top-level 클래스로 만들면 `lab.bank` 아래 테스트 소스도 `@SpringBootTest`의 컴포넌트 스캔에 걸려 M3-2 이후 모든 `@SpringBootTest`가 순환 참조로 실패한다) 최하위 원인 예외가 `BeanCurrentlyInCreationException`인 것을 테스트 1개로 확인하고, 그 메시지 첫 줄을 위 표에 붙인다

## 생각해볼 질문
1. Spring은 setter 주입끼리의 순환 참조를 3단계 캐시(`singletonObjects`, `earlySingletonObjects`, `singletonFactories`)로 해결할 수 있는데 생성자 주입 순환은 해결하지 못한다. 왜 생성자 주입에서는 원리상 불가능한가? Spring Boot 2.6부터 `spring.main.allow-circular-references` 기본값이 `false`인 이유와 연결해 답하라.
2. 이 컨테이너는 모든 빈을 컨테이너 생성 시점에 만든다(eager). 요청할 때 만드는 방식(lazy)과 비교해, 시나리오 6·7 같은 설정 오류가 언제 드러나는지 차이를 적어라. 이체 서버라면 어느 쪽이 사고를 줄이는가?
3. 시나리오 7에서 `SmsNotifier`를 기본값으로 쓰고 싶다면 컨테이너에 무엇을 추가해야 하나? Spring의 `@Primary`와 `@Qualifier`는 각각 어떤 규칙을 타입 해석 규칙에 끼워 넣는가?
4. (다음 미션 연결) 이 컨테이너가 `getBean(TransferEngine.class)`로 진짜 구현체 대신 "호출 시간을 재는 객체"를 돌려주게 하려면 생성 단계 어디에 코드를 끼워야 하나? M3-4에서 만들 프록시와 Spring의 `BeanPostProcessor`가 그 자리다.
