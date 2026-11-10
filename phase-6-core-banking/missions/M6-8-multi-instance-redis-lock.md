# M6-8 다중 인스턴스와 Redis 분산락

> 가이드 수준: L3 · 예상 시간: 5~7h · 선행: M6-4

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 애플리케이션 2대(포트 8081, 8082)를 같은 MySQL에 붙여 실행하고, JVM 락으로 보호한 잔액 차감 1,000건이 lost update를 내는 것을 실험 기록으로 보여준다.
- Redisson 락의 만료 시간(lease)이 지나거나 프로세스가 멈춘 동안 다른 인스턴스가 같은 락을 잡아 잔액이 틀어지는 상황을 재현하고, DB 쪽 조건부 쓰기가 그 쓰기를 거부하는 것을 보여준다.
- JVM 락, DB 락, Redis 락, Redis 락 + DB 조건부 쓰기 4가지를 정확성·장애 시 동작·처리량 열이 정해진 비교표로 정리하고, 이체 API에 쓸 전략을 측정값을 근거로 고른다.
- M6-3·M6-4의 이체 API가 인스턴스 2대에서도 INV-1~INV-3과 1일 한도·비밀번호 오류 횟수 규칙을 지키는 것을 테스트로 보여준다.

## 배경
서버 1대에서 통과한 동시성 테스트는 서버가 2대가 되는 순간 근거를 잃을 수 있다. `synchronized`, `ReentrantLock`, `ConcurrentHashMap` 캐시는 JVM마다 따로 존재하므로, 두 인스턴스가 같은 계좌를 동시에 수정하는 것을 막지 못한다.
Redis 분산락은 락을 JVM 밖으로 옮기지만, 만료 시간이 있는 락은 "락을 잡고 있다고 믿는 프로세스가 2개"인 순간을 만든다(README 8절). 이 순간에 돈이 걸린 쓰기가 일어나면 잔액이 틀어진다.
M6-4에서 단일 인스턴스 기준 동시성 테스트를 통과했다. 이 미션은 같은 코드를 인스턴스 2대에서 다시 검증하고, 분산락을 어디에 쓰고 어디에 쓰지 말아야 하는지를 측정으로 정한다.

## 요구사항

### 1. 실행 환경
1. README "워크스페이스 만들기" 2절의 `compose.yaml`로 MySQL 8.4와 Redis 8을 띄운다.
2. 의존성 `org.redisson:redisson-spring-boot-starter:4.8.0`을 추가한다. 이 버전은 Spring Boot 4.1용 `redisson-spring-data-41` 모듈을 끌어온다(2026-11-10 Maven Central 확인). 연결 설정은 `spring.data.redis.host`, `spring.data.redis.port`로 한다.
3. 인스턴스 2대 실행:

```bash
cd phase-6-core-banking/workspace/corebank
./gradlew bootJar
java -jar build/libs/corebank-0.0.1-SNAPSHOT.jar --server.port=8081 --spring.profiles.active=experiment > /tmp/corebank-8081.log 2>&1 &
java -jar build/libs/corebank-0.0.1-SNAPSHOT.jar --server.port=8082 --spring.profiles.active=experiment > /tmp/corebank-8082.log 2>&1 &
curl -s localhost:8081/actuator/health; curl -s localhost:8082/actuator/health   # 둘 다 {"status":"UP"}
```

(jar 파일 이름은 `build.gradle.kts`의 `version`에 따라 다르다. `ls build/libs`로 확인한다.)

### 2. JVM 상태 목록
지금까지 작성한 `lab.corebank` 코드에서 인스턴스마다 따로 존재하는 상태를 모두 찾아 `workspace/docs/distributed-lock-report.md`의 표로 적는다. 열: `위치(클래스.필드) | 종류(synchronized, Lock, Map, static 필드, 로컬 캐시, @Scheduled 등) | 인스턴스 2대에서 깨지는가 | 깨진다면 재현 방법 | 조치`.
최소 다음을 검색한 결과를 표에 포함한다: `synchronized`, `ReentrantLock`, `ConcurrentHashMap`, `static` 가변 필드, `@Cacheable`, `@Scheduled`. 검색 결과가 0건인 항목도 "0건"으로 적는다.

