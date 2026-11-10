# M3-5 감사 로그 AOP

> 가이드 수준: L2, 예상 시간: 4~6h, 선행: M3-4

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- `@Audited`가 붙은 메서드의 호출자, 메서드, 인자(계좌번호 마스킹), 결과 또는 예외, 소요 시간을 `@Aspect` + `@Around`로 기록하고, 이체 코드에는 감사 코드를 한 줄도 넣지 않는다.
- `ThreadLocal` 기반 `CallerContext`를 정리하지 않으면 스레드 풀에서 다른 요청의 호출자가 남는 것을 테스트로 재현하고, `runAs`의 `finally`로 막는다.
- self-invocation으로 감사가 누락되는 것을 "감사 로그 0건" 테스트로 재현하고, 빈 분리와 자기 주입 2가지로 고친 뒤 장단점을 표로 비교한다.
- 감사 저장이 실패했을 때 이체가 이미 반영돼 있는 것을 테스트로 보여주고, 이 한계가 Phase 5 트랜잭션과 어떻게 연결되는지 설명한다.

## 배경
금융회사는 "누가, 언제, 어떤 계좌로, 얼마를 옮기려 했고, 결과가 무엇이었나"를 남겨야 한다. 사고 조사, 내부 감사, 민원 대응 모두 이 기록에서 시작한다. 이체 메서드마다 로그 코드를 직접 넣으면 신규 메서드에서 1곳만 빠져도 그 거래는 기록 없이 실행되고, 로그에 계좌번호 원문을 남기면 그 자체가 개인정보 유출 사고가 된다. M3-4에서 손으로 만든 CGLIB 프록시를 이번에는 Spring AOP가 `@Aspect` 선언만 보고 자동으로 만든다. 그리고 M3-4 시나리오 12에서 본 self-invocation 문제가 감사 누락이라는 실제 사고로 나타난다. README 4절을 먼저 읽는다.

## 요구사항
패키지: `lab.bank.audit` (감사 기능), `lab.bank.bulk` (self-invocation 재현, 수정). 의존성 `spring-boot-starter-aspectj`는 README의 `build.gradle.kts`에 이미 있다.

### 제공하는 핵심 시그니처
```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Audited {
    String action();                 // 예: "TRANSFER"
}

public final class CallerContext {
    public static void set(String callerId)
    public static String current()                                // 설정 안 됐으면 "UNKNOWN"
    public static void clear()
    public static <T> T runAs(String callerId, Supplier<T> action)
}

public interface AuditLogRepository {
    void save(AuditLog log);
    List<AuditLog> findAll();          // 저장 순서대로, 수정 불가능한 복사본
    void deleteAll();
}
```

### 1. `CallerContext`
Spring Security가 없으므로 "현재 호출자"를 `ThreadLocal<String>`에 둔다 (Phase 4 M4-7에서 `SecurityContextHolder`로 바뀐다).
1. `set(callerId)`: `null`이거나 공백 문자열이면 `IllegalArgumentException`.
2. `current()`: 현재 스레드에 값이 없으면 문자열 `"UNKNOWN"`.
3. `runAs(callerId, action)`: 호출 전 값을 기억하고 → `callerId`로 바꾸고 → `action.get()` 결과를 반환하고 → `finally`에서 **호출 전 값으로 되돌린다**. 호출 전 값이 없었으면 `remove()`한다. `action`이 예외를 던져도 되돌린 뒤 그 예외를 그대로 전파한다. `callerId` 검증은 `set`과 같다.

### 2. `AuditLog` (record, 필드는 아래 표 그대로)

| 필드 | 타입 | 값 규칙 |
|---|---|---|
| `occurredAt` | `Instant` | `Clock` 빈(M3-2)의 `instant()`, 메서드 호출 직전 시각 |
| `caller` | `String` | `CallerContext.current()` |
| `action` | `String` | `@Audited.action()` |
| `method` | `String` | `{target 클래스 simple name}.{메서드 이름}`: 프록시 클래스 이름(`$$SpringCGLIB$$`)이 아니다 |
| `args` | `String` | 각 인자를 `String.valueOf`(null은 `"null"`)로 바꿔 `", "`로 이은 뒤 `[`, `]`로 감싸고 마스킹 |
| `outcome` | `AuditOutcome` (enum `SUCCESS`, `FAILURE`) | 정상 반환이면 `SUCCESS`, 예외면 `FAILURE` |
| `result` | `String` | 성공: 반환값을 `String.valueOf` 후 마스킹 / 실패: `null` |
| `exceptionType` | `String` | 실패: 예외 클래스 simple name / 성공: `null` |
| `elapsedMillis` | `long` | 호출 직전, 직후 `System.nanoTime()` 차이 ÷ 1,000,000 (소수점 버림) |

