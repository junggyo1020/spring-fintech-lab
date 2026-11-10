# M4-3 에러 응답 표준화

> 가이드 수준: L2, 예상 시간: 4~5h, 선행: M4-2

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- `ErrorCode`의 모든 상수가 HTTP 상태 하나에 매핑됨을 `@ParameterizedTest` + `@EnumSource`로 보여준다.
- 모든 오류 응답(406 제외)을 `application/problem+json` 형식, 6개 필드(`type`, `title`, `status`, `detail`, `instance`, `code`)로 만든다.
- 검증 실패 응답에 필드별 오류 목록(`errors`)을 정해진 순서로 넣고 테스트로 검증한다.
- 409와 422를 README 2절 규칙표로 구분해, 이 미션의 매핑표 각 행에 근거를 적는다.

## 배경
오류 응답 형식이 엔드포인트마다 다르면 클라이언트는 응답마다 다른 파싱 코드를 짜야 하고, 새 오류가 생길 때마다 앱 배포가 필요해진다.
상태 코드를 잘못 고르면 더 큰 사고가 난다. 잔액 부족(재시도해도 실패)을 503(재시도하면 성공 가능)으로 돌려주면 클라이언트의 자동 재시도가 같은 요청을 반복한다.
예외 메시지를 그대로 응답에 넣으면 전체 계좌번호, 내부 클래스 이름, SQL(Phase 5)이 외부로 나간다.
M1-2에서 만든 `BankException`, `ErrorCode`를 M4-2의 컨트롤러에 연결해, 도메인 예외가 정해진 HTTP 응답이 되게 한다.

## 요구사항

### 1. 응답 형식

```json
HTTP/1.1 422
Content-Type: application/problem+json

{
  "type": "urn:problem-type:lab-bank:insufficient-balance",
  "title": "잔액 부족",
  "status": 422,
  "detail": "잔액이 부족합니다. 계좌 110-****-0001",
  "instance": "/accounts/110-0000-0001/withdrawals",
  "code": "INSUFFICIENT_BALANCE"
}
```

| 필드 | 규칙 |
|---|---|
| `type` | `urn:problem-type:lab-bank:` + `code`를 소문자로 바꾸고 `_`를 `-`로 바꾼 값 |
| `title` | 아래 매핑표의 "title" 열 값. 같은 `code`면 항상 같다 |
| `status` | 응답 상태 코드와 같은 숫자 |
| `detail` | 발생 건 설명. 계좌번호는 `AccountNumber#masked()` 형식(`110-****-0001`)만 넣는다. 예외 클래스 이름, 스택 트레이스, 원본 예외 메시지(500일 때)를 넣지 않는다 |
| `instance` | 요청 URI의 경로 부분 (`HttpServletRequest#getRequestURI()`), 쿼리 문자열 제외 |
| `code` | 아래 매핑표의 `code` 열 값 |

### 2. 검증 실패 응답의 `errors`

```json
{
  "type": "urn:problem-type:lab-bank:validation-failed",
  "title": "입력값 검증 실패",
  "status": 400,
  "detail": "요청 값 2개가 검증을 통과하지 못했습니다.",
  "instance": "/accounts",
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "currency", "code": "Pattern", "message": "..."},
    {"field": "ownerName", "code": "NotBlank", "message": "..."}
  ]
}
```

- `field`: 본문 필드는 경로(`money`, `ownerName`), 경로 변수, 쿼리 파라미터는 파라미터 이름(`number`, `size`).
- `code`: 제약 애너테이션의 단순 이름(`NotBlank`, `Size`, `Pattern`, `NotNull`, `ValidMoney`, `AccountNumberFormat`). 타입 변환 실패(`size=abc`)는 `TypeMismatch`.
- `message`: Bean Validation 메시지. **로케일에 따라 바뀌므로 테스트에서 비교하지 않는다.** `field`와 `code`만 비교한다.
- 정렬: `field` 오름차순, 같으면 `code` 오름차순. 같은 (`field`, `code`) 쌍은 1개만 남긴다.
- `detail`의 숫자 = `errors` 원소 수.

### 3. 매핑표: 도메인 `ErrorCode` (`lab.bank.common`, M1-2, M1-3, M2-4, M2-5, M2-7에서 만든 enum, 상수 15개)
HTTP 상태는 `ErrorCode` enum에 넣지 않는다. 도메인은 HTTP를 모른다. 매핑은 `lab.bank.web.error` 패키지에 둔다.

