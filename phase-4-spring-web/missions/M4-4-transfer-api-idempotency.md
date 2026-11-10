# M4-4 이체 API와 `Idempotency-Key`

> 가이드 수준: L2 · 예상 시간: 5~7h · 선행: M4-3

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 같은 `Idempotency-Key`와 같은 본문으로 `POST /transfers`를 2번 보내면 출금이 1번만 일어나고 두 응답의 상태 코드·본문이 같음을 테스트로 보여준다.
- 키 누락(400), 형식 오류(400), 다른 본문 재사용(422), 처리 중 재요청(409)을 각각 재현하는 테스트를 작성한다.
- 같은 키로 스레드 10개가 동시에 요청해도 이체가 1건만 실행됨을 잔액과 거래내역 건수로 보여준다.
- 멱등 키 보관 기간(24시간) 경계를 `Clock`을 바꿔 가며 테스트한다.

## 배경
모바일 앱이 이체 요청을 보낸 뒤 지하철에서 응답을 못 받으면, 앱은 이체가 됐는지 모른다. 사용자가 "다시 시도"를 누르면 이중 출금이 되고, 앱이 재시도를 막으면 이체가 누락됐는지 확인할 방법이 없다.
그래서 결제·이체 API는 클라이언트가 요청마다 고유 키를 보내고, 서버가 그 키로 첫 결과를 기억했다가 재시도에 같은 결과를 돌려주는 방식을 쓴다.
M2-7의 `TransferEngine`은 같은 `requestId`를 두 번 실행하지 않는 것까지 보장했다. 이 미션은 그 위에 HTTP 계약(같은 응답 재전송, 다른 본문 거절, 처리 중 충돌)을 올리고, M4-3의 오류 형식을 그대로 쓴다.

## 요구사항

### 1. 엔드포인트

| 메서드·경로 | 요청 | 성공 응답 |
|---|---|---|
| `POST /transfers` | 헤더 `Idempotency-Key`, 본문 `TransferRequest` | `201`, `Location: /transfers/{transferId}`, 본문 `TransferResponse` |
| `GET /transfers/{transferId}` | 없음 | `200`, `TransferResponse` (성공한 이체만 조회된다) |

```json
// TransferRequest
{"fromAccount": "110-0000-0001", "toAccount": "110-0000-0002",
 "money": {"amount": "30000", "currency": "KRW"}, "memo": "월세"}

// TransferResponse
{"transferId": "UUID 문자열", "fromAccount": "110-0000-0001", "toAccount": "110-0000-0002",
 "money": {"amount": "30000", "currency": "KRW"}, "memo": "월세",
 "fromBalanceAfter": {"amount": "70000", "currency": "KRW"},
 "executedAt": "2026-11-10T14:30:00"}
```

- `fromAccount`, `toAccount`: `@NotNull` + `@AccountNumberFormat`. `money`: `@NotNull` + `@Valid`(M4-2의 `@ValidMoney`). `memo`: 생략 가능, `@Size(max = 50)`.
- 컨트롤러는 M2-7의 `TransferEngine#transfer(TransferCommand)`를 호출한다. `TransferCommand`의 `requestId`에는 멱등 키를 처음 등록할 때 새로 만든 UUID를 넣고, 같은 값을 `transferId`로 쓴다. 멱등 키 자체를 `requestId`로 넣으면 24시간 만료 후 같은 키의 새 요청(시나리오 24)이 엔진의 `requestId` 멱등 처리에 막혀 실행되지 않는다. M2-7의 `TransferResult(requestId, outTransactionId, inTransactionId, fromBalanceAfter, toBalanceAfter)`에서 `transferId` = `requestId`, `fromBalanceAfter`는 그대로 쓰고, `executedAt`은 `outTransactionId` 거래의 `occurredAt`이다. `toBalanceAfter`(받는 사람의 잔액)는 응답에 넣지 않는다.
- 1일 한도는 M3-6의 `TransferProperties`(`lab.transfer.daily-limit`) 값을 쓴다. 테스트는 `@SpringBootTest(properties = "lab.transfer.daily-limit=5000000")`로 고정한다.
- 없는 `transferId`(형식이 UUID가 아닌 문자열 포함)를 조회하면 404 `TRANSFER_NOT_FOUND`.

