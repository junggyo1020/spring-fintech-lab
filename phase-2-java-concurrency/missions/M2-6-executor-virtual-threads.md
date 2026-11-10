# M2-6 `ExecutorService`와 가상 스레드

> 가이드 수준: L2, 예상 시간: 4~5h, 선행: M2-4

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 스레드 풀 4종(고정, 캐시, 단일, 가상 스레드)에 100ms 대기 작업을 넣어 소요 시간과 최대 플랫폼 스레드 수를 README 6절 규칙으로 측정하고, 측정값을 계산한 예상값과 비교한다.
- `ThreadPoolExecutor`의 core/max/큐 크기 설정에 따라 작업 20개 중 몇 개가 거절되는지 미리 계산하고 실행 결과로 확인한다.
- `Future`와 `CompletableFuture`로 이체 1,000건을 비동기로 실행해 성공, 실패를 집계하고, `orTimeout`/`completeOnTimeout`의 동작 차이를 테스트로 보여준다.
- JDK 21에서 `synchronized` 안의 블로킹이 가상 스레드를 캐리어에 고정(pinning)하는 것을 소요 시간과 JFR 이벤트 수로 보여준다.

## 배경
M2-1~M2-4에서는 테스트마다 스레드를 직접 만들었다. 운영 서버는 요청마다 스레드를 새로 만들지 않고 풀을 쓴다. Spring Boot의 Tomcat 요청 처리 스레드, `@Async`, DB 커넥션 풀이 모두 같은 구조다. 풀 크기를 잘못 정하면 요청이 큐에 쌓여 응답 시간이 늘거나, 스레드를 무제한으로 만들다 OS 한도에 걸려 서버가 멈춘다. Java 21의 가상 스레드는 블로킹 대기 중 플랫폼 스레드를 내놓아 적은 플랫폼 스레드로 많은 대기 작업을 처리하지만, JDK 21에서는 `synchronized` 안에서 블로킹하면 이 이점이 사라진다. M2-4에서 만든 `ReentrantLock` 이체가 여기서 그 차이를 보여준다.

## 요구사항
1. **1단계: 스레드 풀 4종 측정** (`lab.bank.experiment`, README 6절 측정 규칙 적용)
   - 작업 1개 = `Thread.sleep(100)` 후 종료. 풀별 작업 수와 예상 소요 시간:

     | 풀 | 생성 방법 | 작업 수 | 예상 소요 시간 |
     |---|---|---|---|
     | 고정 | `Executors.newFixedThreadPool(100)` | 10,000 | 10,000 ÷ 100 × 100ms = 10,000ms |
     | 캐시 | `Executors.newCachedThreadPool()` | 10,000 | 직접 예측해 측정 전에 적는다 |
     | 단일 | `Executors.newSingleThreadExecutor()` | 100 | 100 × 100ms = 10,000ms |
     | 가상 | `Executors.newVirtualThreadPerTaskExecutor()` | 10,000 | 직접 예측해 측정 전에 적는다 |

     단일 스레드 풀에 10,000개를 넣으면 10,000 × 100ms = 1,000초(16.7분)가 걸리므로 100개로 줄였다.
   - 1회 측정 = 풀 생성 → 작업 전부 제출 → `close()`(try-with-resources)로 모든 작업 종료 대기. 소요 시간은 제출 시작부터 `close()` 반환까지다.
   - 플랫폼 스레드 수: `ManagementFactory.getThreadMXBean()`으로 측정 직전 `getThreadCount()`(기준값)를 기록하고 `resetPeakThreadCount()`를 호출한다. 측정 직후 `getPeakThreadCount()`를 기록한다. 풀이 추가로 만든 플랫폼 스레드 수 ≈ 최대값 − 기준값. JDK 21의 `ThreadMXBean` 스레드 수는 플랫폼 스레드만 세고 가상 스레드는 세지 않는다 (`ThreadMXBean.getThreadCount` Javadoc).
   - `Thread.activeCount()`는 쓰지 않는다. 호출한 순간 현재 스레드 그룹의 플랫폼 스레드 수 추정값만 반환하므로 측정 중 최대값을 잡지 못한다.
   - 캐시 풀은 작업마다 놀고 있는 스레드가 없으면 새 플랫폼 스레드를 만든다. OS의 프로세스당 스레드 한도(macOS는 `sysctl kern.num_taskthreads`로 확인, 이 문서 작성 환경에서 4,096)를 넘으면 `OutOfMemoryError: unable to create native thread`가 난다. 이 오류가 나면 그 결과를 표에 그대로 기록한다.
   - 전체 측정 시간: 고정, 단일 풀이 회당 약 10초 × 8회(워밍업 3 + 측정 5)이므로 약 3분 걸린다.
