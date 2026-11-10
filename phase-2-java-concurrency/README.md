# Phase 2 — Java 동시성 (3주)

> 가이드 수준: L2 · 선행: Phase 1 완료 · 이 Phase의 workspace 시작 방법: Phase 1 `src/` 복사

## 학습 목표
이 Phase를 끝내면 다음을 할 수 있다.
- lost update, 가시성 문제, 데드락을 각각 재현하는 테스트를 작성하고, 고친 뒤 같은 테스트가 `@RepeatedTest(50)`에서 50회 모두 통과함을 보여준다.
- 원자성·가시성·순서 문제를 코드 예시 하나씩으로 구분하고, 각 문제에 쓰는 도구(`synchronized`, `volatile`, `ReentrantLock`, Atomic/CAS)를 표로 비교한다.
- 데드락 상태의 JVM에서 `jstack`으로 스레드 덤프를 떠 `Found one Java-level deadlock:` 절을 해석하고, 락 순서 규칙으로 데드락을 없앤다.
- 같은 문제(계좌 출금)를 `synchronized` / `ReentrantLock` / CAS 세 방식으로 구현하고, 이 README의 "성능 측정 규칙"대로 측정한 표를 남긴다.
- 서로 다른 계좌 간 이체가 서로 블로킹하지 않고, 1일 한도와 멱등성을 지키는 `TransferEngine`을 만든다.

## 이 Phase의 결과물
Phase 1의 `Account`/`BankService`를 출발점으로, 가상 스레드 10,000개가 계좌 100개 사이에서 동시에 이체해도 총액이 보존되는 이체 엔진(`TransferEngine`)과 측정표·TIL·`DESIGN.md`가 남는다.

```
phase-2-java-concurrency/workspace/
├── build.gradle.kts
├── DESIGN.md                      # M2-7 설계 문서
└── src/
    ├── main/java/lab/bank/
    │   ├── common/ money/ account/ ledger/ interest/ application/ console/   # Phase 1에서 복사
    │   ├── concurrency/           # UnsafeCounter(M2-1), CasAccount·VersionedAccount(M2-5)
    │   ├── experiment/            # 락 범위 실험(M2-2), 카운터 3종(M2-5), 스레드 풀 측정(M2-6)
    │   └── transfer/              # TransferEngine, TransferCommand, TransferResult (M2-7)
    └── test/java/lab/bank/        # 미션별 테스트
```

`TransferEngine`, `TransferCommand`, `TransferResult`는 Phase 3~5에서 같은 이름으로 계속 쓴다.

---

## 핵심 개념 정리 (미션 전에 읽기)

### 1. 동시성 문제의 3요소
| 문제 | 설명 | 예 | 해결 도구 |
|---|---|---|---|
| **원자성** | 여러 단계로 된 연산 중간에 다른 스레드가 끼어든다 | `balance = balance.minus(amount)` (읽기 → 계산 → 쓰기 3단계) | `synchronized`, `Lock`, CAS(`AtomicLong`, `AtomicReference`) |
| **가시성** | 한 스레드가 쓴 값을 다른 스레드가 읽지 못한다 | `while (!stopped)` 루프가 `stopped = true` 이후에도 끝나지 않음 | `volatile`, `synchronized`, `Lock` |
| **순서** | 컴파일러·JIT·CPU가 명령어 순서를 바꿔, 다른 스레드가 바뀐 순서를 관찰한다 | `volatile` 없는 double-checked locking에서 초기화가 덜 된 객체를 읽음 | `volatile`, `synchronized`/`Lock`, `final` 필드 |

순서 문제의 해결 도구는 "happens-before 규칙"이 아니다. happens-before는 JLS 17.4.5에 정의된 **규칙**이고, 위 표의 도구들이 그 규칙에 따라 happens-before 관계를 **만든다**.
- `volatile` 변수 쓰기는 그 변수를 이후에 읽는 동작보다 happens-before
- 모니터 `unlock`은 같은 모니터의 이후 `lock`보다 happens-before (`ReentrantLock`도 같은 메모리 의미를 갖는다 — `Lock` 인터페이스 Javadoc "Memory Synchronization" 절)
- `Thread.start()` 호출은 시작된 스레드의 모든 동작보다 happens-before, 스레드의 모든 동작은 다른 스레드가 그 스레드의 `join()`에서 돌아오는 것보다 happens-before
- 생성자가 끝난 뒤 공개된 객체의 `final` 필드는 다른 스레드에서 초기화된 값으로 보인다 (JLS 17.5)

