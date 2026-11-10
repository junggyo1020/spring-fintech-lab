# M6-7 타행이체 시뮬레이션

> 가이드 수준: L3 · 예상 시간: 7~9h · 선행: M6-3, M6-4

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 가짜 대외기관 서버(`fake-kftc`)가 처리 후 응답 전에 멈추는 경우 이체를 `UNKNOWN`으로 두고, 조회 API로 `SUCCEEDED` 또는 `FAILED`로 확정하는 흐름을 통합 테스트로 보여준다.
- 대외기관이 처리하지 않은 것이 확인된 이체만 반대 분개로 보상하고, 그 외에는 돈이 `타행이체미정산` 계정에 남는 것(INV-4)을 테스트로 보여준다.
- 랜덤 장애 모드에서 타행이체 1,000건을 보낸 뒤 당행 `SUCCEEDED` 목록과 대외기관 처리 목록이 1건도 다르지 않은 것을 대외기관 대사 결과로 보여준다.
- 대외기관 연속 실패 시 Resilience4j 서킷 브레이커가 `OPEN`이 되어 새 타행이체가 출금 전에 거절되는 것을 테스트로 보여준다.

## 배경
타행이체는 금융결제원(KFTC) 전자금융공동망을 거친다(`fintech-domain-facts` 6절). 당행 서버가 요청을 보낸 뒤 응답을 받지 못하면, 요청이 도착하지 않았는지, 처리됐는데 응답만 유실됐는지 알 수 없다(README 7절).
이때 실패로 보고 고객에게 돈을 돌려주면 상대 은행에도 돈이 들어가 이중 지급이 되고, 성공으로 보면 실제로는 안 나간 돈이 사라진다. 두 사고 모두 실제 금융 시스템에서 수작업 정정과 민원으로 이어진다.
M6-3의 이체는 한 DB 트랜잭션 안에서 끝났다. 이 미션의 이체는 DB 트랜잭션 밖의 HTTP 호출을 포함하므로, 트랜잭션 하나로 원자성을 얻을 수 없고 상태 머신과 보상으로 정합성을 지킨다.

## 요구사항

### 1. 가짜 대외기관 `fake-kftc` (별도 Spring Boot 앱)
`phase-6-core-banking/workspace/fake-kftc/`, 패키지 `lab.fakekftc`, 포트 9095(Phase 8의 Prometheus 9090과 겹치지 않게 정함), 의존성 `spring-boot-starter-webmvc`만 쓴다(README "워크스페이스 만들기" 4절). 저장소는 메모리(`ConcurrentHashMap`)다. 이 서버의 규칙은 전부 **이 미션의 규칙**이며 실제 금융결제원 전문 규격이 아니다.

| 메서드 | 경로 | 동작 |
|---|---|---|
| POST | `/clearing/transfers` | 본문 `requestId`(UUID 문자열), `toBankCode`, `toAccountNumber`, `amount`. 현재 동작 모드에 따라 응답 (아래 표) |
| GET | `/clearing/transfers/{requestId}` | 처리 기록이 있으면 200 + `result`(`SUCCEEDED` 또는 `FAILED`), 없으면 404 |
| PUT | `/admin/behavior` | 동작 모드 설정. 본문 `mode`, `RANDOM`일 때 `seed` |
| GET | `/admin/processed` | `SUCCEEDED`로 처리한 `requestId`와 금액 목록 |
| POST | `/admin/reset` | 처리 기록 삭제, 모드 `SUCCESS`로 초기화 |