2. **2단계: `ThreadPoolExecutor` 직접 생성**
   - `new ThreadPoolExecutor(2, 4, 60, SECONDS, new ArrayBlockingQueue<>(10))`(기본 거절 정책 `AbortPolicy`)에 `Thread.sleep(1_000)` 작업 20개를 연달아 `execute`한다.
   - 실행 전에 "실행 중 스레드 수, 큐에 들어간 수, 거절된 수"를 계산해 TIL에 적고, 실행 결과(`RejectedExecutionException` 건수, `getPoolSize()`, `getQueue().size()`)와 비교한다.
   - 거절 정책을 `ThreadPoolExecutor.CallerRunsPolicy`로 바꿔 같은 실험을 하고, 제출하는 스레드에 무슨 일이 생기는지(20개 제출에 걸린 시간) 기록한다.
3. **3단계: `Future`와 `CompletableFuture`**
   - 비동기 이체: 계좌 A 1,000,000원, B 0원. `BankService.transfer(A, B, 1,500원, "메모")` 호출 1,000개를 `Callable`로 감싸 가상 스레드 실행기에 `submit`하고 `List<Future<?>>`로 모은다. `Future.get()`이 정상 반환하면 성공, `ExecutionException`의 `getCause()`가 `InsufficientBalanceException`이면 실패로 센다.
   - 체이닝: "잔액 조회 → 한도 조회 → 이체"를 `CompletableFuture.supplyAsync` → `thenCompose` → `thenApply`로 잇는다. 한도 조회는 이 단계용 가짜 구현 `FakeLimitClient`(`Money remainingLimit(AccountNumber)`, 항상 5,000,000원 반환, 생성자로 지연 시간과 예외 발생 여부를 받음)를 쓴다. 잔액 또는 남은 한도가 이체 금액보다 작으면 이체 단계에서 해당 예외를 던진다.
   - 타임아웃: 체인 끝에 `orTimeout(200, MILLISECONDS)`와 `completeOnTimeout(대체값, 200, MILLISECONDS)`를 각각 붙여 결과를 비교한다.