### 2. Lost Update — 금융 동시성 버그의 원형
```
잔액 10,000원, 스레드 A와 B가 동시에 각각 3,000원 출금

A: 잔액 읽기 (10,000)
B: 잔액 읽기 (10,000)
A: 10,000 - 3,000 = 7,000 쓰기
B: 10,000 - 3,000 = 7,000 쓰기   ← A의 출금이 사라짐

결과: 6,000원이 출금됐는데 잔액 7,000원 (은행이 3,000원 손해)
```
같은 패턴이 메모리(Phase 2) → DB(Phase 5, `UPDATE` 경합) → 분산 시스템(Phase 6 다중 인스턴스, Phase 8 메시지 중복 처리)에서 다시 나온다.

### 3. 도구 비교
| 도구 | 원자성 | 가시성 | 특징 |
|---|---|---|---|
| `volatile` | 변수 하나의 읽기 1회·쓰기 1회만 원자적 (`long`/`double` 포함, JLS 17.7). `count++` 같은 읽기-계산-쓰기 복합 연산은 원자적이지 않음 | ✅ | 한 스레드만 쓰고 여러 스레드가 읽는 플래그용 |
| `synchronized` | ✅ (블록 전체) | ✅ | 블록을 벗어나면(예외 포함) 자동 해제. 타임아웃·공정성 옵션 없음. 대기 중 인터럽트로 깨울 수 없음 |
| `ReentrantLock` | ✅ (lock~unlock 구간) | ✅ | `tryLock(timeout)`, `lockInterruptibly()`, 공정성, `Condition`. `unlock()`을 반드시 `finally`에서 호출 |
| `AtomicLong`, `AtomicReference` 등 | ✅ (변수 하나에 대한 CAS) | ✅ | 락 없이 재시도. 변수 2개 이상(예: 계좌 2개)을 한 번에 바꾸지 못함 |
| 불변 객체 | 변경 연산 자체가 없음 | ✅ (`final` 필드, JLS 17.5) | 공유해도 안전. "공유하지 않거나, 바꾸지 않는다"가 첫 번째 선택지 |

### 4. 데드락 4조건 (4개가 모두 성립해야 발생)
1. 상호 배제 — 락은 한 번에 한 스레드만 가진다
2. 점유 대기 — 락 하나를 가진 채 다른 락을 기다린다
3. 비선점 — 다른 스레드가 가진 락을 빼앗을 수 없다
4. **순환 대기** — T1은 T2의 락을, T2는 T1의 락을 기다린다

M2-3은 모든 스레드가 같은 순서(계좌번호 오름차순)로 락을 잡게 해서 4번을 깬다. M2-4는 `tryLock(timeout)`으로 기다림을 포기하게 해서 2번을 깬다.

`synchronized`로 데드락에 빠진 스레드는 `interrupt()`로 깨울 수 없다. `ExecutorService.shutdownNow()`도 인터럽트를 보낼 뿐이라 이 스레드들은 JVM이 끝날 때까지 남는다. M2-3의 데드락 재현 테스트를 따로 격리하는 이유다.

### 5. 동시성 테스트 기본 틀
여러 스레드를 **동시에 출발**시키고, **모두 끝날 때까지 제한 시간 안에서 기다린 뒤**, 불변식(총액 보존, 잔액 ≥ 0)을 검증한다.

```java
@Test
void concurrentWithdraw() throws InterruptedException {
    int threadCount = 100;
    CountDownLatch ready = new CountDownLatch(threadCount);
    CountDownLatch start = new CountDownLatch(1);
    CountDownLatch done  = new CountDownLatch(threadCount);

    // 스레드 수 >= 작업 수: 100개 작업이 모두 동시에 start.await()에 도달할 수 있어야 한다
    try (ExecutorService executor = Executors.newFixedThreadPool(threadCount)) {
        for (int i = 0; i < threadCount; i++) {
            executor.submit(() -> {
                ready.countDown();
                try {
                    start.await();      // 100개가 모두 준비될 때까지 대기 → 동시에 출발
                    // TODO: 테스트할 동작
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();   // 인터럽트 플래그 복구 (삼키지 않는다)
                } catch (BankException e) {
                    // TODO: 실패 건수 집계 (예: AtomicInteger.incrementAndGet())
                } finally {
                    done.countDown();
                }
            });
        }

        ready.await();                  // 100개 작업이 모두 실행 중임을 확인
        start.countDown();              // 출발
        assertThat(done.await(10, TimeUnit.SECONDS)).isTrue();   // 10초 안에 전부 끝나야 통과
    }                                   // close(): 남은 작업이 끝날 때까지 기다린 뒤 풀 종료 (Java 19+)

    // TODO: 불변식 검증 (예: 총액 보존, 잔액 >= 0, 성공 + 실패 == 100)
}
```