### 2. `Idempotency-Key` 헤더 규칙
IETF 드래프트 draft-ietf-httpapi-idempotency-key-header-08(2026-10-22, RFC 아님)은 값을 Structured Field String(큰따옴표로 감싼 문자열, 예: `Idempotency-Key: "8e03978e-40d5-43e8-bc93-6894a57f9324"`)으로 정의한다. curl 사용자는 따옴표 없이 보내는 경우가 많으므로 이 레포는 두 형태를 모두 받는다.

| 단계 | 규칙 | 실패 시 |
|---|---|---|
| 1. 존재 | 헤더가 없으면 실패 | 400 `IDEMPOTENCY_KEY_MISSING` |
| 2. 따옴표 제거 | 값의 맨 앞과 맨 뒤가 모두 `"`이면 한 쌍만 제거. 한쪽에만 있으면 제거하지 않는다 | — |
| 3. 형식 | 정규식 `^[A-Za-z0-9_-]{1,64}$` (UUID 36자 권장) | 400 `IDEMPOTENCY_KEY_INVALID` |

- 헤더 검사는 본문 검사보다 먼저다. 헤더도 없고 본문도 틀리면 `IDEMPOTENCY_KEY_MISSING`이다.
- 키는 대소문자를 구분한다. `abc`와 `ABC`는 다른 키다.
- 키의 범위는 이 미션에서 서버 전체다. M4-7에서 (사용자, 키) 쌍으로 바꾼다.

### 3. 같은 요청 판정 (fingerprint)
본문을 파싱한 뒤 아래 4개 값이 모두 같으면 "같은 본문"이다. 원본 JSON 문자열을 비교하지 않는다(공백·필드 순서가 달라도 같은 요청).
- `fromAccount`, `toAccount` (문자열 그대로)
- `money` (`Money#equals` 기준: USD `"1000"`과 `"1000.00"`은 같다)
- `memo` (`null`·생략·`""`은 모두 `""`로 본다)

### 4. 처리 흐름과 저장 규칙

```
헤더 검사 → 본문 검증(@Valid) → 저장소에서 키 조회
  ├ 없음            → IN_PROGRESS(fingerprint)로 원자적 등록 → 이체 실행 → 결과 저장(COMPLETED)
  ├ fingerprint 다름 → 422 IDEMPOTENCY_KEY_CONFLICT  (상태와 무관하게 먼저 검사)
  ├ IN_PROGRESS     → 409 IDEMPOTENCY_REQUEST_IN_PROGRESS + Retry-After: 1
  └ COMPLETED       → 저장된 상태 코드·본문·Location 그대로 + Idempotent-Replayed: true
```

| 이체 실행 결과 | 저장 여부 | 같은 키 재요청 시 |
|---|---|---|
| 201 성공 | 저장 | 201, 같은 본문(같은 `transferId`) |
| 400 `SAME_ACCOUNT_TRANSFER`, 404 `ACCOUNT_NOT_FOUND`, 409 `ACCOUNT_NOT_ACTIVE`, 422 (`INSUFFICIENT_BALANCE`, `CURRENCY_MISMATCH`, `DAILY_TRANSFER_LIMIT_EXCEEDED`) | 저장 | 같은 상태·같은 `ProblemDetail`. 그 사이 입금으로 잔액이 생겨도 다시 실행하지 않는다 |
| 503 `LOCK_ACQUISITION_TIMEOUT`, 500 | 저장하지 않고 키 삭제 | 새 요청으로 실행 |
| 헤더·본문 검증 실패 (등록 전) | 등록 자체를 안 함 | 새 요청으로 처리 |