| `code` | 발생 예외 | 상태 | title | 근거 (README 2절 규칙) |
|---|---|---|---|---|
| `INVALID_AMOUNT` | `InvalidAmountException` | 400 | 잘못된 금액 | 금액 ≤ 0은 요청만 보고 판단 가능 |
| `SAME_ACCOUNT_TRANSFER` | `SameAccountTransferException` | 400 | 같은 계좌 이체 불가 | 요청의 두 필드만 비교하면 판단 가능 |
| `ACCOUNT_NOT_FOUND` | `AccountNotFoundException` | 404 | 계좌 없음 | 리소스 없음 |
| `TRANSACTION_NOT_FOUND` | `TransactionNotFoundException` | 404 | 거래 없음 | 리소스 없음 |
| `ACCOUNT_NOT_ACTIVE` | `AccountNotActiveException` | 409 | 거래 불가 상태 | 계좌 `status`와 충돌. 해제(`unfreeze`)하면 같은 요청이 성공 |
| `ILLEGAL_STATE_TRANSITION` | `IllegalAccountStateTransitionException` | 409 | 허용되지 않은 상태 변경 | 계좌 `status`와 충돌 |
| `TRANSACTION_ALREADY_REVERSED` | `TransactionAlreadyReversedException` | 409 | 이미 취소된 거래 | 거래의 상태(취소됨)와 충돌 |
| `INSUFFICIENT_BALANCE` | `InsufficientBalanceException` | 422 | 잔액 부족 | 서버 데이터(잔액)와 비교한 규칙 위반 |
| `CURRENCY_MISMATCH` | `CurrencyMismatchException` | 422 | 통화 불일치 | 서버 데이터(계좌 통화)와 비교한 규칙 위반 |
| `DAILY_TRANSFER_LIMIT_EXCEEDED` | `DailyTransferLimitExceededException` | 422 | 1일 이체 한도 초과 | 서버 데이터(당일 누적액)와 비교한 규칙 위반 |
| `ACCOUNT_HAS_BALANCE` | `AccountHasBalanceException` | 422 | 잔액이 남은 계좌 | 서버 데이터(잔액)와 비교한 규칙 위반 |
| `INVALID_REVERSAL` | `InvalidReversalException` | 422 | 취소할 수 없는 거래 | 서버 데이터(원거래 유형)와 비교한 규칙 위반 |
| `IDEMPOTENCY_KEY_CONFLICT` | `IdempotencyKeyConflictException` (M2-7), M4-4의 키 재사용 | 422 | 멱등 키 재사용 | 서버 데이터(저장된 첫 요청)와 비교한 규칙 위반. Idempotency-Key 드래프트 2.7절도 422 권고 |
| `LOCK_ACQUISITION_TIMEOUT` | `LockAcquisitionTimeoutException` (M2-4, M2-7에서 재사용) | 503 | 일시적 처리 지연 | 재시도하면 성공 가능. 응답 헤더 `Retry-After: 1` 추가 |

- 위 표는 14행이다. M2-5의 `OPTIMISTIC_LOCK_FAILURE`(`OptimisticLockFailureException`)는 일부러 비워 두었다. README 2절 규칙으로 상태를 정해 15번째 행을 추가하고 `til/phase-4/M4-3-error-mapping.md`에 근거를 적는다. 그 밖에 직접 추가한 상수가 있으면 같은 방법으로 행을 추가한다.
- 거래 취소(`reverse`) API는 이 Phase에서 만들지 않는다. `TRANSACTION_NOT_FOUND`, `TRANSACTION_ALREADY_REVERSED`, `INVALID_REVERSAL`은 시나리오 17의 매핑 테스트로만 확인한다.

### 4. 매핑표: 웹 계층 코드 (`WebErrorCode` enum, 새로 만든다)