각 래치가 필요한 이유:

| 래치 | 없으면 생기는 일 |
|---|---|
| `ready` | 메인 스레드가 일부 작업이 아직 제출·시작되기 전에 `start`를 열어, 먼저 시작한 작업이 혼자 끝나 버린다 (경합이 줄어 버그 재현율이 떨어진다) |
| `start` | 작업이 제출되는 순서대로 하나씩 실행을 시작해, 동시에 같은 계좌를 건드리는 구간이 짧아진다 |
| `done` | 메인 스레드가 작업이 끝나기 전에 잔액을 검증한다. `await(10, SECONDS)`의 반환값을 검사하지 않으면 데드락이 나도 테스트가 10초 뒤 "통과"한다 |

**풀 크기는 작업 수 이상이어야 한다.** `newFixedThreadPool(32)`에 작업 100개를 넣으면, 처음 32개 작업이 `start.await()`에서 멈춘 채 스레드 32개를 모두 차지한다. 나머지 68개는 큐에서 실행되지 못하므로 `ready`가 0이 되지 않고, 메인 스레드는 `ready.await()`에서 영원히 멈춘다. 작업 수가 1,000개 이상이면 `Executors.newVirtualThreadPerTaskExecutor()`를 쓴다.

> 이 틀은 복사하지 말고 직접 타이핑한다. 각 래치를 하나씩 지웠을 때 어떤 일이 생기는지 TIL에 적는다.
> 동시성 버그 재현은 확률적이다. 1회 통과는 안전의 증거가 아니므로 `@RepeatedTest(50)`으로 50회 반복한다.

### 6. 성능 측정 규칙 (M2-2, M2-4, M2-5, M2-6에서 사용)
측정값은 실행할 때마다 달라진다. 아래 규칙을 지켜야 버전 간 비교가 의미를 가진다.

1. 측정 코드는 테스트가 아니라 `main` 메서드(`lab.bank.experiment` 패키지)로 만든다. 테스트 러너의 부가 작업이 측정값에 섞이지 않게 하기 위해서다.
2. 같은 JVM 안에서 **워밍업 3회** 실행 후 버린다 (JIT 컴파일 전후 차이를 제거).
3. 이어서 **측정 5회** 실행하고 각 회차의 소요 시간을 `System.nanoTime()` 차이로 잰다.
4. 5회 중 **중앙값**(정렬 후 3번째 값)을 표에 기록한다. 최솟값·최댓값도 함께 적는다.
5. 표 위에 **JDK 버전**(`java -version` 출력 첫 줄), **CPU 코어 수**(`Runtime.getRuntime().availableProcessors()`), **OS와 버전**을 적는다.
6. 측정 중에는 IDE 인덱싱, 브라우저 영상 재생 같은 다른 부하를 끈다.

측정표 공통 머리말 예시:
```
JDK: openjdk version "21.0.8" · CPU 코어: 11 · OS: macOS 26.6 (arm64)
워밍업 3회 / 측정 5회 / 중앙값 기록
```

JIT의 죽은 코드 제거·인라이닝 때문에 마이크로벤치마크는 위 규칙으로도 왜곡될 수 있다. 정밀한 측정이 필요하면 JMH(OpenJDK Code Tools 프로젝트의 벤치마크 도구)를 쓴다. 이 Phase에서 JMH는 선택이다.

---

## 워크스페이스 만들기

```bash
cd phase-2-java-concurrency
mkdir -p workspace
rsync -a --exclude build --exclude .gradle --exclude .idea \
  ../phase-1-java-foundation/workspace/ workspace/
```
Phase 1 workspace는 수정하지 않는다. M2-7이 끝난 뒤 두 디렉터리를 비교해 무엇이 바뀌었는지 TIL에 적는다.

`workspace/settings.gradle.kts`:
```kotlin
rootProject.name = "bank-concurrency"
```

