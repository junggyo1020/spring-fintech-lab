# M3-4 프록시 직접 만들기

> 가이드 수준: L2, 예상 시간: 4~5h, 선행: M3-2

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 메서드 실행 시간 측정 기능을 데코레이터, JDK 동적 프록시(`InvocationHandler`), CGLIB 프록시(Spring `ProxyFactory`) 3가지로 구현하고 같은 테스트를 통과시킨다.
- JDK 동적 프록시에서 target 예외를 풀지 않으면 호출자가 `UndeclaredThrowableException`을 받는 것을 재현하고, 원래 예외 인스턴스가 그대로 전달되도록 고친다.
- CGLIB 프록시에서 final 메서드와 self-invocation이 가로채지지 않는 것을 테스트 2개로 보여주고, final 메서드가 `null`을 반환하는 이유를 설명한다.
- 3가지 방식의 차이를 7개 열의 비교표로 기록한다.

## 배경
M3-2까지 이체 엔진에는 "이 호출이 몇 ms 걸렸나"를 남기는 코드가 없다. 대외기관 연동이나 DB 락 대기로 이체가 3초씩 걸려도, 메서드마다 `System.nanoTime()`을 직접 넣지 않으면 어디가 느린지 모른다. 그렇다고 이체, 조회 메서드 20개에 측정 코드를 복사하면 1곳만 빠져도 장애 분석 때 그 구간이 비어 있다. 프록시는 target 코드를 고치지 않고 호출 앞뒤에 기능을 붙인다. Spring의 AOP(M3-5)와 `@Transactional`(Phase 5)은 이 미션에서 손으로 만드는 CGLIB 프록시를 Spring이 자동으로 만들어 주는 것이다. README 3절을 먼저 읽는다.

## 요구사항
패키지: `lab.bank.proxy`. 이 미션의 클래스는 Spring 빈으로 등록하지 않는다 (`@Component` 없음). 테스트는 순수 단위 테스트로 작성한다.

### 제공하는 핵심 시그니처
```java
public record MethodTiming(String targetClass, String method, long elapsedNanos, boolean failed) {}

public interface TimingRecorder {
    void record(MethodTiming timing);
    List<MethodTiming> timings();            // 기록 순서대로, 수정 불가능한 복사본
}

public final class TimingProxies {
    public static TransferEngine decorate(TransferEngine target, TimingRecorder recorder)
    public static <T> T jdk(T target, Class<T> iface, TimingRecorder recorder)
    public static <T> T cglib(T target, TimingRecorder recorder)
}
```

### 1. 공통 측정 규칙 (3가지 방식 모두)
1. `targetClass` = **target**의 `getClass().getSimpleName()` (프록시 클래스 이름이 아니다). `method` = 메서드 이름.
2. `elapsedNanos` = target 메서드 호출 직전과 직후의 `System.nanoTime()` 차이.
3. target이 정상 반환하면 `failed = false`, 그 반환값을 그대로 돌려준다.
4. target이 예외를 던지면 `failed = true`로 기록한 뒤 **target이 던진 예외 인스턴스 그대로** 다시 던진다. 감싸거나 새로 만들지 않는다.
5. `java.lang.Object`에 선언된 메서드(`toString`, `hashCode`, `equals`)는 측정하지 않고 target에 위임만 한다. 판별 기준: `method.getDeclaringClass() == Object.class`.
6. `TimingRecorder` 구현체 `InMemoryTimingRecorder`는 스레드 100개가 동시에 기록해도 기록이 사라지지 않는다.

### 2. 데코레이터: `TimedTransferEngine`
- `TransferEngine`을 구현하고 생성자로 target `TransferEngine`과 `TimingRecorder`를 받는다. `TransferEngine`의 모든 메서드에 1번 규칙을 손으로 구현한다. `TimingProxies.decorate`는 이 클래스를 생성해 반환한다.

### 3. JDK 동적 프록시: `TimingInvocationHandler`
- `java.lang.reflect.InvocationHandler` 구현. `TimingProxies.jdk`는 `Proxy.newProxyInstance`로 프록시를 만든다.
- `iface`가 인터페이스가 아니면 `IllegalArgumentException` (메시지에 타입 simple name). `target`이 `iface`를 구현하지 않으면 `IllegalArgumentException`. `target`이나 `iface`가 `null`이면 `NullPointerException`.