| `code` | 발생 원인 | 상태 | title | 도입 미션 |
|---|---|---|---|---|
| `VALIDATION_FAILED` | `MethodArgumentNotValidException`, `HandlerMethodValidationException`, 쿼리 파라미터 타입 변환 실패 | 400 | 입력값 검증 실패 | M4-3 |
| `INVALID_REQUEST_BODY` | `HttpMessageNotReadableException` (JSON 문법 오류, 본문 없음, 타입 불일치) | 400 | 읽을 수 없는 요청 본문 | M4-3 |
| `RESOURCE_NOT_FOUND` | `NoResourceFoundException` (매핑 없는 경로) | 404 | 리소스 없음 | M4-3 |
| `METHOD_NOT_ALLOWED` | `HttpRequestMethodNotSupportedException` | 405 | 허용되지 않은 메서드 | M4-3 |
| `UNSUPPORTED_MEDIA_TYPE` | `HttpMediaTypeNotSupportedException` | 415 | 지원하지 않는 본문 형식 | M4-3 |
| `INTERNAL_ERROR` | 위에 해당하지 않는 모든 `Exception` | 500 | 서버 오류 | M4-3 |
| `IDEMPOTENCY_KEY_MISSING` | `Idempotency-Key` 헤더 없음 | 400 | 멱등 키 누락 | M4-4 |
| `IDEMPOTENCY_KEY_INVALID` | 헤더 값 형식 오류 | 400 | 멱등 키 형식 오류 | M4-4 |
| `IDEMPOTENCY_REQUEST_IN_PROGRESS` | 같은 키 요청이 처리 중 | 409 | 같은 요청 처리 중 | M4-4 |
| `TRANSFER_NOT_FOUND` | 없는 `transferId` 조회 | 404 | 이체 없음 | M4-4 |
| `INVALID_CURSOR` | 커서 해석 실패, 조건 불일치 | 400 | 잘못된 커서 | M4-5 |
| `INVALID_DATE_RANGE` | `from` > `to`, 기간 365일 초과 | 400 | 잘못된 조회 기간 | M4-5 |
| `UNAUTHENTICATED` | 인증 없음, 실패 | 401 | 인증 필요 | M4-7 |
| `ACCESS_DENIED` | 역할 부족 | 403 | 권한 없음 | M4-7 |

- 406(`HttpMediaTypeNotAcceptableException`)은 클라이언트가 JSON을 받지 않겠다고 한 경우라 `problem+json` 본문을 강제하지 않는다. 상태 코드만 406이면 된다.
- 500의 `detail`은 항상 `"요청을 처리하지 못했습니다."`다. 원본 예외는 `ERROR` 레벨 로그에 스택 트레이스와 함께 남긴다. 4xx는 `WARN` 레벨 1줄(`code`, `instance`)만 남기고 스택 트레이스를 남기지 않는다.
- 이 미션에서는 표에서 "M4-3"과 도메인 `ErrorCode` 행만 구현한다. 나머지 상수는 enum에 미리 만들어 두거나 각 미션에서 추가한다.

### 5. 구현 구조 (핵심 시그니처만 제공)

```java
@RestControllerAdvice
public class GlobalExceptionHandler extends ResponseEntityExceptionHandler {
    // BankException, CurrencyMismatchException, Exception 핸들러를 추가하고
    // Spring MVC 기본 예외(400/404/405/415)의 ProblemDetail에도 code, type, title을 채운다
}
```

- `ResponseEntityExceptionHandler`를 상속한다. Spring MVC 기본 예외를 이미 `ProblemDetail`로 바꿔 주기 때문이다.
- `spring.mvc.problemdetails.enabled`(기본값 `false`)는 설정하지 않는다. `true`로 켜면 Spring Boot가 `ProblemDetailsExceptionHandler`(`ResponseEntityExceptionHandler` 하위 클래스)를 등록하는데, 이 등록에는 `@ConditionalOnMissingBean(ResponseEntityExceptionHandler.class)` 조건이 붙어 있어 이 클래스가 빈으로 있으면 등록되지 않는다 (Spring Boot 4.1.2 `WebMvcAutoConfiguration`에서 확인). 이 클래스를 만든 뒤에는 켜도 결과가 같다.

### 6. 운영용 엔드포인트 (이 미션에서 추가)
409를 API로 재현하려면 계좌를 정지할 수 있어야 한다.

| 메서드, 경로 | 성공 응답 | 실패 |
|---|---|---|
| `POST /ops/accounts/{number}/freeze` | `200`, `AccountResponse` (`status` = `"FROZEN"`) | 이미 `FROZEN`, `CLOSED` → 409 `ILLEGAL_STATE_TRANSITION` |
| `POST /ops/accounts/{number}/unfreeze` | `200`, `AccountResponse` (`status` = `"ACTIVE"`) | `ACTIVE`, `CLOSED` → 409 `ILLEGAL_STATE_TRANSITION` |