`workspace/build.gradle.kts` (Phase 1 설정에 M2-3 데드락 테스트 격리 설정을 더한 것):
```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("org.assertj:assertj-core:3.27.3")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform {
        excludeTags("deadlock-demo")      // M2-3 데드락 재현 테스트는 기본 test에서 제외
    }
    testLogging {
        events("passed", "failed", "skipped")
    }
}

// M2-3 데드락 재현 테스트만 실행: ./gradlew deadlockDemo
val deadlockDemo by tasks.registering(Test::class) {
    description = "M2-3 데드락 재현 테스트(@Tag(\"deadlock-demo\"))만 실행한다"
    group = "verification"
    testClassesDirs = sourceSets.test.get().output.classesDirs
    classpath = sourceSets.test.get().runtimeClasspath
    useJUnitPlatform {
        includeTags("deadlock-demo")
    }
}
```
확인: `./gradlew test`와 `./gradlew deadlockDemo`가 각각 `BUILD SUCCESSFUL`로 끝난다 (Gradle 8.14.3, JDK 21.0.8에서 확인).

## 주차별 계획
| 주 | 미션 | 개념 학습 범위 |
|---|---|---|
| 1주 (10~14h) | M2-1, M2-2, M2-3 | 이 README 1~6절 · 『자바 병렬 프로그래밍』 2장, 3장 3.1~3.2절, 10장 10.1절 |
| 2주 (12~15h) | M2-4, M2-5, M2-6 | 『자바 병렬 프로그래밍』 13장 13.1~13.3절, 15장 15.1~15.3절, 6장 6.2절, 7장 7.1절 · `ReentrantLock` Javadoc · JEP 444 "Description" 절 · JEP 491 "Description" 절 |
| 3주 (8~12h) | M2-7 | `ConcurrentHashMap`·`CompletableFuture` Javadoc · 이 README 5절 동시성 테스트 틀 |

M2-6의 선행은 M2-4이므로 2주차 안에서 M2-4를 먼저 끝낸다. M2-7(8~12h)과 다른 미션을 같은 주에 두면 그 주가 주 15h를 넘는다.

## 미션

| 미션 | 주제 | 예상 시간 |
|---|---|---|
| [M2-1](missions/M2-1-race-condition.md) | Race condition 재현 | 3~4h |
| [M2-2](missions/M2-2-synchronized.md) | `synchronized`로 계좌 보호 | 3~4h |
| [M2-3](missions/M2-3-deadlock.md) | 이체와 데드락 | 4~6h |
| [M2-4](missions/M2-4-reentrant-lock.md) | `ReentrantLock`, `tryLock`, 타임아웃 | 4~5h |
| [M2-5](missions/M2-5-cas.md) | Atomic/CAS와 낙관적 동시성 | 4~5h |
| [M2-6](missions/M2-6-executor-virtual-threads.md) | `ExecutorService`와 가상 스레드 | 4~5h |
| [M2-7](missions/M2-7-transfer-engine.md) | [종합] 스레드 안전한 이체 엔진 | 8~12h |

## 읽을거리
- 『자바 병렬 프로그래밍』(Brian Goetz 외) 2장 스레드 안전성, 3장 객체 공유, 6장 작업 실행, 7장 중단 및 종료, 10장 활동성 위험, 13장 명시적인 락, 15장 단일 연산 변수와 넌블로킹 동기화
- JLS 17.4.5 Happens-before Order, 17.5 final Field Semantics, 17.7 Non-Atomic Treatment of double and long
- `java.util.concurrent.locks.Lock` Javadoc — "Memory Synchronization" 절
- JEP 444 Virtual Threads (JDK 21), JEP 491 Synchronize Virtual Threads without Pinning (JDK 24)

## 완료 기준
- [ ] M2-1의 `UnsafeCounter` 재현 테스트가 lost update를 잡아내고, 10회 실행 결과표가 TIL에 있다
- [ ] `./gradlew deadlockDemo`가 데드락을 감지해 통과하고, `jstack` 출력의 `Found one Java-level deadlock:` 절을 해석한 TIL이 있다
- [ ] 계좌 출금을 `synchronized` / `ReentrantLock` / CAS로 구현한 3버전이 M2-2 2단계 테스트(성공 33건, 실패 17건, 잔액 1,000원)를 모두 통과한다
- [ ] M2-2, M2-4, M2-5, M2-6 측정표 머리말에 JDK 버전·CPU 코어 수·OS가 적혀 있다
- [ ] `./gradlew test`가 통과하고, M2-7의 반복 지정 시나리오가 `@RepeatedTest(100)`에서 100회 모두 통과한다
- [ ] 프로젝트 전체에서 `catch (InterruptedException e) {}`처럼 인터럽트를 삼킨 곳이 0곳이다 (`grep -rn "InterruptedException" src`로 확인)
- [ ] [레벨 진단](../docs/self-check.md) Phase 2 항목을 말로 설명할 수 있다