| 모드 | `POST /clearing/transfers` 동작 | 처리 기록 |
|---|---|---|
| `SUCCESS` | 200 `{"result":"SUCCEEDED"}` | `SUCCEEDED` 저장 |
| `REJECT` | 422 `{"result":"FAILED","reason":"INVALID_ACCOUNT"}` | `FAILED` 저장 |
| `UNAVAILABLE` | 503, 처리하지 않음 | 없음 |
| `TIMEOUT_AFTER_PROCESS` | `SUCCEEDED` 저장 후 5초 대기하고 200 | `SUCCEEDED` 저장 |
| `TIMEOUT_BEFORE_PROCESS` | 5초 대기 후 처리하지 않고 연결 종료 | 없음 |
| `INQUIRY_TIMEOUT` | `SUCCESS`와 같음. 대신 `GET` 조회가 5초 대기 후 응답 | `SUCCEEDED` 저장 |
| `RANDOM` | 요청마다 `seed`로 만든 `Random`으로 고른다: `SUCCESS` 70%, `REJECT` 10%, `UNAVAILABLE` 10%, `TIMEOUT_AFTER_PROCESS` 5%, `TIMEOUT_BEFORE_PROCESS` 5%. 모든 응답 전에 0~500ms 균등 지연. `GET` 조회는 무작위 선택 없이 정상 응답한다 | 고른 모드대로 |

- 같은 `requestId`로 다시 POST하면 처리 기록이 있으면 다시 처리하지 않고 저장된 결과를 돌려준다(대외기관 쪽 멱등). 기록이 없으면 현재 모드로 처리한다.

### 2. 타행이체 상태와 분개 (`lab.corebank.interbank`)
상태: `REQUESTED` → `SENT` → (`SUCCEEDED` | `FAILED` | `UNKNOWN`), `UNKNOWN` → (`SUCCEEDED` | `FAILED`). 이 외의 전이는 없다. `SUCCEEDED`, `FAILED`는 최종 상태다.

| 시점 | 분개 유형 | 차변 | 대변 |
|---|---|---|---|
| 요청 접수 (`REQUESTED`) | `INTERBANK_REQUEST` | 고객예금 A | 타행이체미정산 |
| `SUCCEEDED` 확정 | `INTERBANK_SETTLE` | 타행이체미정산 | 대외결제예치금 |
| `FAILED` 확정 | `INTERBANK_COMPENSATE` | 타행이체미정산 | 고객예금 A |

요청 접수 분개는 `fintech-domain-facts` 6절의 분개다(확인일 2026-11-10). 정산·보상 분개와 `대외결제예치금` 계정은 **이 미션의 규칙**이다(실제 은행의 대외 정산 계정 처리는 은행마다 다르다).

### 3. API와 처리 흐름
`POST /api/interbank-transfers` (헤더 `X-Customer-Id`, `Idempotency-Key`, 본문 `fromAccountNumber`, `toBankCode`, `toAccountNumber`, `amount`, `password`). M6-3의 멱등 규칙과 M6-4의 검사 순서·한도·비밀번호 규칙을 그대로 적용한다(주차별 계획상 M6-4가 먼저 끝나 있다).

1. 트랜잭션 1: 검사 통과 후 출금계좌 잔액 감소, `account_transaction` `INTERBANK_OUT` 행, 요청 접수 분개, `interbank_transfer` 행(`REQUESTED`, `requestId` = 새 UUID), 1일 한도 누적을 커밋한다.
2. 트랜잭션 2: 상태를 `SENT`로 바꾸고 보낸 시각을 기록해 커밋한다.
3. DB 트랜잭션 밖에서 `fake-kftc`를 호출한다. HTTP 클라이언트는 `RestClient`(Spring Framework 7)이고 연결 타임아웃 1초, 읽기 타임아웃 3초다(이 미션의 규칙).
4. 결과별 처리:

| 호출 결과 | 상태 | 분개 | API 응답 |
|---|---|---|---|
| 200 `SUCCEEDED` | `SUCCEEDED` | 정산 | 200, `status: SUCCEEDED` |
| 422 `FAILED` | `FAILED` | 보상, 1일 한도 누적에서 금액 차감 | 422 `INTERBANK_REJECTED` |
| 연결 실패(연결 거부, 연결 타임아웃) 또는 503 | 재시도 (5절). 재시도를 모두 실패하면 `FAILED` | 보상 | 503 `CLEARING_UNAVAILABLE` |
| 읽기 타임아웃, 응답 도중 연결 끊김 | `UNKNOWN` | 없음 | 202, `status: UNKNOWN` |

5. `GET /api/interbank-transfers/{id}`: 현재 상태를 돌려준다.
6. 서킷 브레이커가 `OPEN`이면 트랜잭션 1 전에 거절한다: 503 `CLEARING_UNAVAILABLE`, 잔액·분개·한도 변화 없음.