요청 본문은 없다. 이 경로는 M4-7에서 `OPS` 역할만 호출할 수 있게 막는다.

## 테스트 시나리오
`@SpringBootTest` + `@AutoConfigureMockMvc`. `A`는 테스트 안에서 개설한 KRW 계좌, `N`은 개설하지 않은 번호 `110-9999-0000`이다. 모든 오류 행은 공통으로 `Content-Type`이 `application/problem+json`과 호환되고 `$.instance`가 요청 경로와 같아야 한다.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 없음 | `GET /accounts/110-9999-0000` | `404`, `$.code` = `"ACCOUNT_NOT_FOUND"`, `$.type` = `"urn:problem-type:lab-bank:account-not-found"`, `$.title` = `"계좌 없음"`, `$.status` = `404`, `$.detail`에 `"110-****-0000"` 포함, `"110-9999-0000"` 미포함 |
| 2 | `A` 잔액 10,000 | `POST /accounts/A/withdrawals` `{"money":{"amount":"10001","currency":"KRW"}}` | `422`, `$.code` = `"INSUFFICIENT_BALANCE"`, 이후 `GET /accounts/A`의 `$.balance.amount` = `"10000"` |
| 3 | `A` (KRW) | `POST /accounts/A/deposits` `{"money":{"amount":"10.00","currency":"USD"}}` | `422`, `$.code` = `"CURRENCY_MISMATCH"` |
| 4 | `A`를 `POST /ops/accounts/A/freeze` | `POST /accounts/A/deposits` 1,000 KRW | `409`, `$.code` = `"ACCOUNT_NOT_ACTIVE"` |
| 5 | 4번 이후 `POST /ops/accounts/A/unfreeze` | 같은 입금 | `200`, `$.balanceAfter.amount` = `"1000"` |
| 6 | `A` `FROZEN` | `POST /ops/accounts/A/freeze` | `409`, `$.code` = `"ILLEGAL_STATE_TRANSITION"` |
| 7 | 없음 | `POST /accounts` `{"ownerName":"","currency":"krw"}` | `400`, `$.code` = `"VALIDATION_FAILED"`, `$.errors.length()` = `2`, `$.errors[0].field` = `"currency"`, `$.errors[0].code` = `"Pattern"`, `$.errors[1].field` = `"ownerName"`, `$.errors[1].code` = `"NotBlank"`, `$.detail` = `"요청 값 2개가 검증을 통과하지 못했습니다."` |
| 8 | 없음 | `POST /accounts` `{"ownerName":"홍길동"}` | `400`, `$.errors.length()` = `1`, `$.errors[0]` = `{field:"currency", code:"NotNull"}` |
| 9 | `A` (KRW) | 입금 `{"money":{"amount":"10000.0","currency":"KRW"}}` | `400`, `$.errors[0].field` = `"money"`, `$.errors[0].code` = `"ValidMoney"` |
| 10 | 없음 | `GET /accounts/1101234` | `400`, `$.code` = `"VALIDATION_FAILED"`, `$.errors[0].field` = `"number"`, `$.errors[0].code` = `"AccountNumberFormat"` |
| 11 | 없음 | `POST /accounts`, 본문 `{"ownerName":"홍길동","currency":"KRW"` | `400`, `$.code` = `"INVALID_REQUEST_BODY"`, `$.detail`에 `"tools.jackson"`, `"Exception"` 미포함 |
| 12 | 없음 | `POST /accounts`, 본문 없음, `Content-Type: application/json` | `400`, `$.code` = `"INVALID_REQUEST_BODY"` |
| 13 | 없음 | `GET /no-such-path` | `404`, `$.code` = `"RESOURCE_NOT_FOUND"` |
| 14 | 없음 | `DELETE /accounts/110-0000-0001` | `405`, `$.code` = `"METHOD_NOT_ALLOWED"` |
| 15 | 없음 | `POST /accounts`, `Content-Type: text/plain` | `415`, `$.code` = `"UNSUPPORTED_MEDIA_TYPE"` |
| 16 | 테스트 소스에만 있는 컨트롤러 `GET /test/boom`이 `RuntimeException("internal-secret-42")`을 던짐 | `GET /test/boom` | `500`, `$.code` = `"INTERNAL_ERROR"`, `$.detail` = `"요청을 처리하지 못했습니다."`, 응답 본문 전체에 `"internal-secret-42"` 미포함 |
| 17 | 없음 | `ErrorCode.values()` 전체를 `@EnumSource`로 매핑 함수에 넣음 | 모든 상수가 `null`이 아닌 상태를 반환, 값이 3절 표와 같음 |
| 18 | 없음 | `WebErrorCode.values()` 전체 | 모든 상수가 4절 표의 상태와 같음 |
| 19 | 테스트 전용 컨트롤러 `GET /test/lock-timeout`이 락 타임아웃 예외를 던짐 | `GET /test/lock-timeout` | `503`, `$.code` = `"LOCK_ACQUISITION_TIMEOUT"`, 응답 헤더 `Retry-After` = `"1"` |