- `Idempotent-Replayed: true` 응답 헤더는 이 레포의 규칙이다(드래프트에 없음). 첫 응답에는 이 헤더가 없다.
- 보관 기간: `COMPLETED` 시각 + 24시간. `now >= 완료 시각 + 24h`이면 만료로 보고 새 요청으로 처리한다. 만료 항목은 조회할 때 지운다(별도 스케줄러 없음). 시각은 `Clock` 빈에서 얻는다.
- 같은 계좌 이체(`fromAccount` = `toAccount`)는 컨트롤러에서 검사하지 않는다. M2-7 엔진이 `SameAccountTransferException`을 던지고 M4-3 표대로 400이 된다.
- M2-7 엔진도 `requestId`별 멱등 처리를 한다. 이 미션은 `requestId`에 매번 새 UUID를 넣으므로 엔진의 멱등 처리는 HTTP 계층 저장소가 놓친 경우의 2차 방어선이 된다.

### 5. 저장소 (핵심 시그니처만 제공)

```java
public interface IdempotencyStore {
    // 키가 없으면 IN_PROGRESS로 등록하고 empty 반환, 있으면 기존 항목 반환 (원자적)
    Optional<IdempotencyRecord> registerIfAbsent(String key, Object fingerprint, Instant now);
    void complete(String key, StoredResponse response, Instant completedAt);
    void remove(String key);
}
```

`IdempotencyRecord`, `StoredResponse`의 필드는 직접 설계한다. 메모리 구현은 `ConcurrentHashMap`을 쓴다.