### 4. CGLIB: `TimingInterceptor`
- `org.aopalliance.intercept.MethodInterceptor` 구현. `TimingProxies.cglib`는 `org.springframework.aop.framework.ProxyFactory`에 target을 넣고 `setProxyTargetClass(true)`로 **인터페이스가 있어도 하위 클래스 프록시**를 만든다.
- target 클래스가 `final`이면 `ProxyFactory.getProxy()`가 던지는 `AopConfigException`을 그대로 전파한다.
- 원본 CGLIB 라이브러리(`cglib:cglib`)를 의존성에 추가하지 않는다. Spring이 `org.springframework.cglib`로 재패키징한 것이 `spring-core`에 들어 있다 (README 3절).

### 5. 측정 대상 클래스
1. `FeeCalculator` (`lab.bank.proxy`, 인터페이스 없음, `final` 아님). 생성자 `FeeCalculator(String policyName)`.
   - `Money feeOf(Money amount)`: 이 미션의 수수료 규칙: 금액이 1,000,000원 미만이면 500원, 1,000,000원 이상이면 1,000원. 금액이 0원 이하면 Phase 1의 `InvalidAmountException`.
   - `Money totalDebit(Money amount)`: `amount + this.feeOf(amount)`. **반드시 `feeOf`를 내부 호출해서** 구한다 (self-invocation 관찰용).
   - `public final String policyName()`: 생성자에서 받은 `policyName` 필드를 반환한다.
2. 테스트 전용 클래스 (`src/test/java/lab/bank/proxy/`):
   - `StubTransferEngine implements TransferEngine`: `balanceOf`는 `Thread.sleep(50)` 후 0원을 반환, `transfer`는 생성자로 받은 `StubFailureException` 인스턴스를 던진다, `historyOf`는 빈 리스트를 반환.
   - `StubFailureException extends RuntimeException`.
   - `FinalFeeCalculator`: `final class`, 메서드 `Money feeOf(Money)` 1개.

## 테스트 시나리오
"D/J/C"는 데코레이터 / JDK 동적 프록시 / CGLIB를 뜻한다. "D/J/C 각각"인 행은 같은 단언을 3가지 방식에 대해 `@ParameterizedTest`(방식 이름을 인자로)로 실행한다.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | D/J/C 각각, target = `StubTransferEngine` | `balanceOf(아무 계좌번호)` | 0원 반환. `timings()` 크기 1: `targetClass="StubTransferEngine"`, `method="balanceOf"`, `elapsedNanos ≥ 50,000,000`, `failed=false` |
| 2 | D/J/C 각각, target = `StubTransferEngine(ex)` | `transfer(아무 명령)` | 호출자가 잡은 예외가 `ex`와 같은 인스턴스(`isSameAs`). `timings()` 크기 1, `failed=true` |
| 3 | J, 2번의 `TimingInvocationHandler`에서 `method.invoke`가 던지는 `InvocationTargetException`을 풀지 않은 버전 (실험 후 원복) | `transfer(...)` | 호출자가 `java.lang.reflect.UndeclaredThrowableException`을 받는다. 결과를 TIL에 기록하고, 원복한 코드로 2번이 통과한다 |
| 4 | J, target = `StubTransferEngine` | `toString()`, `hashCode()`, `equals(프록시 자신)` 각 1번 | `timings()` 크기 0 |
| 5 | J | `Proxy.isProxyClass(proxy.getClass())` | `true` |
| 6 | J | `(StubTransferEngine) proxy` 캐스팅 | `ClassCastException` |
| 7 | J | `TimingProxies.jdk(new FeeCalculator("FLAT-2026"), FeeCalculator.class, recorder)` | `IllegalArgumentException`, 메시지에 `FeeCalculator` 포함 |
| 8 | C, target = `StubTransferEngine` | `proxy.getClass().getName()`과 `proxy instanceof StubTransferEngine` | 이름에 `$$SpringCGLIB$$` 포함, `instanceof` 결과 `true` |
| 9 | C, target = `new FeeCalculator("FLAT-2026")` | `feeOf(10,000원)` | 500원. `timings()` 크기 1, `method="feeOf"`, `targetClass="FeeCalculator"` |
| 10 | 9번과 같은 준비 | `feeOf(999,999원)`, `feeOf(1,000,000원)` | 500원, 1,000원 (경계값) |
| 11 | 9번과 같은 준비 | `feeOf(0원)` | `InvalidAmountException`. `timings()` 크기 1, `failed=true` |
| 12 | 9번과 같은 준비 | `totalDebit(10,000원)` | 10,500원. `timings()` 크기 **1**, 그 항목의 `method="totalDebit"` (`feeOf` 기록 없음) |
| 13 | 9번과 같은 준비 | `proxy.policyName()`과 `target.policyName()` | 프록시는 `null`, target은 `"FLAT-2026"`. `timings()` 크기 0 |
| 14 | C, target = `FinalFeeCalculator` 인스턴스 | `TimingProxies.cglib(...)` | `org.springframework.aop.framework.AopConfigException`, 메시지에 `Could not generate CGLIB subclass` 포함 |
| 15 | J, target = `StubTransferEngine`, Phase 2 README 5절 동시성 틀, 스레드 100개 | 각 스레드가 `balanceOf` 1번 | `timings()` 크기 100 |