## 제약
- 컨트롤러 메서드 안에 `try-catch`를 쓰지 않는다. 예외 → 응답 변환은 `GlobalExceptionHandler` 한 곳에서만 한다.
- `ErrorCode` enum에 `HttpStatus`나 숫자 상태 코드 필드를 넣지 않는다.
- `IllegalArgumentException`, `IllegalStateException`을 400으로 매핑하지 않는다. 라이브러리 내부 버그도 400이 되어 서버 오류가 클라이언트 잘못으로 숨는다. 이 둘은 500으로 둔다.
- 예외 메시지(`getMessage()`)를 `detail`로 그대로 쓰지 않는다. Phase 1 예외 메시지에 전체 계좌번호가 들어 있다면 이 미션에서 마스킹 번호로 바꾼다.

## 힌트
<details>
<summary>힌트 1: Spring MVC 기본 예외에 `code` 붙이기</summary>

`ResponseEntityExceptionHandler`에서 모든 기본 예외가 지나가는 protected 메서드가 무엇인지 소스에서 찾는다(`handleExceptionInternal`, `createResponseEntity`). `body`가 `ProblemDetail`이면 거기에 `type`, `title`, `code`를 덮어쓴다. `ProblemDetail#setProperty`로 넣은 값은 JSON 최상위 필드로 나간다.
`HandlerMethodValidationException`의 오류 하나하나는 `MessageSourceResolvable`이고, `getCodes()` 배열의 마지막 원소가 제약의 단순 이름이다.
</details>

<details>
<summary>힌트 2: 상태 매핑 함수</summary>

`switch` 표현식을 `ErrorCode`에 쓰면 상수를 추가했을 때 `default` 없이 컴파일 오류가 나게 만들 수 있다(enum `switch` 표현식의 완전성 검사, Java 14부터). 시나리오 17의 테스트와 함께 "매핑 누락"을 두 번 막는다.
</details>

## 완료 기준
- [ ] `./gradlew test --tests "*ErrorResponse*"`에서 시나리오 19개에 해당하는 테스트가 통과한다.
- [ ] M4-2의 오류 시나리오(6, 7, 9~17, 19~25번)에 4절 표의 `$.code` 검증을 추가했고 모두 통과한다.
- [ ] `til/phase-4/M4-3-error-mapping.md`에 3절, 4절 표가 있고, 추가한 행이 있으면 근거 열이 채워져 있다.
- [ ] `curl -v localhost:8080/accounts/110-9999-0000` 출력에 `< Content-Type: application/problem+json`이 보인다.
- [ ] `grep -rn "try {" src/main/java/lab/bank/web/*Controller.java` 결과가 0줄이다.

## 생각해볼 질문
1. 잔액 부족을 409로 정한 API도 실제로 있다. 409로 정했을 때 클라이언트가 "재시도하면 될까?"를 판단하는 데 어떤 차이가 생기나? 이 레포의 규칙표(README 2절)에서 가장 판단이 애매했던 행 하나와 이유를 적는다.
2. `code` 필드 없이 `type` URI만으로 분기하게 하면 어떤 장단점이 있나? RFC 9457 3.1.1절이 `type`에 대해 권고하는 내용과 비교한다.
3. Phase 5에서 DB 유니크 제약 위반(`DataIntegrityViolationException`)과 낙관적 락 실패(`OptimisticLockingFailureException`)가 새로 생긴다. 각각 이 레포의 규칙표로는 몇 번 상태가 되어야 하나?