### 3. 실험용 엔드포인트 (`experiment` 프로파일에서만 등록)
1. Flyway 위치를 `experiment` 프로파일에서만 `classpath:db/migration,classpath:db/experiment`로 늘리고, `db/experiment`에 `experiment_account`(`id`, `balance`, `version`) 테이블을 만든다. 분개·멱등 처리는 하지 않는 실험 전용 테이블이다.
2. `POST /api/experiments/accounts/{id}/decrement?strategy={jvm|db|redis|redis-fenced}&leaseMs={선택}&holdMs={선택}`: 잔액을 1 줄인다. 모든 전략에서 쓰기 방식은 "SELECT로 잔액을 읽고 → Java에서 1을 빼고 → UPDATE로 쓴다"이다. `holdMs`가 있으면 읽은 뒤 쓰기 전에 그 시간만큼 멈춘다.

| 전략 | 락 | 쓰기 |
|---|---|---|
| `jvm` | 계좌 ID별 `ReentrantLock` (JVM 메모리) | `UPDATE ... SET balance = ? WHERE id = ?` |
| `db` | `SELECT ... FOR UPDATE` | 같음 |
| `redis` | Redisson `RLock` 키 `lock:experiment-account:{id}`, 대기 2초. `leaseMs`가 있으면 그 값을 만료 시간으로, 없으면 Redisson watchdog | 같음 |
| `redis-fenced` | `redis`와 같음 | `UPDATE ... SET balance = ?, version = version + 1 WHERE id = ? AND version = ?(읽은 값)`, 바뀐 행이 0이면 409 `STALE_WRITE` |

3. 락을 2초 안에 얻지 못하면 409 `LOCK_TIMEOUT`, Redis에 연결할 수 없으면 503 `LOCK_UNAVAILABLE`로 응답하고 잔액을 바꾸지 않는다. 락 없이 진행하지 않는다.
4. `GET /api/experiments/accounts/{id}`: 잔액과 `version`.

### 4. 실험 (결과는 `distributed-lock-report.md`에 기록)
각 실험 전에 `experiment_account` 잔액을 100,000으로 초기화한다. 동시 요청은 아래 명령처럼 두 포트에 반씩 보낸다.

```bash
send() { # $1=port $2=strategy $3=count $4=extra query
  seq 1 "$3" | xargs -P 50 -I{} curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST "localhost:$1/api/experiments/accounts/1/decrement?strategy=$2$4"
}
( send 8081 jvm 500 "" > /tmp/r8081.txt & send 8082 jvm 500 "" > /tmp/r8082.txt & wait )
sort /tmp/r8081.txt /tmp/r8082.txt | uniq -c      # 응답 코드별 개수
curl -s localhost:8081/api/experiments/accounts/1
```

| 실험 | 내용 | 기록할 값 |
|---|---|---|
| E1 | `jvm`: 인스턴스 1대(8081에 1,000건) vs 2대(500건씩) | 최종 잔액, 200 응답 수, lost update 수 = 최종 잔액 − (100,000 − 200 응답 수) |
| E2 | `db`, `redis`, `redis-fenced`: 2대에 500건씩 | 같은 값 |
| E3 | `redis`와 `redis-fenced`, `leaseMs=1000&holdMs=1500`: 2대에 20건씩 | 같은 값, `STALE_WRITE` 수 |
| E4 | `redis`(watchdog), `holdMs=40000`인 요청 1건을 8081로 보내고 그 요청이 락을 잡은 직후 `kill -STOP <8081 pid>`, 35초 뒤 8082로 일반 요청 1건, 그다음 `kill -CONT <8081 pid>`. 같은 순서를 `redis-fenced`로 반복 | 두 요청의 응답 코드, 최종 잔액, `version` |
| E5 | `redis` 부하(2대 500건씩) 도중 `docker compose stop redis` | 응답 코드별 수, 최종 잔액 == 100,000 − 200 응답 수 인지 |

- E4는 Redisson watchdog이 락을 연장하는 스레드도 `kill -STOP`으로 함께 멈춘다는 점을 이용한다. Redisson의 기본 `lockWatchdogTimeout`은 30초다(Redisson 문서 "Lock" 절). 35초 정지면 락이 만료된다. watchdog은 `lockWatchdogTimeout / 3`(10초)마다 만료 시간을 다시 30초로 늘리므로, 정지 직전 마지막 연장 시점에 따라 락은 정지 후 20~30초 사이에 풀린다.
- E4에서 재개된 8081 요청이 쓰기 후 `unlock()`을 부르면, 락이 이미 만료돼 다른 스레드 소유이므로 Redisson은 `IllegalMonitorStateException`을 던진다. 이 경우 응답 코드를 무엇으로 할지(쓰기는 이미 커밋됨) 정하고 보고서에 적는다.