**마스킹 규칙** (이 미션의 규칙): 정규식 `(\d{3})-\d{4}-(\d{4})`에 맞는 부분을 `$1-****-$2`로 바꾼다. `110-1234-5678` → `110-****-5678`. `args`와 `result` 모두에 적용한다.

### 3. `AuditAspect` (`@Aspect` + `@Component`)
1. 포인트컷: `@annotation(lab.bank.audit.Audited)`. 어드바이스: `@Around` 1개.
2. 순서: 시작 시각, `nanoTime` 기록 → `proceed()` → `AuditLog` 생성 → `AuditLogRepository.save` → 결과 반환 또는 예외 재던지기.
3. target 예외는 **같은 인스턴스**로 다시 던진다.
4. `save`가 예외를 던질 때 (이 미션의 규칙):
   - target이 정상 반환한 경우: `save`의 예외가 호출자에게 전파된다. target이 이미 실행한 이체는 되돌리지 않는다 (트랜잭션이 없으므로 되돌릴 방법이 없다).
   - target이 예외를 던진 경우: target 예외가 호출자에게 전파되고, `save`의 예외는 target 예외의 `addSuppressed`로 붙인다.
5. `InMemoryAuditLogRepository`(`@Component`): 스레드 100개가 동시에 `save`해도 기록이 사라지지 않는다.

### 4. 감사 대상
1. M3-2의 `TransferEngine` 구현체 `transfer` 메서드에 `@Audited(action = "TRANSFER")`를 붙인다. 애노테이션은 **구현 클래스의 메서드**에 붙인다 (인터페이스 메서드에 붙인 애노테이션은 구현 메서드로 상속되지 않는다).
2. 구현 클래스가 `final`이면 `final`을 지운다. 그대로 두면 시작 시 `BeanCreationException`(원인 `AopConfigException: Could not generate CGLIB subclass of class ...`)으로 실패한다 (README 4절). `transfer` 메서드가 `final`이면 시작은 되지만 감사가 적용되지 않는다 (M3-4 시나리오 13).

### 5. self-invocation 재현과 수정 (`lab.bank.bulk`, 모두 `@Service`, `TransferEngine`을 생성자로 주입)
1. `BulkTransferService`: `@Audited(action = "TRANSFER_ONE") public TransferResult transferOne(TransferCommand)` → `transferEngine.transfer` 호출. `public List<TransferResult> transferAll(List<TransferCommand>)` → 각 명령마다 `this.transferOne` 호출. `transferAll`에는 `@Audited`가 없다.
2. 수정 1: 빈 분리: `SplitBulkTransferService`(`transferAll`만 가짐)가 별도 빈 `TransferOneExecutor`(`@Audited(action = "TRANSFER_ONE") transferOne`)를 주입받아 호출한다.
3. 수정 2: 자기 주입: `SelfInjectedBulkTransferService`가 생성자 파라미터로 `@Lazy SelfInjectedBulkTransferService self`를 받아 `transferAll` 안에서 `self.transferOne`을 호출한다. `@Lazy` 없이 자기 자신을 생성자로 받으면 시작 시 순환 참조로 실패한다 (Spring Boot 4.1.2에서 최하위 원인 `BeanCurrentlyInCreationException` 확인).