### 4. `UNKNOWN` 해소 (이 미션의 규칙)
1. `UnknownTransferResolver`(이름은 바꿔도 된다)가 `@Scheduled(fixedDelay = 1000)`로 다음 조회 시각이 지난 `UNKNOWN` 이체를 조회한다.
2. 조회 간격: `UNKNOWN`이 된 뒤 1초, 2초, 4초, 8초, 16초, 32초, 그다음부터 60초 간격. 조회 시각과 횟수는 `interbank_transfer` 행에 저장한다(재시작해도 이어진다).
3. 조회 결과 `SUCCEEDED` → 정산 분개 후 `SUCCEEDED`. `FAILED` → 보상 분개 후 `FAILED`.
4. 조회 결과 404: 보낸 시각으로부터 60초가 지났고 404가 연속 2번이면 `FAILED`로 확정하고 보상한다. 60초 전의 404는 횟수에 넣지 않는다.
5. 조회가 타임아웃이거나 503이면 상태를 바꾸지 않는다. 조회 10회 동안 결과를 못 얻으면 `manual_review = true`로 표시하고 계속 `UNKNOWN`으로 둔다. 자동 보상하지 않는다.
6. 확정(정산 또는 보상)은 `WHERE id = ? AND status IN ('SENT', 'UNKNOWN')` 조건부 UPDATE로 하고, 바뀐 행이 1개일 때만 같은 트랜잭션에서 분개를 저장한다. 원래 요청 스레드와 resolver가 동시에 확정하려 해도 분개는 1개만 생긴다.

### 5. 재시도와 서킷 브레이커 (이 미션의 규칙)
의존성: `io.github.resilience4j:resilience4j-spring-boot4:2.4.0`과 `org.springframework.boot:spring-boot-starter-aspectj`(애노테이션 방식 `@CircuitBreaker`는 AOP 프록시로 동작한다). Resilience4j는 2.4.0부터 Spring Boot 4 모듈을 제공한다(2026-11-10 Maven Central 확인).

1. 재시도 대상: 연결 실패와 503만. 읽기 타임아웃과 422는 재시도하지 않는다. 최대 3회 재시도(첫 시도 포함 4회), 대기 200ms → 400ms → 800ms(지수 백오프, 배수 2, 지터 없음). 재시도는 Resilience4j Retry 또는 Spring Framework 7의 `@Retryable` 중 하나로 하고, 고른 것을 설계 문서에 적는다.
2. 서킷 브레이커 인스턴스 `kftcSend`(이체 요청), `kftcInquiry`(조회) 2개, 설정은 같다:

| 속성 | 값 |
|---|---|
| `slidingWindowType` | `COUNT_BASED` |
| `slidingWindowSize` | 20 |
| `minimumNumberOfCalls` | 10 |
| `failureRateThreshold` | 50 |
| `slowCallDurationThreshold` | 2초 |
| `slowCallRateThreshold` | 50 |
| `waitDurationInOpenState` | 10초 |
| `permittedNumberOfCallsInHalfOpenState` | 3 |
| 실패로 기록 | 연결 실패, 읽기 타임아웃, 503 |
| 실패로 기록하지 않음 | 422 (업무 거절은 대외기관 장애가 아니다) |

3. `OPEN` 상태에서 호출하면 Resilience4j가 `CallNotPermittedException`을 던진다. 이 예외를 3절 6번의 503으로 바꾼다.
4. 재시도와 서킷 브레이커를 함께 쓸 때 어느 쪽이 바깥에 있는지(재시도 4회가 서킷 브레이커에 1회로 기록되는지 4회로 기록되는지)를 테스트로 확인하고 설계 문서에 적는다.

### 6. 대외기관 대사
`POST /api/admin/interbank/reconcile`: `fake-kftc`의 `GET /admin/processed` 목록과 당행 `SUCCEEDED` 이체 목록을 `requestId`로 비교해, 한쪽에만 있는 건과 금액이 다른 건을 응답 본문 목록으로 돌려준다. 돈은 움직이지 않는다.