4. **4단계: 가상 스레드와 락 (pinning)** (`lab.bank.experiment`, README 6절 측정 규칙 적용)
   - 계좌 2,000개로 서로 겹치지 않는 1,000쌍을 만든다 (가상 스레드 i는 계좌 2i → 2i+1로 1원 이체). 두 계좌 락을 쥔 상태에서 외부 API 호출을 흉내 내는 `Thread.sleep(50)`을 한다.
   - 버전 S: 락을 `synchronized`로 잡는다. 버전 R: M2-4의 `ReentrantLock`으로 잡는다. 가상 스레드 1,000개를 `newVirtualThreadPerTaskExecutor()`로 동시에 실행해 소요 시간을 잰다.
   - 예상값 (JDK 21): 가상 스레드 스케줄러의 캐리어 수 P는 기본값이 CPU 코어 수다. 버전 S는 고정된 가상 스레드가 50ms 동안 캐리어를 놓지 않으므로 약 ⌈1,000 ÷ P⌉ × 50ms, 버전 R은 약 50ms + 스케줄링 오버헤드다. 이 문서 작성 환경(JDK 21.0.8, 코어 11개)에서 S 약 4,880ms(계산 ⌈1,000 ÷ 11⌉ × 50 = 4,550ms), R 약 60ms였다.
   - pinning 관찰 (JDK 21~23): `-Djdk.tracePinnedThreads=full`(또는 `short`) 옵션으로 실행하면 가상 스레드가 `synchronized` 안에서 블로킹할 때 스택 트레이스가 표준 출력에 찍힌다. 이 시스템 속성은 JDK 24에서 제거되어(JEP 491) 설정해도 효과가 없다.
   - pinning 관찰 (JDK 21 이상 공통): JFR로 기록하고 `jdk.VirtualThreadPinned` 이벤트 수를 센다.
     ```bash
     java -XX:StartFlightRecording=filename=pinning.jfr -cp build/classes/java/main lab.bank.experiment.PinningExperiment
     jfr summary pinning.jfr | grep VirtualThreadPinned
     jfr print --events jdk.VirtualThreadPinned pinning.jfr | head -30
     ```
     `jfr` 명령은 `$JAVA_HOME/bin/jfr`에 있다 (PATH에 없으면 전체 경로로 실행). 이 이벤트는 기본 설정에서 20ms 이상 고정된 경우만 기록된다. 이 문서 작성 환경(JDK 21.0.8)에서 버전 S 1회 실행에 이벤트 1,000건, 버전 R은 0건이었다.
   - JDK 24 이상: JEP 491로 `synchronized` 안에서 블로킹해도 가상 스레드가 캐리어를 내놓는다. 버전 S와 R의 차이가 줄어드는지 JDK 24 이상이 설치되어 있으면 같은 실험으로 확인한다 (선택). JEP 491 이후에도 네이티브 메서드나 Foreign Function & Memory API로 호출한 네이티브 코드가 다시 Java 코드를 호출해 그 안에서 블로킹하는 경우, 클래스 초기화(`<clinit>`) 중 블로킹하는 경우 등은 여전히 고정된다 (JEP 491 "Future Work" 절).
5. **5단계: 올바른 종료와 인터럽트**
   - `shutdown()`과 `shutdownNow()`의 차이를 테스트로 보인다: `Thread.sleep(10_000)` 작업 10개를 넣은 고정 풀(10개)에서 `shutdown()` 후 `awaitTermination(1, SECONDS)`는 `false`, `shutdownNow()` 후 `awaitTermination(1, SECONDS)`는 `true`이고 `shutdownNow()`가 반환한 대기 작업 목록 크기는 0이다.
   - 작업은 `InterruptedException`을 받으면 인터럽트 플래그를 복구하고 즉시 반환한다.
   - Java 19부터 `ExecutorService`는 `AutoCloseable`이다. 이 Phase의 모든 측정, 테스트 코드에서 풀은 try-with-resources로 닫는다.

## 테스트 시나리오

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | `ThreadPoolExecutor(2, 4, 60s, ArrayBlockingQueue(10))`, `AbortPolicy` | 1초 대기 작업 20개를 연달아 `execute` | `RejectedExecutionException` 6건, `getPoolSize() == 4`, `getQueue().size() == 10` |
| 2 | A 1,000,000원, B 0원, 가상 스레드 실행기 | `transfer(A, B, 1,500원)` 1,000건 `submit` 후 `Future.get()` | 성공 666건, `InsufficientBalanceException` 334건, A 1,000원, B 999,000원 |
| 3 | A 10,000원, `FakeLimitClient` 지연 0 | 체인으로 3,000원 이체 | `join()` 정상 반환, A 7,000원 |
| 4 | `FakeLimitClient`가 `IllegalStateException`을 던지도록 설정 | 체인 실행 후 `join()` | `CompletionException`, `getCause()`가 `IllegalStateException`, A 잔액 변화 없음 |
| 5 | `FakeLimitClient` 지연 500ms, 체인 끝에 `orTimeout(200ms)` | `join()` 후 800ms 대기 | `CompletionException`, `getCause()`가 `TimeoutException`, 800ms 뒤에도 A 잔액 변화 없음 (이체 단계 미실행) |
| 6 | `FakeLimitClient` 지연 500ms, 체인 끝에 `completeOnTimeout(대체값, 200ms)` | `join()` | 대체값 반환, 호출부터 반환까지 200ms 이상 500ms 미만 |
| 7 | 고정 풀(10), `Thread.sleep(10_000)` 작업 10개 | `shutdown()` → `awaitTermination(1s)` | `false` (테스트 끝에서 `shutdownNow()`로 정리) |
| 8 | 7과 같은 새 풀 | `shutdownNow()` → `awaitTermination(1s)` | `true`, `shutdownNow()` 반환 목록 크기 0 |