시나리오 12 계산: 10,000원 < 1,000,000원 → 수수료 500원 → 10,000 + 500 = 10,500원.
시나리오 13, 14의 동작은 Spring Boot 4.1.2(Spring Framework 7)에서 실행해 확인했다. 13번 실행 시 `CglibAopProxy`가 `Public final method [...] cannot get proxied via CGLIB` 경고를 로그에 남긴다.

## 제약
- 데코레이터, JDK 프록시, CGLIB 프록시는 모두 같은 `TimingRecorder`에 기록한다. 방식마다 다른 측정 코드를 쓰면 비교가 되지 않는다.
- `FeeCalculator`와 `StubTransferEngine`(target) 코드 안에 측정 코드를 넣지 않는다: target을 고치지 않는 것이 프록시를 쓰는 이유다.
- 시나리오 1의 상한값(예: `< 100ms`)을 단언하지 않는다. CI 환경 부하에 따라 sleep이 길어져 테스트가 우연히 실패한다.
- Spring AOP(`@Aspect`)를 쓰지 않는다: M3-5에서 쓴다.

## 힌트
<details>
<summary>힌트 1: 시나리오 13에서 `null`이 나오는 이유를 찾는 순서</summary>

(1) CGLIB 프록시는 target의 하위 클래스 인스턴스다. 그 인스턴스의 `policyName` 필드에는 무엇이 들어 있나? (2) Spring은 프록시 인스턴스를 만들 때 `FeeCalculator(String)` 생성자를 호출하는가? README 3절의 Objenesis 문단을 다시 읽는다. (3) `final` 메서드는 하위 클래스에서 오버라이드할 수 없으므로 `proxy.policyName()`은 어느 객체의 필드를 읽는가? 디버거로 `proxy`의 필드 값을 확인해 TIL에 캡처를 남긴다.
</details>

## 완료 기준
- [ ] `./gradlew test --tests 'lab.bank.proxy.*'`에서 시나리오 1~2(각 3케이스), 4~15가 통과한다
- [ ] `grep -rn "nanoTime" src/main/java/lab/bank/proxy/FeeCalculator.java` 결과가 0줄이다
- [ ] 시나리오 3의 `UndeclaredThrowableException` 스택 트레이스 첫 3줄과 원인 체인(`getCause()` 클래스 이름)이 TIL에 있다
- [ ] `docs/M3-4-proxy-comparison.md`에 열 `방식 | 인터페이스 필요 | getClass().getName() 실제 출력 | final 메서드 | self-invocation | Object 메서드 처리 | TransferEngine에 메서드 1개 추가 시 고칠 파일 수`인 표가 있고 3행(D/J/C)이 모두 채워져 있다

## 생각해볼 질문
1. 시나리오 12에서 `feeOf`도 측정되게 하려면 `FeeCalculator`를 어떻게 바꿔야 하나? 방법 2가지를 적고, 각각 `FeeCalculator`가 프록시의 존재를 알게 되는지 비교하라 (M3-5에서 Spring AOP로 같은 문제를 다시 만난다).
2. 데코레이터 방식은 메서드마다 코드를 써야 하지만 컴파일러가 누락을 잡아준다. JDK 프록시, CGLIB는 코드가 적은 대신 무엇을 잃는가? 측정 대상이 메서드 3개뿐이면 어떤 방식을 고르겠는가?
3. Spring Boot가 인터페이스가 있는 빈에도 기본으로 CGLIB 프록시를 쓰는 이유를 시나리오 6과 연결해 설명하라 (`TransferEngine` 타입 대신 구현 클래스 타입으로 주입받는 코드가 있다면?).
4. (Phase 5 연결) Phase 5의 `@Transactional`도 이 미션의 `TimingInterceptor`처럼 메서드 호출 앞뒤에 "트랜잭션 시작 / 커밋 또는 롤백"을 붙이는 프록시다. 시나리오 12, 13의 결과로 볼 때, `final` 메서드나 같은 클래스 내부 호출에 붙은 `@Transactional`은 어떻게 동작할지 예측해 적어라.