### 5. 이체 API 검증 (인스턴스 2대)
1. 자동 테스트: 한 테스트 JVM에서 `SpringApplicationBuilder`로 애플리케이션 컨텍스트 2개를 서로 다른 포트로 띄우고(같은 Testcontainers MySQL·Redis), 아래를 확인한다. 이 방식은 `static` 필드를 두 컨텍스트가 공유하므로, 2절 표에 `static` 가변 상태가 있다면 1절 3번의 프로세스 2개로도 같은 확인을 하고 결과를 기록한다.
   - 같은 고객·같은 `Idempotency-Key` 이체 20건을 두 컨텍스트에 10건씩 동시에: 분개 1개
   - 계좌 20개(각 1,000,000원)에 랜덤 당행이체 2,000건(시드 `20261110`)을 두 컨텍스트에 반씩: M6-4 4절의 INV-1, INV-2, L1~L5 (L1의 총액은 20,000,000원)
   - 누적 0원 계좌에 600,000원 이체 10건을 두 컨텍스트에 5건씩 동시에: 성공 8건
   - 틀린 비밀번호 8건을 두 컨텍스트에 4건씩 동시에: 오류 횟수 5, `PASSWORD_LOCKED` 이력 1행
2. 이체 API의 계좌 보호 전략을 설정값 `corebank.transfer.lock=db|redis-db`로 고를 수 있게 한다. `db`는 M6-3에서 고른 방식 그대로, `redis-db`는 출금·입금계좌의 Redisson 락을 계좌 ID 오름차순으로 잡은 뒤 M6-3 방식을 그대로 수행한다.
3. 처리량 측정: 계좌 10개 사이의 랜덤 이체 2,000건을 두 인스턴스에 반씩, 동시 요청 64개로 보낸다. 부하 도구는 학습자가 Java `HttpClient`로 작성한다(k6는 Phase 8에서 쓴다). 워밍업 3회 후 5회 측정, 중앙값 기록. 표 위에 JDK 버전, CPU 코어 수, OS를 적는다. 열: `전략 | 실행 | 소요 시간(ms) | TPS | p99(ms) | 5xx 수 | 409 수`.

### 6. 비교표와 결정 (`distributed-lock-report.md`)
아래 열을 그대로 쓴다. 각 칸은 4절·5절에서 측정하거나 재현한 결과로 채우고, 재현하지 않은 칸은 "재현 안 함 + 근거 문헌"으로 적는다.

| 전략 | 인스턴스 2대 정확성 (E1·E2) | 락 만료 시 (E3) | 프로세스 정지 시 (E4) | Redis 중단 시 (E5) | 정확성을 최종 보장하는 장치 | TPS 중앙값 | p99 | 필요한 인프라 |
|---|---|---|---|---|---|---|---|---|
| `jvm` | | | | | | | | |
| `db` | | | | | | | | |
| `redis` | | | | | | | | |
| `redis-fenced` | | | | | | | | |

비교표 아래에 이체 API(`corebank.transfer.lock`)의 기본값으로 무엇을 고르는지 한 문단으로 쓰고, 근거로 표의 칸을 최소 3개 인용한다. Kleppmann의 "How to do distributed locking" 글에서 펜싱 토큰을 설명한 절과 이 미션의 `version` 컬럼이 어떻게 대응하는지 2~4문장으로 적는다.

## 직접 작성할 테스트 시나리오
`workspace/docs/test-scenarios/M6-8.md`에 표(번호 / Given / When / Then)를 쓰고 리뷰를 받은 뒤 구현한다. 4절 실험 E1~E5는 수동 실험이므로 표에 넣지 않고 보고서에 기록한다. 표에는 자동 테스트만 넣는다.

