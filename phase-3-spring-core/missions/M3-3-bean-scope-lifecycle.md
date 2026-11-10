# M3-3 빈 스코프, 라이프사이클과 싱글톤 상태 문제

> 가이드 수준: L2, 예상 시간: 3~4h, 선행: M3-2

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 싱글톤 빈 하나의 라이프사이클 콜백 7단계가 호출되는 순서를 기록하는 테스트를 작성하고, 순서가 README 2절과 같음을 단언한다.
- 프로토타입 빈을 싱글톤에 생성자로 주입했을 때 인스턴스가 1개만 생기는 것과, `ObjectProvider`로 호출마다 새 인스턴스를 얻는 것을 테스트로 보여준다.
- 요청별 값을 필드에 저장하는 싱글톤 빈의 동시성 버그를 Phase 2 동시성 테스트 틀로 재현하고, "총액은 맞는데 계좌별 잔액이 틀린" 결과를 표로 기록한다.
- 같은 빈을 무상태로 고친 뒤 `@RepeatedTest(50)`에서 50회 모두 불일치 0건임을 보여준다.

## 배경
M3-2에서 `TransferEngine`은 모든 스레드가 공유하는 싱글톤 빈이 됐다. Phase 2에서 엔진 자체는 스레드 안전하게 만들었지만, 그 앞에 붙는 서비스 빈 개발자가 "메서드 여러 개에 인자로 넘기기 귀찮다"며 이체 명령을 필드에 잠깐 저장하면 문제가 다시 생긴다. 스레드 A가 저장한 명령을 스레드 B가 덮어쓰면 A 고객의 요청 대신 B 고객의 명령이 두 번 실행되고, A는 B의 이체 결과를 응답으로 받는다. 이 버그는 총액 보존 검증을 통과한다. 이체 건수와 계좌별 잔액을 확인해야 드러난다. README 2절을 먼저 읽는다.

## 요구사항
패키지: `lab.bank.lifecycle`.

### 1. 라이프사이클 기록 (파트 A)
1. `LifecycleRecorder`: 문자열 이벤트를 순서대로 저장하고 `List<String> events()`로 복사본을 돌려준다. 여러 스레드가 동시에 기록해도 이벤트가 사라지지 않아야 한다.
2. `LifecycleProbe`: 아래 7개 시점에 recorder에 정해진 문자열을 기록한다.

| 시점 | 기록할 문자열 | 구현 수단 |
|---|---|---|
| 생성자 | `constructor` | 생성자 파라미터로 `LifecycleRecorder`를 받는다 |
| setter 주입 | `setter-injection` | `@Autowired`가 붙은 `setClock(Clock)` (이 파트만 관찰용으로 setter 주입 허용) |
| 초기화 1 | `post-construct` | `@PostConstruct` (`jakarta.annotation`) |
| 초기화 2 | `after-properties-set` | `InitializingBean.afterPropertiesSet()` |
| 컨텍스트 준비 완료 | `context-refreshed` | `@EventListener(ContextRefreshedEvent.class)` |
| 소멸 1 | `pre-destroy` | `@PreDestroy` |
| 소멸 2 | `destroy` | `DisposableBean.destroy()` |

3. 파트 A, B의 클래스에는 `@Component`를 붙이지 않는다. 테스트 전용 `@Configuration` 클래스에서 `@Bean` 또는 `@Import`로 등록하고 `new AnnotationConfigApplicationContext(테스트설정.class)`로 띄운다. 애플리케이션 컨텍스트(`@SpringBootTest`)에 실험용 빈이 섞이지 않게 하기 위해서다.
4. 테스트 전용 `@Configuration`은 **테스트 클래스 안의 static 중첩 클래스**로 만든다. `src/test/java/lab/bank/` 아래의 top-level `@Configuration`, `@Component`는 `@SpringBootTest`의 컴포넌트 스캔에 포함되지만, 테스트 클래스의 중첩 클래스는 Spring Boot의 `TypeExcludeFilter`가 스캔에서 뺀다 (Spring Boot 4.1.2에서 확인). 단, `@SpringBootTest` 클래스 **자신의** 중첩 `@Configuration`은 애플리케이션 설정을 대신해 버리므로 파트 A, B 테스트에는 `@SpringBootTest`를 붙이지 않는다.

### 2. 프로토타입 스코프 (파트 B)
1. `RequestTrace`: `@Scope("prototype")`. 생성 시 `UUID.randomUUID().toString()`으로 `traceId`를 정하고 `traceId()`로 돌려준다. `@PreDestroy`에서 recorder에 `trace-destroyed:{traceId}`를 기록한다.
2. `EagerTraceService`(싱글톤): 생성자로 `RequestTrace`를 받는다. `String currentTraceId()`는 받은 `RequestTrace`의 `traceId`를 반환한다.
3. `ProviderTraceService`(싱글톤): 생성자로 `ObjectProvider<RequestTrace>`를 받는다. `String newTraceId()`는 호출마다 `getObject()`로 꺼낸 `RequestTrace`의 `traceId`를 반환한다.