## 테스트 시나리오
`@SpringBootTest` 테스트는 `@BeforeEach`에서 `auditLogRepository.deleteAll()`과 `CallerContext.clear()`를 호출한다. 계좌는 시나리오별 대역을 쓰고 Phase 2의 계좌 개설 API로 만든다. "impl"은 각자의 `TransferEngine` 구현 클래스 simple name이다.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 아무것도 설정 안 함 | `CallerContext.current()` | `"UNKNOWN"` |
| 2 | 없음 | `set(null)`, `set("")`, `set("  ")` | 3개 모두 `IllegalArgumentException` |
| 3 | 없음 | `runAs("alice", CallerContext::current)` 후 `current()` | 반환값 `"alice"`, 이후 `current()`는 `"UNKNOWN"` |
| 4 | 없음 | `runAs("alice", () -> { throw new IllegalStateException("x"); })` 후 `current()` | `IllegalStateException("x")` 전파, 이후 `current()`는 `"UNKNOWN"` |
| 5 | 없음 | `runAs("alice", () -> runAs("bob", CallerContext::current) + "/" + CallerContext.current())` | 반환값 `"bob/alice"`, 이후 `current()`는 `"UNKNOWN"` |
| 6 | `Executors.newFixedThreadPool(1)` | 작업 1: `set("alice")` 후 정리 없이 종료 → 작업 2: `current()` 반환 | 작업 2 결과 `"alice"` (누수 재현) |
| 7 | 6번과 같은 풀 구성(새 풀) | 작업 1: `runAs("alice", ...)` → 작업 2: `current()` 반환 | 작업 2 결과 `"UNKNOWN"` |
| 8 | `@SpringBootTest`, `710-0000-0001`(1,000,000원), `710-0000-0002`(0원) | `runAs("teller-01", ...)` 안에서 `710-req-1`, 30,000원 이체 | 로그 1건: `caller="teller-01"`, `action="TRANSFER"`, `method="impl.transfer"`, `outcome=SUCCESS`, `exceptionType=null`, `result≠null`, `elapsedMillis ≥ 0`. `args`에 `710-****-0001`과 `710-****-0002` 포함, `710-0000-0001`, `710-0000-0002`는 `args`, `result` 어디에도 없음 |
| 9 | `@SpringBootTest`, `720-0000-0001`(10,000원), `720-0000-0002`(0원) | `runAs("teller-02", ...)` 안에서 10,001원 이체 | 호출자가 M1-2의 `InsufficientBalanceException`을 받음. 로그 1건: `outcome=FAILURE`, `exceptionType="InsufficientBalanceException"`, `result=null`. `720-0000-0001` 잔액 10,000원 |
| 10 | `@SpringBootTest`, `CallerContext` 비어 있음, `721-0000-0001`(100,000원) → `721-0000-0002` | 10,000원 이체 | 로그 1건, `caller="UNKNOWN"` |
| 11 | `@SpringBootTest` | `AopUtils.isAopProxy(engine)`, `AopUtils.isCglibProxy(engine)` | 둘 다 `true` |
| 12 | `@SpringBootTest`, `730-0000-0001`~`730-0000-0100`(각 100,000원), `730-9999-9999`(0원), Phase 2 README 5절 동시성 틀, 스레드 100개 | 스레드 `i`가 `runAs("caller-" + i, ...)` 안에서 `730-req-{i}`, 1,000원을 `730-0000-{i 4자리}` → `730-9999-9999` 이체 | 로그 100건. `caller` 값 100개가 모두 다르고, 각 로그에서 `caller="caller-i"`이면 `args`에 `730-****-{i 4자리}` 포함. `730-9999-9999` 잔액 100,000원 |
| 13 | `@SpringBootTest` + `@MockitoBean AuditLogRepository` (`save`가 `new IllegalStateException("audit store down")`을 던지게 스텁), `740-0000-0001`(100,000원) → `740-0000-0002` | 30,000원 이체 | 호출자가 `IllegalStateException("audit store down")`을 받음. `740-0000-0001` 잔액 70,000원 (이체는 반영됨) |
| 14 | 13번과 같은 목, `741-0000-0001`(10,000원) → `741-0000-0002` | 10,001원 이체 | 호출자가 `InsufficientBalanceException`을 받음. `getSuppressed()`에 `IllegalStateException` 1개 |
| 15 | `@SpringBootTest`, `750-0000-0001`(1,000,000원) → `750-0000-0002`, 명령 3개(`750-req-1~3`, 각 10,000원) | `BulkTransferService.transferAll(명령 3개)` | `action="TRANSFER_ONE"` 로그 **0건**, `action="TRANSFER"` 로그 3건, `750-0000-0002` 잔액 30,000원 |
| 16 | 15번과 같은 구성, 대역 `760` | `SplitBulkTransferService.transferAll(...)` | `TRANSFER_ONE` 3건, `TRANSFER` 3건 |
| 17 | 15번과 같은 구성, 대역 `770` | `SelfInjectedBulkTransferService.transferAll(...)` | `TRANSFER_ONE` 3건, `TRANSFER` 3건 |
| 18 | `@SpringBootTest`가 없는 별도 테스트 클래스 안의 static 중첩 클래스 `EagerSelf`(`@Component`, 생성자 파라미터 `EagerSelf self`, `@Lazy` 없음) | `new AnnotationConfigApplicationContext(EagerSelf.class)` | 예외 발생, 최하위 원인이 `BeanCurrentlyInCreationException` |

시나리오 12 계산: 1,000원 × 100건 = 100,000원.
시나리오 15는 먼저 "`TRANSFER_ONE` 3건"을 기대하는 테스트로 작성해 실행하고, 실패 메시지(기대 3, 실제 0)를 `docs/M3-5-self-invocation-fixes.md`에 붙인 뒤, 기대값을 0건으로 바꾸고 `@DisplayName`을 `"M3-5 #15 self-invocation은 감사되지 않는다"`로 고친다.