반드시 포함할 경우 (최소 10개 행):
1. 5절 1번의 4가지 경우 (4개 행), 각 행의 Then에 분개 수·잔액 합계·오류 횟수 등 구체 값
2. `corebank.transfer.lock=redis-db`로 1번 4가지 중 랜덤 이체 경우를 다시 실행
3. `redis-db`에서 Redis 컨테이너를 멈춘 뒤 이체 요청: 503 `LOCK_UNAVAILABLE`, 잔액·분개·한도 누적 변화 없음
4. 실험 엔드포인트 `redis-fenced`에서 읽은 `version`이 그사이 바뀐 경우: 409 `STALE_WRITE`, 잔액 불변
5. 실험 엔드포인트 락 대기 2초 초과: 409 `LOCK_TIMEOUT`
6. `experiment` 프로파일이 아닐 때 `/api/experiments/**`가 404
7. A→B 이체와 B→A 이체를 `redis-db`로 동시에 100쌍: 데드락·락 대기 타임아웃 0건, INV-2 성립

## 제약
- Redis 락을 얻지 못했거나 Redis가 응답하지 않을 때 락 없이 이체를 진행하는 "대체 경로"를 만들지 않는다 — 장애 순간에 동시성 보호가 사라진다.
- `redis-db` 전략에서도 M6-3의 DB 쪽 보호(비관적 락, 낙관적 락, 조건부 UPDATE 중 고른 것)를 제거하지 않는다. 제거한 버전을 측정하고 싶다면 실험 엔드포인트에서만 한다.
- 실험 엔드포인트와 `experiment_account` 테이블은 `experiment` 프로파일 밖에서 만들어지지 않는다.
- `kill -STOP`, `docker compose stop` 실험은 로컬 환경에서만 한다. 실험 후 `kill -CONT`, `docker compose start redis`로 되돌린다.

## 힌트
<details>
<summary>힌트 1: 만료 시간을 줄 때와 주지 않을 때</summary>

Redisson `RLock`의 `tryLock(long waitTime, long leaseTime, TimeUnit unit)`과 `tryLock(long waitTime, TimeUnit unit)`의 Javadoc을 비교한다. 어느 쪽이 watchdog으로 락을 연장하는가? 계좌 2개를 한 번에 잠그는 방법은 Redisson 문서 "Locks and synchronizers"의 MultiLock 절에 있다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 M6-8 시나리오 표의 모든 행에 대응하는 테스트가 통과한다
- [ ] `workspace/docs/distributed-lock-report.md`에 2절 JVM 상태 표, 4절 E1~E5 결과(응답 코드별 수, 최종 잔액, 사용한 명령), 5절 3번 측정표(전략 2개 × 8회 실행 + 중앙값 행), 6절 비교표와 결정 문단이 있다
- [ ] E1에서 인스턴스 2대 `jvm`의 lost update 수가 0보다 크고, E2에서 `db`, `redis`, `redis-fenced`의 lost update 수가 0인 결과가 기록되어 있다 (E1이 0이 나오면 `holdMs=5`를 주고 다시 실행해 기록한다)
- [ ] E4에서 `redis`는 잔액이 틀어지고 `redis-fenced`는 8081의 늦은 쓰기가 409 `STALE_WRITE`로 거부된 기록이 있다
- [ ] PR 본문에 `workspace/docs/test-scenarios/M6-8.md` 표가 붙어 있다

## 생각해볼 질문
1. 이체의 정합성을 DB가 끝까지 보장한다면 Redis 락은 무엇을 위해 남겨두는가? 5절 3번 측정에서 `redis-db`가 `db`보다 TPS가 낮았다면 Redis 락을 쓸 이유가 남는가?
2. E4에서 펜싱이 동작한 것은 저장소(MySQL)가 `version`을 검사했기 때문이다. 쓰기 대상이 MySQL이 아니라 `fake-kftc` 같은 외부 시스템이라면 펜싱 토큰을 어떻게 전달하고 검사하게 할 수 있는가?
3. Redis를 Sentinel이나 Cluster로 구성하면 E5의 "Redis 중단"은 줄어든다. 그래도 Kleppmann 글이 Redlock에 대해 지적한 문제(시계, 프로세스 정지)는 남는가?
4. Phase 7의 매칭 엔진은 종목별 단일 스레드로 동시성을 피한다(M7-4). 인스턴스가 2대가 되면 "종목 A는 어느 인스턴스가 처리하는가"를 정해야 한다. 이 결정에 분산락, Kafka 파티션, DB 중 무엇을 쓰겠는가?