### 3. 상태 있는 싱글톤의 동시성 버그 (파트 C)
1. `StatefulTransferFacade`(`@Component`): 필드 `private TransferCommand current;`를 둔다. `TransferResult execute(TransferCommand command)`는 정확히 다음 3단계를 실행한다.
   1. `current = command;`
   2. `Thread.sleep(1)`: 검증, 수수료 조회에 걸리는 시간을 흉내 내는 **재현용 장치**다. `InterruptedException`을 잡으면 `Thread.currentThread().interrupt()`로 플래그를 복구하고 `IllegalStateException`을 던진다.
   3. `return transferEngine.transfer(current);`
2. `StatelessTransferFacade`(`@Component`): 같은 3단계를 필드 없이 지역 변수(또는 파라미터)로 실행한다. 클래스의 모든 필드는 `private final`이고 주입받은 빈만 가리킨다.
3. `StatefulTransferFacadeNoSleep`(`@Component`): 1번에서 2단계(sleep)만 뺀 버전. 재현용 장치 없이도 버그가 있는지 관찰하는 용도다.
4. 세 퍼사드는 `TransferEngine` 빈을 생성자로 주입받는다.

### 4. 동시성 테스트 데이터 (파트 C 공통)
- 라운드마다 새 계좌를 쓴다. 라운드 번호 `r`의 계좌: 출금 계좌 100개 `Prr-0000-0001` ~ `Prr-0000-0100`(각 1,000,000원), 입금 계좌 1개 `Prr-9999-9999`(0원). `P`는 테스트별 접두 숫자, `rr`은 두 자리 라운드 번호다.
  - 버그 재현 테스트(sleep 있음): `P=3`, `r=00~19` → `300-0000-0001` ...
  - 버그 관찰 테스트(sleep 없음): `P=6`, `r=00~19`
  - 수정 검증 테스트: `P=4`, `r=01~50` (`RepetitionInfo.getCurrentRepetition()`)
- 스레드 `i`(1~100)는 `requestId = "{P}{rr}-req-{i}"`(예: `300-req-1`, `401-req-100`. 테스트끼리 같은 엔진 빈을 공유하므로 `P`가 빠지면 다른 테스트의 요청과 멱등성 키가 겹쳐 이체가 실행되지 않는다), `from = Prr-0000-{i를 4자리로}`, `to = Prr-9999-9999`, 금액 `i × 1,000`원인 명령 1개를 실행한다.
- Phase 2 README 5절의 동시성 테스트 틀을 쓴다. 풀 크기는 작업 수와 같은 100 (`Executors.newFixedThreadPool(100)`).
- 판정: "불일치 계좌" = 실행 후 잔액이 `1,000,000 − i × 1,000`원이 아닌 출금 계좌.

## 테스트 시나리오

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 파트 A 테스트 설정 (`LifecycleRecorder`, `Clock`, `LifecycleProbe` 등록) | 컨텍스트 생성 → `close()` | `events()`가 정확히 `[constructor, setter-injection, post-construct, after-properties-set, context-refreshed, pre-destroy, destroy]` (`containsExactly`) |
| 2 | 1번 설정 | 컨텍스트 생성 직후(`close()` 전) | `events()`가 정확히 앞 5개 (`pre-destroy`, `destroy` 없음) |
| 3 | 파트 B 설정 (`LifecycleRecorder`, `RequestTrace`, `EagerTraceService`, `ProviderTraceService`) | `EagerTraceService.currentTraceId()` 3번 | 3개 값이 모두 같다 (서로 다른 값 1개) |
| 4 | 3번 설정 | `ProviderTraceService.newTraceId()` 3번 | 3개 값이 모두 다르다 (서로 다른 값 3개) |
| 5 | 3번 설정 | `getBean(RequestTrace.class)` 2번 | 서로 다른 인스턴스 (`isNotSameAs`) |
| 6 | 3, 4번 실행 후 | 컨텍스트 `close()` | `events()`에 `trace-destroyed:`로 시작하는 항목 0개 (프로토타입은 컨테이너가 소멸 콜백을 호출하지 않는다) |
| 7 | `@SpringBootTest`, 버그 재현용 데이터(P=3) | 라운드 0부터 `StatefulTransferFacade`로 100개 동시 실행, 불일치 계좌가 1개 이상 나온 라운드에서 멈춘다 (최대 20라운드) | 20라운드 안에 불일치 계좌 ≥ 1인 라운드가 나온다. **모든 라운드에서** 출금 계좌 100개 + 입금 계좌 잔액 합계 = 100,000,000원 |
| 8 | 7번에서 불일치가 나온 라운드 | 그 라운드의 입금 계좌 잔액 확인 | 5,050,000원보다 작다 (실행되지 않은 명령이 있다) |
| 9 | `@SpringBootTest`, P=6 | `StatefulTransferFacadeNoSleep`으로 20라운드 실행 (중간에 멈추지 않음) | 단언 없음. 라운드별 불일치 계좌 수를 `docs/M3-3-singleton-state.md`에 기록 (0이 나와도 된다) |
| 10 | `@SpringBootTest`, P=4, `@RepeatedTest(50)` | `StatelessTransferFacade`로 100개 동시 실행 | 50회 모두: 불일치 계좌 0개, 입금 계좌 5,050,000원, 합계 100,000,000원, 실패(예외) 0건 |