### 7. 설계 문서 `workspace/docs/interbank-design.md`
- 2절 상태 머신(Mermaid `stateDiagram-v2`)과 상태별 분개 표.
- 3절 4번 표의 각 행이 README 7절 표의 어느 경우를 커버하는지.
- 1절 모드 6개 각각에서 이체 1건의 시퀀스(Mermaid `sequenceDiagram`, 6개 그림)와 최종 상태·분개 목록.
- 4절 4번 규칙(404 두 번이면 실패)이 틀리는 경우가 있는지와, 이 시뮬레이터에서는 왜 그 경우가 생기지 않는지.

## 직접 작성할 테스트 시나리오
`workspace/docs/test-scenarios/M6-7.md`에 표(번호 / Given / When / Then)를 쓰고 리뷰를 받은 뒤 구현한다. `fake-kftc`를 쓰는 통합 테스트는 JUnit 태그 `external`을 붙이고, `fake-kftc`를 먼저 띄운 뒤 실행한다(완료 기준 참고). CI(M0-3)의 `./gradlew test`에는 `fake-kftc`가 없으므로, `corebank/build.gradle.kts`에서 기본 `test` 태스크는 `external`을 빼고 별도 태스크로만 실행한다(Gradle 9.8.2에서 동작 확인):

```kotlin
tasks.test {
    useJUnitPlatform { excludeTags("external") }
}
tasks.register<Test>("externalTest") {
    description = "fake-kftc(9095)를 먼저 띄운 뒤 실행하는 external 태그 테스트"
    group = "verification"
    testClassesDirs = sourceSets.test.get().output.classesDirs
    classpath = sourceSets.test.get().runtimeClasspath
    useJUnitPlatform { includeTags("external") }
}
```

Then에는 이체 상태, 계좌 잔액, `타행이체미정산` 잔액, 분개 유형별 개수를 쓴다.

반드시 포함할 경우 (최소 16개 행):
1. `SUCCESS`: `SUCCEEDED`, 분개 2개(요청·정산), `타행이체미정산` 0원
2. `REJECT`: `FAILED`, 분개 2개(요청·보상), 출금계좌 잔액 원래대로, 1일 한도 누적 원래대로
3. `UNAVAILABLE`: 재시도 3회(대외기관 수신 4회) 후 `FAILED`, 보상
4. `UNAVAILABLE` 2회 후 `SUCCESS`로 바뀜: 재시도로 `SUCCEEDED`
5. `TIMEOUT_AFTER_PROCESS`: API 202 `UNKNOWN`, 직후 `타행이체미정산` == 이체 금액, resolver 조회 후 `SUCCEEDED`, 보상 분개 0개
6. `TIMEOUT_BEFORE_PROCESS`: `UNKNOWN` → 60초 경과 후 404 두 번 → `FAILED`, 보상 1개
7. 60초 전의 404는 확정하지 않는 경우 (`Clock` 교체)
8. `INQUIRY_TIMEOUT` + 조회 10회 실패: `UNKNOWN` 유지, `manual_review = true`, 보상 0개
9. 같은 이체를 원래 요청 스레드와 resolver가 동시에 확정: 정산 분개 1개
10. 서킷 브레이커: `UNAVAILABLE` 모드에서 `kftcSend`에 실패가 10회 기록되어 `OPEN`이 된 뒤의 다음 요청은 `fake-kftc` 수신 없이 503, 출금 없음 (실패 10회가 요청 몇 건 만에 쌓이는지는 5절 4번에서 확인한 순서대로 적는다)
11. `OPEN` 10초 후 `HALF_OPEN`에서 3건 성공 → `CLOSED`
12. 422는 서킷 브레이커 실패율에 들어가지 않는 경우
13. 같은 `Idempotency-Key`로 타행이체 재요청: `fake-kftc` 수신 1회, 분개 그대로
14. 각 시나리오 종료 시 INV-1, INV-2, INV-4 성립
15. `RANDOM` 모드(seed 20261110) 1,000건 → 모든 `UNKNOWN`이 확정될 때까지 대기(최대 5분) → `manual_review` 0건, INV-4 성립, 대외기관 대사 결과 불일치 0건. 1건씩 순서대로 보내면 1건 평균 약 0.6초(응답 전 지연 평균 0.25초 + 타임아웃 10% × 읽기 타임아웃 3초 + 503 재시도 대기)라서 보내는 데만 약 10분이 걸린다. 동시 요청 수와 출금계좌 구성(1일 한도 M6-4에 걸리지 않게)을 정해 시나리오 표에 적는다
16. 상태가 `UNKNOWN`인 이체가 있는 계좌의 해지 요청: M6-1 T6 거부