## 테스트 시나리오
`@SpringBootTest` + `@AutoConfigureMockMvc`, 1일 한도 5,000,000원, `Clock`은 테스트에서 바꿀 수 있는 빈으로 교체(시작 시각 `2026-11-10T14:30:00+09:00`). `A`·`B`는 테스트마다 새로 만든 KRW 계좌, `K1`·`K2`는 서로 다른 UUID다. 본문 `T` = `{"fromAccount":A,"toAccount":B,"money":{"amount":"30000","currency":"KRW"},"memo":"월세"}`.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | `A` 100,000, `B` 0 | `POST /transfers`, `Idempotency-Key: K1`, 본문 `T` | `201`, `Location` = `/transfers/` + `$.transferId`, `$.fromBalanceAfter.amount` = `"70000"`, `Idempotent-Replayed` 헤더 없음. `A` 잔액 `"70000"`, `B` 잔액 `"30000"` |
| 2 | 1번 직후 | 같은 키 `K1`, 같은 본문 `T` | `201`, `$.transferId`가 1번과 같음, 본문 전체가 1번과 같음, `Idempotent-Replayed: true`. `A` 잔액 `"70000"` 그대로, `A` 거래내역 `TRANSFER_OUT` 1건 |
| 3 | 1번 직후 | `K1`, 본문 `T`에서 공백·필드 순서만 바꾼 JSON | 2번과 같음 (같은 요청으로 판정) |
| 4 | 1번 직후 | `K1`, 본문 `T`에서 `amount`만 `"30001"` | `422`, `$.code` = `"IDEMPOTENCY_KEY_CONFLICT"`, `A` 잔액 `"70000"` 그대로 |
| 5 | 1번 직후 | `K1`, 본문 `T`에서 `memo`만 `"관리비"` | `422`, `$.code` = `"IDEMPOTENCY_KEY_CONFLICT"` |
| 6 | 1번 직후 | `K2`, 본문 `T` | `201`, 새 `transferId`, `A` 잔액 `"40000"` |
| 7 | 없음 | 헤더 없이 본문 `T` | `400`, `$.code` = `"IDEMPOTENCY_KEY_MISSING"` |
| 8 | 없음 | 헤더 없이 본문 `{}` | `400`, `$.code` = `"IDEMPOTENCY_KEY_MISSING"` (헤더 검사가 먼저) |
| 9 | 없음 | `Idempotency-Key:` (빈 값) | `400`, `$.code` = `"IDEMPOTENCY_KEY_INVALID"` |
| 10 | 없음 | 키 65자 (`a` × 65) | `400`, `$.code` = `"IDEMPOTENCY_KEY_INVALID"` |
| 11 | `A` 100,000 | 키 64자 (`a` × 64), 본문 `T` | `201` |
| 12 | 없음 | 키 `abc def` (공백 포함) | `400`, `$.code` = `"IDEMPOTENCY_KEY_INVALID"` |
| 13 | `A` 100,000 | 키 `"K1"` (큰따옴표 포함) → 이어서 키 `K1` (따옴표 없음), 본문 둘 다 `T` | 첫 요청 `201`, 두 번째 `201` + `Idempotent-Replayed: true` (같은 키) |
| 14 | 없음 | 키 `"abc` (앞 따옴표만) | `400`, `$.code` = `"IDEMPOTENCY_KEY_INVALID"` |
| 15 | `A` 10,000 | `K1`, 본문 `T` (30,000) | `422`, `$.code` = `"INSUFFICIENT_BALANCE"` |
| 16 | 15번 후 `A`에 100,000 입금 | `K1`, 본문 `T` | `422`, `$.code` = `"INSUFFICIENT_BALANCE"`, `Idempotent-Replayed: true`, `A` 잔액 `"110000"` 그대로 |
| 17 | `A` 100,000 | `K1`, `toAccount` = `A` (같은 계좌) | `400`, `$.code` = `"SAME_ACCOUNT_TRANSFER"` |
| 18 | `A` 100,000 | `K1`, `toAccount` = `110-9999-0000` (없는 계좌) | `404`, `$.code` = `"ACCOUNT_NOT_FOUND"`, `A` 잔액 `"100000"` |
| 19 | `A` 10,000,000 | `K1`, 5,000,000 → 이어서 `K2`, 1 | 첫 요청 `201`, 두 번째 `422` `$.code` = `"DAILY_TRANSFER_LIMIT_EXCEEDED"`, `A` 잔액 `"5000000"` |
| 20 | `A` 100,000, `TransferEngine`을 `CountDownLatch`에서 멈추는 테스트용 빈으로 감쌈 | 스레드 1: `K1` 본문 `T` (멈춤) → 스레드 2: `K1` 본문 `T` → 래치 해제 → 스레드 3: `K1` 본문 `T` | 스레드 2: `409`, `$.code` = `"IDEMPOTENCY_REQUEST_IN_PROGRESS"`, `Retry-After: 1`. 스레드 1: `201`. 스레드 3: `201` + `Idempotent-Replayed: true`, `transferId` = 스레드 1과 같음 |
| 21 | 20번과 같이 멈춤 | 스레드 1: `K1` 본문 `T` (멈춤) → 스레드 2: `K1`, `amount` `"1"` | 스레드 2: `422` `IDEMPOTENCY_KEY_CONFLICT` (fingerprint 검사가 처리 중 검사보다 먼저) |
| 22 | `A` 100,000, 래치 없음 | 스레드 10개가 동시에 `K1` 본문 `T` | 모든 응답이 `201` 또는 `409`, `201` ≥ 1개, `201` 응답의 `transferId`가 모두 같음, `A` 잔액 `"70000"`, `A`의 `TRANSFER_OUT` 1건 |
| 23 | 1번 완료 후 `Clock`을 23시간 59분 59초 앞으로 | `K1`, 본문 `T` | `201` + `Idempotent-Replayed: true`, `A` 잔액 `"70000"` |
| 24 | 1번 완료 후 `Clock`을 정확히 24시간 앞으로 | `K1`, 본문 `T` | `201`, `Idempotent-Replayed` 없음, 새 `transferId`, `A` 잔액 `"40000"` |
| 25 | 락 타임아웃 예외를 1번 던지고 이후 정상 동작하는 테스트용 엔진 | `K1` 본문 `T` → 같은 요청 재시도 | 첫 응답 `503` `LOCK_ACQUISITION_TIMEOUT`, 재시도 `201` + `Idempotent-Replayed` 없음 (503은 저장하지 않음) |
| 26 | 1번 완료 | `GET /transfers/{1번 transferId}` | `200`, 본문이 1번 응답과 같음 |
| 27 | 없음 | `GET /transfers/not-a-uuid` | `404`, `$.code` = `"TRANSFER_NOT_FOUND"` |