## 제약
- `TransferEngine` 구현체, `BulkTransferService` 등 대상 코드에 감사 로직(로그 생성, 저장소 호출, 마스킹)을 넣지 않는다: 대상 코드에 남는 것은 `@Audited` 한 줄뿐이다.
- `CallerContext.set`을 쓴 코드는 같은 메서드의 `finally`에서 `clear()`하거나 `runAs`를 쓴다. 테스트 코드도 마찬가지다 (시나리오 6만 예외).
- 감사 로그를 `System.out`이나 로거로만 남기지 않는다: 테스트로 검증할 수 없다. 저장소에 저장한다.
- 시나리오 13, 14는 `@MockitoBean`을 쓰므로 다른 시나리오와 **별도 테스트 클래스**에 둔다. 같은 클래스에 두면 모든 시나리오에서 저장이 실패한다.
- `AopContext.currentProxy()`(`exposeProxy`)는 이 미션에서 쓰지 않는다. 생각해볼 질문 2에서 비교만 한다.

## 힌트
<details>
<summary>힌트 1: `@Around`에서 필요한 정보 꺼내기</summary>

`ProceedingJoinPoint`의 `getTarget()`(target 객체), `getSignature().getName()`(메서드 이름), `getArgs()`(인자 배열)을 본다. `@Audited`의 `action` 값은 포인트컷을 `@annotation(audited)`로 쓰고 어드바이스 메서드 파라미터를 `Audited audited`로 선언하면 바인딩된다 (Spring Framework Reference "Declaring Advice" › "Passing Parameters to Advice" 단락). 바인딩 이름을 쓸 때는 포인트컷 문자열에 패키지 이름 대신 파라미터 이름이 들어간다.
</details>

<details>
<summary>힌트 2: 시나리오 15에서 `TRANSFER`는 3건인데 `TRANSFER_ONE`은 0건인 이유</summary>

`transferAll` 안의 `this`는 프록시가 아니라 `BulkTransferService` target이다. 그런데 `transferOne` 안에서 호출하는 `transferEngine`은 무엇인가? 생성자로 주입받은 그 객체의 클래스 이름을 출력해 보라.
</details>

## 완료 기준
- [ ] `./gradlew test --tests 'lab.bank.audit.*' --tests 'lab.bank.bulk.*'`에서 시나리오 1~18이 통과한다
- [ ] `TransferEngine` 구현 클래스에서 `lab.bank.audit` 패키지를 참조하는 줄이 `@Audited` import 1줄과 애노테이션 1줄뿐이다
- [ ] `docs/M3-5-self-invocation-fixes.md`에 시나리오 15의 첫 실패 메시지와, 열 `방법 | 새로 만들거나 바꾼 클래스 수 | 대상 코드가 프록시 존재를 아는가 | 시작 시 실패 위험 | TRANSFER_ONE 로그 건수 | 단점`인 표(3행: 원래 코드, 빈 분리, 자기 주입)가 있다
- [ ] TIL에 시나리오 13 결과(감사는 실패했는데 이체는 반영됨)가 금융 시스템에서 왜 문제인지 3문장 이내로 적었다

## 생각해볼 질문
1. 빈 분리와 자기 주입 중 팀 표준으로 하나를 고른다면 무엇을 고르겠는가? `SelfInjectedBulkTransferService`를 처음 보는 동료가 `self` 필드를 "불필요한 코드"로 지우면 어떤 일이 생기고, 어떤 테스트가 그것을 잡아내는가?
2. `@EnableAspectJAutoProxy(exposeProxy = true)` + `AopContext.currentProxy()`도 self-invocation을 피하는 방법이다. 이 방법은 대상 코드가 Spring AOP API에 의존하게 만든다. 자기 주입과 비교해 장단점을 적어라.
3. `CallerContext`를 가상 스레드(M2-6)에서 쓰면 `ThreadLocal` 누수 위험은 플랫폼 스레드 풀과 비교해 어떻게 다른가? 가상 스레드는 작업마다 새로 만들어진다는 점을 근거로 답하라.
4. (Phase 5 연결) 시나리오 13에서 감사 저장이 실패해도 이체가 되돌아가지 않았다. Phase 5에서 이체와 감사 저장을 같은 DB 트랜잭션에 넣는다면, `@Transactional` 프록시와 `AuditAspect` 프록시 중 어느 것이 바깥에 있어야 감사 실패 시 이체가 롤백되는가? `@Transactional`도 프록시이므로 시나리오 15와 같은 self-invocation 함정이 그대로 있다는 점도 함께 생각하라.