시나리오 1 계산: core 2개 스레드가 작업 1~2를 실행 → 작업 3~12는 큐(10칸) → 큐가 차면 max 4까지 스레드를 늘려 작업 13~14 실행 → 작업 15~20(6개) 거절.
시나리오 2 계산: 1,000,000 ÷ 1,500 = 666 나머지 1,000 → 성공 666건(999,000원), 실패 1,000 − 666 = 334건, A 1,000원.

## 제약
- `catch (InterruptedException e) {}`처럼 인터럽트를 삼키지 않는다. 플래그를 복구하거나(`Thread.currentThread().interrupt()`) 다시 던진다.
- 1단계, 4단계 측정은 `main` 메서드로 실행한다 (README 6절). 4단계는 측정표 위에 JDK 버전을 반드시 적는다. JDK 버전에 따라 결과가 달라진다.
- 풀 크기를 정할 때 `Runtime.getRuntime().availableProcessors()` 같은 측정값 대신 숫자를 하드코딩했다면 그 숫자의 근거를 주석에 적는다.

## 힌트
<details>
<summary>힌트 1: 시나리오 5에서 이체가 실행되지 않는 이유</summary>

`orTimeout`은 체인의 마지막 단계(`thenApply`로 만든 이체 단계)를 `TimeoutException`으로 먼저 완료시킨다. 이미 완료된 단계의 함수는 앞 단계가 나중에 끝나도 실행되지 않는다. 반면 이미 실행 중인 한도 조회 작업은 취소되지 않고 끝까지 실행된다 (`CompletableFuture.cancel` Javadoc: 인터럽트를 보내지 않음). 운영 코드에서 이 차이가 무엇을 의미하는지 생각해 본다.
</details>

<details>
<summary>힌트 2: 가상 스레드 캐리어 수 확인</summary>

가상 스레드 스케줄러는 `ForkJoinPool`이고 병렬도 기본값은 `availableProcessors()`다. `-Djdk.virtualThreadScheduler.parallelism=2`로 실행하면 4단계 버전 S 소요 시간이 어떻게 바뀌는지 계산값과 비교한다 (JEP 444 "Scheduling virtual threads" 절).
</details>

## 완료 기준
- [ ] `./gradlew test`에서 시나리오 1~8이 통과한다
- [ ] TIL에 1단계 측정표가 있다. 표 위에 JDK 버전, CPU 코어 수, OS, 열은 `풀`, `작업 수`, `예상 소요 시간(ms)`, `소요 시간 중앙값(ms)`, `최소(ms)`, `최대(ms)`, `플랫폼 스레드 기준값`, `플랫폼 스레드 최대값`이다
- [ ] TIL에 2단계 계산값과 실행 결과 비교, `CallerRunsPolicy` 실험 결과가 있다
- [ ] TIL에 4단계 측정표가 있다. 열은 `JDK 버전`, `버전(S/R)`, `예상 소요 시간(ms)`, `소요 시간 중앙값(ms)`, `jdk.VirtualThreadPinned 이벤트 수`이다
- [ ] `grep -rn "InterruptedException" src` 결과의 모든 `catch` 블록이 플래그를 복구하거나 다시 던진다

## 생각해볼 질문
1. 가상 스레드는 CPU만 쓰는 작업(예: 이자 계산 100만 건)도 빠르게 하는가? 1단계 결과를 근거로, 가상 스레드가 효과를 내는 작업의 조건을 적어 보자.
2. 가상 스레드 10,000개가 동시에 DB에 접근하고 커넥션 풀 크기가 10이면 9,990개는 어디서 무엇을 기다리는가? Phase 5에서 HikariCP `connectionTimeout`과 연결해 생각해 보자.
3. Tomcat 요청 처리 스레드(기본 최대 200개)가 모두 사용 중일 때 들어온 요청은 어디에 쌓이고, 그 큐마저 차면 어떻게 되는가? Phase 4에서 확인할 설정 이름을 찾아 적어 두자.