계산: 6번 70,000 − 30,000 = 40,000. 16번 10,000 + 100,000 = 110,000. 19번 10,000,000 − 5,000,000 = 5,000,000, 당일 누적 5,000,000 + 1 > 5,000,000.

## 제약
- 멱등 처리를 컨트롤러 메서드 본문에 직접 쓰지 않는다. 별도 빈(예: `IdempotentTransferService`)으로 분리한다. 컨트롤러는 "헤더·본문 받기 → 멱등 처리 빈 호출 → 응답 반환"만 한다.
- `synchronized`나 전역 락으로 모든 이체를 직렬화하지 않는다. 서로 다른 키의 요청은 서로 기다리지 않아야 한다(M2-7 비기능 요구사항과 같다).
- `registerIfAbsent`는 "조회 후 등록" 2단계로 만들지 않는다. `ConcurrentHashMap#putIfAbsent` 또는 `compute` 계열로 한 번에 처리한다. 2단계로 만들면 시나리오 22에서 이체가 2건 실행될 수 있다.
- 테스트에서 `Thread.sleep`으로 순서를 맞추지 않는다. 시나리오 20·21은 `CountDownLatch`로 순서를 고정한다.

## 힌트
<details>
<summary>힌트 1: 실패 응답을 저장하려면</summary>

이체 실행 중 난 `BankException`이 `GlobalExceptionHandler`로 바로 날아가면 멱등 처리 빈은 저장할 기회를 잃는다. 멱등 처리 빈이 예외를 잡아 "상태 코드 + `ProblemDetail`"로 바꿔 저장해야 한다. M4-3에서 `ErrorCode` → 상태·`ProblemDetail`을 만드는 코드를 `GlobalExceptionHandler` 밖의 별도 빈으로 빼 두면 두 곳에서 같은 코드를 쓸 수 있다.
</details>

<details>
<summary>힌트 2: 헤더 검사를 본문 검사보다 먼저 하려면</summary>

`@RequestHeader`와 `@Valid @RequestBody` 파라미터는 메서드 파라미터 순서대로 resolver가 처리한다. `@RequestHeader(required = true)`의 누락은 `MissingRequestHeaderException`이다. `ResponseEntityExceptionHandler`가 이 예외를 처리하는 메서드를 찾아, 헤더 이름이 `Idempotency-Key`일 때만 `IDEMPOTENCY_KEY_MISSING`으로 바꾼다.
</details>

## 완료 기준
- [ ] `./gradlew test --tests "*Transfer*"`에서 시나리오 27개에 해당하는 테스트가 통과한다.
- [ ] 시나리오 22를 `@RepeatedTest(50)`으로 돌려 50회 모두 통과한다.
- [ ] 서버를 띄우고 같은 키로 `curl`을 2번 실행한 출력(두 번째에 `< Idempotent-Replayed: true`)을 `til/phase-4/M4-4-idempotency.md`에 붙인다.
- [ ] 같은 TIL에 4절 흐름도를 자기 코드의 클래스·메서드 이름으로 다시 그린 그림이 있다.

## 생각해볼 질문
1. 같은 키에 다른 본문이 왔을 때 409가 아니라 422로 정한 근거를 드래프트 2.7절과 이 레포의 규칙표(README 2절)로 설명한다. 반대로 409를 쓰는 회사가 있다면 그쪽 근거는 무엇일까?
2. 처리 중(IN_PROGRESS)인 요청에 409를 주는 대신 첫 요청이 끝날 때까지 기다렸다가 같은 결과를 주는 방법도 있다(M2-7 엔진이 이렇게 동작했다). 두 방식의 스레드 사용량과 클라이언트 구현 난이도를 비교한다.
3. 서버가 이체를 실행한 직후, 결과를 `IdempotencyStore`에 저장하기 직전에 프로세스가 죽으면 무슨 일이 생기나? 재시작하면 메모리의 키가 모두 사라지는데, 같은 키로 재시도가 오면 이중 출금을 어떻게 막을 수 있나? Phase 5에서 멱등 키를 이체와 **같은 DB 트랜잭션**으로 저장해야 하는 이유와 연결해 적는다.