## 제약
- `fake-kftc` 호출을 `@Transactional` 메서드 안에서 하지 않는다 — 읽기 타임아웃 3초 동안 DB 커넥션과 계좌 락을 잡고 있게 된다(Phase 5 M5-6 트랜잭션 함정).
- 읽기 타임아웃을 실패로 보고 보상하지 않는다. 보상은 대외기관이 처리하지 않았다는 근거(422, 503, 연결 실패, 4절 4번의 404 규칙)가 있을 때만 한다.
- 이미 기록한 요청 접수 분개를 수정·삭제하지 않는다. 결과는 정산 또는 보상 분개를 새로 추가해 반영한다(M6-2).
- 테스트에서 `Thread.sleep`으로 resolver를 기다리지 않는다. 조건이 될 때까지 짧은 간격으로 확인하는 대기(예: Awaitility `org.awaitility:awaitility`, 최대 대기 시간 명시)를 쓰거나 resolver 메서드를 직접 호출한다.

## 힌트
<details>
<summary>힌트 1: 타임아웃 종류 구분</summary>

`RestClient`가 던지는 `ResourceAccessException`의 원인(`getCause()`)을 연결 거부, 연결 타임아웃, 읽기 타임아웃 세 경우로 직접 발생시켜 출력해본다. JDK `HttpClient` 기반 요청 팩토리와 다른 요청 팩토리에서 원인 예외 클래스가 같은지도 확인한다. 이 구분이 3절 4번 표의 2행과 4행을 가른다.
</details>

## 완료 기준
- [ ] `cd workspace/fake-kftc && ./gradlew bootRun`으로 9095 포트에 띄운 뒤, `cd workspace/corebank && ./gradlew test externalTest`에서 M6-7 시나리오 표의 모든 행에 대응하는 테스트가 통과한다 (`fake-kftc`를 띄우지 않은 상태의 `./gradlew test`도 통과해야 한다)
- [ ] 이름에 `INV-4`가 들어간 테스트가 있고, `UNKNOWN` 상태 직후와 확정 후 두 시점에서 `타행이체미정산` 잔액 == `REQUESTED`·`SENT`·`UNKNOWN` 이체 금액 합계를 assert한다
- [ ] 시나리오 15의 결과(상태별 건수, 재시도 횟수, 서킷 브레이커 `OPEN` 횟수, 대사 불일치 수 0)가 `workspace/docs/interbank-design.md` 부록에 표로 있다
- [ ] `curl -s localhost:8080/actuator/health`에 서킷 브레이커 상태가 보이도록 설정했거나, 보이지 않는다면 Resilience4j 상태를 확인한 다른 방법이 설계 문서에 있다
- [ ] PR 본문에 `workspace/docs/test-scenarios/M6-7.md` 표가 붙어 있다

## 생각해볼 질문
1. 읽기 타임아웃 3초를 10초로 늘리면 `UNKNOWN`은 줄어든다. 대신 무엇이 늘어나는가? 사용자 응답 시간과 서버 스레드 점유로 답한다.
2. `fake-kftc`가 같은 `requestId`를 멱등 처리하지 않는다면, 3절 4번의 503 재시도는 안전한가? 읽기 타임아웃 뒤 재시도는?
3. 서킷 브레이커가 `OPEN`일 때 출금 전에 거절하는 설계와, 출금은 하고 `REQUESTED`로 쌓아뒀다가 `CLOSED`가 되면 보내는 설계를 고객 경험과 INV-4 관점에서 비교한다.
4. Phase 8의 Saga는 서비스 사이의 "보상 트랜잭션"을 다룬다. 이 미션의 보상 분개는 Saga의 보상 단계와 무엇이 같은가? 보상 자체가 실패하면 어떻게 하는가?