시나리오 8, 10의 5,050,000원 계산: 1,000 × (1 + 2 + … + 100) = 1,000 × 100 × 101 ÷ 2 = 1,000 × 5,050 = 5,050,000.
합계 100,000,000원 = 출금 계좌 100개 × 1,000,000원 + 입금 계좌 0원. 이체는 계좌 사이에서 돈을 옮기기만 하므로 버그가 있어도 이 값은 변하지 않는다.

## 제약
- 파트 C의 sleep은 `StatefulTransferFacade`에만 둔다. `StatelessTransferFacade`에 sleep을 넣어도 결과가 같아야 하지만, 비교 대상을 명확히 하기 위해 넣지 않는다.
- 시나리오 7을 "실패하는 테스트"로 커밋하지 않는다. 버그가 재현됨을 단언하는 테스트로 작성해, 수정 버전(시나리오 10)과 나란히 통과시킨다.
- `synchronized`나 `ThreadLocal`로 `StatefulTransferFacade`를 "고치지" 않는다. 이 미션의 수정은 필드를 없애는 것이다. `synchronized`로 감싸면 버그는 사라지지만 모든 이체가 한 줄로 서는데, 그 이유를 생각해볼 질문 1에서 다룬다.

## 힌트
<details>
<summary>힌트 1: 시나리오 7에서 무슨 일이 일어나는가</summary>

스레드 A가 1단계에서 `current`에 자기 명령을 쓰고 sleep하는 동안 스레드 B가 `current`를 덮어쓴다. A가 깨어나면 B의 명령을 실행한다. B도 깨어나 B의 명령을 실행하는데, 같은 `requestId`라 M2-7의 멱등성 처리가 두 번째 실행을 막고 첫 결과를 돌려준다. A의 명령은 한 번도 실행되지 않는다. 불일치 계좌가 "잔액 1,000,000원 그대로"인 계좌인지 확인하라. 멱등성이 없었다면 B의 계좌는 어떻게 됐을까?
</details>

## 완료 기준
- [ ] `./gradlew test --tests 'lab.bank.lifecycle.*'`에서 시나리오 1~8, 10이 통과하고 시나리오 10은 50회로 집계된다
- [ ] `StatelessTransferFacade`의 필드가 모두 `private final`이다 (`grep -n "private [^f]" src/main/java/lab/bank/lifecycle/StatelessTransferFacade.java` 결과 0줄)
- [ ] `docs/M3-3-singleton-state.md`에 열 `테스트 | 라운드 | 불일치 계좌 수 | 입금 계좌 잔액(원) | 합계(원)`인 표가 있고, 시나리오 7(불일치가 나온 라운드까지 전부)과 시나리오 9(20라운드)의 행이 있다
- [ ] 같은 문서에 "총액 검증만으로 이 버그를 잡을 수 없는 이유"를 3문장 이내로 적었다

## 생각해볼 질문
1. `StatefulTransferFacade.execute`에 `synchronized`를 붙이면 시나리오 7의 불일치는 사라진다. 그런데 M2-7 요구사항 "서로 다른 계좌 간 작업은 서로 블로킹하지 않는다"는 어떻게 되는가? 100개 이체가 걸리는 시간을 두 방식으로 예측해 적어라.
2. 시나리오 9에서 sleep 없이 불일치가 0건이었다면 그 코드는 안전한가? Phase 2 README 5절의 "1회 통과는 안전의 증거가 아니다"를 이 결과에 적용해 설명하라.
3. 프로토타입 빈의 `@PreDestroy`가 호출되지 않는다면, 프로토타입 빈이 파일 핸들이나 DB 커넥션을 열었을 때 누가 닫아야 하나?
4. (Phase 4 연결) Phase 4의 컨트롤러도 싱글톤 빈이고 요청마다 다른 스레드가 같은 인스턴스를 호출한다. 컨트롤러에 "현재 로그인 사용자"를 필드로 저장하면 시나리오 7과 같은 일이 생긴다. Spring Security는 현재 사용자를 어디에 저장해 이 문제를 피하는가? (M3-5의 `CallerContext`와 비교)
