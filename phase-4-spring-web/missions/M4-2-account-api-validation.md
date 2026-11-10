# M4-2 계좌 API와 입력 검증

> 가이드 수준: L2, 예상 시간: 5~6h, 선행: M4-1

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 계좌 개설, 조회, 입금, 출금 API 4개를 만들고, 개설 응답의 `201`과 `Location` 헤더를 테스트로 검증한다.
- 요청, 응답을 `record` DTO로 분리해, 도메인 클래스(`Account`, `Transaction`)가 JSON으로 직접 나가지 않음을 보여준다.
- 커스텀 Bean Validation 제약 2개(`@AccountNumberFormat`, `@ValidMoney`)를 만들고, 경계값 입력 12종이 모두 400이 되는 테스트를 작성한다.

## 배경
금융 API의 첫 방어선은 입력 검증이다. 금액 `"10000.5"`를 원화 계좌에 받아 내부에서 반올림하면 고객이 보낸 금액과 장부 금액이 달라지고, 대사(Phase 6)에서 차이가 난다.
검증을 빠뜨리면 잘못된 값이 도메인까지 들어가 `IllegalArgumentException` → 500이 되고, 클라이언트는 자기 잘못인지 서버 장애인지 구분하지 못한다.
M4-1에서 만든 HTTP 계층 위에 Phase 1의 `Account`, `Money`, `AccountNumber`와 Phase 3의 서비스 빈을 연결한다.

## 요구사항

### 1. 엔드포인트

| 메서드, 경로 | 요청 본문 | 성공 응답 |
|---|---|---|
| `POST /accounts` | `CreateAccountRequest` | `201`, `Location: /accounts/{number}`, 본문 `AccountResponse` |
| `GET /accounts/{number}` | 없음 | `200`, `AccountResponse` |
| `POST /accounts/{number}/deposits` | `MoneyMovementRequest` | `200`, `TransactionResponse` |
| `POST /accounts/{number}/withdrawals` | `MoneyMovementRequest` | `200`, `TransactionResponse` |

입금, 출금은 만든 거래를 단건으로 조회하는 URI가 없으므로 `201` + `Location` 대신 `200`을 쓴다(README 2절 규칙).

### 2. JSON 형식 (이 Phase 전체에서 같은 형식을 쓴다)

```json
// POST /accounts 요청
{"ownerName": "홍길동", "currency": "KRW"}

// AccountResponse
{"number": "110-0000-0001", "ownerName": "홍길동", "currency": "KRW",
 "balance": {"amount": "0", "currency": "KRW"}, "status": "ACTIVE"}

// POST /accounts/{number}/deposits 요청 (withdrawals도 같음)
{"money": {"amount": "10000", "currency": "KRW"}, "memo": "급여"}

// TransactionResponse
{"transactionId": "UUID 문자열", "type": "DEPOSIT",
 "money": {"amount": "10000", "currency": "KRW"},
 "balanceAfter": {"amount": "10000", "currency": "KRW"},
 "memo": "급여", "occurredAt": "2026-11-10T14:30:00"}
```

- 금액은 JSON 숫자가 아니라 **문자열**이다. 이유는 M4-6에서 다룬다. 이 미션에서는 `record MoneyDto(String amount, String currency)`로 받고 보낸다.
- 응답 금액 문자열은 통화 scale로 맞춘 `BigDecimal#toPlainString()` 결과다. KRW `10000` → `"10000"`, USD `1000.5` → `"1000.50"`. 천 단위 구분 기호를 넣지 않는다.
- `occurredAt`은 이 미션에서 `LocalDateTime`의 Jackson 3 기본 출력(오프셋 없음)을 쓴다. M4-6에서 `+09:00` 오프셋을 붙인다.
- JSON 필드 순서는 검증하지 않는다. 속성 순서는 Jackson 버전의 기본값(Jackson 3.0에서 속성 정렬 관련 기본값이 바뀌었다)과 설정에 따라 달라지므로, 위 예시와 순서가 달라도 된다. 테스트는 JSONPath로 필드별로 비교한다.
- 요청에 정의되지 않은 필드(예: `"foo": 1`)는 무시한다. Jackson 3의 기본값(`FAIL_ON_UNKNOWN_PROPERTIES` 꺼짐)을 그대로 쓴다.

### 3. 계좌번호 발급
- 서버가 발급한다. `AccountNumberGenerator` 빈이 `110-0000-0001`부터 1씩 올려 발급한다(`110-0000-0002`, ...). 이 레포의 규칙이다.
- 동시에 개설 요청이 와도 같은 번호를 두 번 발급하지 않는다(`AtomicLong`, Phase 2 M2-5).
- `110-9999-9999` 다음 번호는 발급하지 않고 `IllegalStateException`을 던진다. 테스트하지 않는다.
- 테스트는 특정 번호를 가정하지 않는다. `@SpringBootTest` 컨텍스트는 테스트 클래스 사이에 캐시되어 앞선 테스트가 번호를 소비한다. 개설 응답의 `$.number`를 읽어 다음 요청에 쓴다.

### 4. 검증 규칙

| 필드 | 규칙 | 위반 시 |
|---|---|---|
| `ownerName` | `@NotBlank` (`null`, 빈 문자열, 공백만 금지) + `@Size(max = 20)` (`String#length()` 기준) | 400 |
| `currency` (개설 요청) | `@NotNull` + `@Pattern(regexp = "KRW\|USD")`, 대소문자 구분 (`"krw"`는 위반) | 400 |
| `money` | `@NotNull` + `@Valid`, `MoneyDto`에 `@ValidMoney` | 400 |
| `money.amount` | 정규식 `^(0\|[1-9][0-9]*)(\.[0-9]+)?$`, 정수부 최대 18자리, 소수 자리 수 ≤ 통화 scale (KRW 0, USD 2), 값 > 0 | 400 |
| `money.currency` | `"KRW"` 또는 `"USD"` | 400 |
| `memo` | 생략, `null` 허용(빈 문자열로 저장), `@Size(max = 50)` | 400 |
| `{number}` (경로) | `@AccountNumberFormat`: 정규식 `^[0-9]{3}-[0-9]{4}-[0-9]{4}$` | 400 |

- 표 안의 `\|`는 마크다운 표를 깨지 않기 위한 표기다. 코드에는 `|` 하나만 쓴다.
- 소수 자리 수는 **문자열에 적힌 자리 수**로 센다. KRW `"10000.0"`, `"10000.00"`은 값이 정수여도 400이다. M1-1의 `Money.of("1000.0", KRW)`는 값을 잃지 않으므로 허용하지만, API는 이 레포의 규칙으로 더 엄격하게 거절한다. 클라이언트가 통화의 소수 자리를 잘못 알고 있다는 신호를 첫 요청에서 알려 주기 위해서다. USD `"1000.5"`는 허용하고 `"1000.50"`으로 저장한다.
- 앞자리 0(`"010000"`), 부호(`"+100"`, `"-100"`), 지수(`"1e3"`), 공백(`" 100"`), 빈 문자열(`""`)은 정규식에서 걸린다. `"0"`, `"0.00"`은 정규식은 통과하고 "값 > 0"에서 걸린다.
- 입금 계좌 통화와 `money.currency`가 다른 경우(KRW 계좌에 USD 입금)는 형식 검증이 아니라 도메인 규칙이다. 이 미션에서는 테스트하지 않고 M4-3에서 422로 만든다.

### 5. 커스텀 제약 (핵심 시그니처만 제공)

```java
@Target({ElementType.PARAMETER, ElementType.FIELD, ElementType.RECORD_COMPONENT})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = AccountNumberFormatValidator.class)
public @interface AccountNumberFormat { /* message, groups, payload */ }

@Target(ElementType.TYPE)            // MoneyDto 클래스에 붙인다
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidMoneyValidator.class)
public @interface ValidMoney { /* message, groups, payload */ }
```

- `@ValidMoney`는 `amount`와 `currency`를 함께 봐야 하므로(소수 자리 수 ≤ 통화 scale) 클래스 단위 제약이다.
- `null` 처리: `AccountNumberFormatValidator`는 `null`을 통과시킨다(`null` 금지는 `@NotNull` 담당: Bean Validation 관례). 경로 변수는 `null`이 될 수 없으므로 문제없다. `ValidMoneyValidator`는 `amount`나 `currency`가 `null`이면 위반으로 판정한다.

### 6. 계층 규칙
- 컨트롤러 → Phase 3의 애플리케이션 서비스(`BankService` 빈) 호출 → 반환된 도메인 객체를 응답 DTO로 변환한다.
- `MoneyDto` → `Money` 변환은 `Money.of(amount, Currency.valueOf(currency))`를 쓴다. 이 시점에는 `@ValidMoney`가 이미 통과했으므로 `Money.of`가 예외를 던지지 않는다.
- `Account`에 `getter`를 추가해야 한다면 추가한다. `setter`는 추가하지 않는다(Phase 1 제약 유지).

## 테스트 시나리오
모든 테스트는 `@SpringBootTest` + `@AutoConfigureMockMvc`로 실제 서비스 빈을 쓴다. 표의 `A`는 그 테스트 안에서 `POST /accounts`로 새로 만든 계좌의 번호다.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 없음 | `POST /accounts` `{"ownerName":"홍길동","currency":"KRW"}` | `201`, `Location` = `/accounts/` + `$.number`, `$.number`가 `^110-[0-9]{4}-[0-9]{4}$`와 일치, `$.balance.amount` = `"0"`, `$.balance.currency` = `"KRW"`, `$.status` = `"ACTIVE"` |
| 2 | 1번으로 계좌 `A` 개설 | `GET` + 1번의 `Location` 값 | `200`, `$.number` = `A`, `$.ownerName` = `"홍길동"` |
| 3 | `A` (KRW, 잔액 0) | `POST /accounts/A/deposits` `{"money":{"amount":"10000","currency":"KRW"},"memo":"급여"}` | `200`, `$.type` = `"DEPOSIT"`, `$.money.amount` = `"10000"`, `$.balanceAfter.amount` = `"10000"`, `$.memo` = `"급여"`, `$.transactionId` 비어 있지 않음 |
| 4 | `A`에 10,000 입금 | `POST /accounts/A/withdrawals` `{"money":{"amount":"10000","currency":"KRW"}}` | `200`, `$.type` = `"WITHDRAWAL"`, `$.balanceAfter.amount` = `"0"`, `$.memo` = `""` |
| 5 | USD 계좌 `U` | `POST /accounts/U/deposits` `{"money":{"amount":"1000.5","currency":"USD"}}` | `200`, `$.money.amount` = `"1000.50"`, `$.balanceAfter.amount` = `"1000.50"` |
| 6 | 없음 | `POST /accounts` `{"ownerName":"   ","currency":"KRW"}` | `400` |
| 7 | 없음 | `POST /accounts` `{"ownerName":"가나다라마바사아자차카타파하가나다라마바사","currency":"KRW"}` (21자) | `400` |
| 8 | 없음 | `POST /accounts` `{"ownerName":"가나다라마바사아자차카타파하가나다라마바","currency":"KRW"}` (20자) | `201` |
| 9 | 없음 | `POST /accounts` `{"ownerName":"홍길동","currency":"krw"}` | `400` |
| 10 | 없음 | `POST /accounts` `{"ownerName":"홍길동"}` (`currency` 누락) | `400` |
| 11 | `A` (KRW) | 입금 `amount` = `"10000.0"` | `400`, `A` 잔액 `"0"` 유지 (`GET`으로 확인) |
| 12 | `A` | 입금 `amount` = `"0"` | `400` |
| 13 | `A` | 입금 `amount` = `"-100"` | `400` |
| 14 | `A` | 입금 `amount` = `"010000"` | `400` |
| 15 | `A` | 입금 `amount` = `"1e3"` | `400` |
| 16 | `A` | 입금 `amount` = `""` | `400` |
| 17 | `A` | 입금 `"money": null` | `400` |
| 18 | `A` | 입금 `amount` = `"999999999999999999"` (18자리) | `200`, `$.balanceAfter.amount` = `"999999999999999999"` |
| 19 | `A` | 입금 `amount` = `"1000000000000000000"` (19자리) | `400` |
| 20 | USD 계좌 `U` | 입금 `amount` = `"10.123"` | `400` |
| 21 | `A` | 입금 `memo` = 51자 문자열 | `400` |
| 22 | 없음 | `GET /accounts/1101234` | `400` |
| 23 | 없음 | `GET /accounts/abc-defg-hijk` | `400` |
| 24 | 없음 | `POST /accounts`, 본문 `{"ownerName":"홍길동","currency":"KRW"` (닫는 괄호 없음) | `400` |
| 25 | 없음 | `POST /accounts`, `Content-Type: text/plain`, 본문은 1번과 같음 | `415` |
| 26 | 스레드 50개 | 동시에 `POST /accounts` 50회 | 모두 `201`, `$.number` 50개가 모두 다름 |

400 응답의 본문 형식은 M4-3에서 정한다. 이 미션은 상태 코드만 검증한다. 없는 계좌 조회(404)도 M4-3에서 다룬다.

## 제약
- 금액을 `double`, `float`, `long`으로 받지 않는다. `String` → 검증 → `BigDecimal`(`Money.of`) 순서를 지킨다.
- 컨트롤러 메서드 안에서 `if (amount ...)`로 검증하지 않는다. 모든 형식 검증은 Bean Validation 제약으로 표현한다.
- 컨트롤러가 `Account`, `Transaction`, `Money`를 직접 반환하지 않는다.
- 커스텀 제약의 정규식 `Pattern`은 `static final` 필드로 한 번만 컴파일한다.

## 힌트
<details>
<summary>힌트 1: 경로 변수 검증이 동작하지 않을 때</summary>

Spring Framework 6.1부터 컨트롤러 메서드 파라미터에 `@Constraint` 계열 애너테이션이 직접 붙어 있으면 내장 메서드 검증이 실행된다. 컨트롤러 클래스에 `@Validated`를 함께 붙이면 AOP 기반 검증과 겹친다. Spring MVC 레퍼런스 "Annotated Controllers > Validation" 절에서 두 방식의 차이를 확인한다.
파라미터 이름(`number`)이 오류에 나오려면 `-parameters` 컴파일 옵션이 필요하다. Spring Boot Gradle 플러그인이 켜 준다.
</details>

<details>
<summary>힌트 2: `Location` 헤더 만들기</summary>

`ServletUriComponentsBuilder`나 `ResponseEntity.created(URI)`를 찾아본다. 시나리오 1은 `Location`이 `/accounts/`로 시작하는 경로인지만 본다. `MockMvc`에서는 호스트가 `http://localhost`로 붙을 수 있으니 테스트에서 경로 부분만 비교한다.
</details>

## 완료 기준
- [ ] `./gradlew test --tests "*AccountController*"`에서 시나리오 26개에 해당하는 테스트가 통과한다 (`@ParameterizedTest` 1개가 여러 행을 맡아도 된다).
- [ ] 서버를 띄우고 `curl -v -X POST localhost:8080/accounts -H 'Content-Type: application/json' -d '{"ownerName":"홍길동","currency":"KRW"}'` 출력에 `< HTTP/1.1 201`과 `< Location: /accounts/110-`가 보인다. 출력을 `til/phase-4/M4-2-curl.md`에 붙인다.
- [ ] `src/main/java/lab/bank/web/dto/`에 요청 DTO 2개, 응답 DTO 2개, `MoneyDto`가 있고 모두 `record`다.
- [ ] `grep -rnwE "double|float" src/main/java/lab/bank/web` 결과가 0줄이다.

## 생각해볼 질문
1. 금액 소수 자리 초과(`"10000.0"` KRW)를 반올림해서 받는 것과 400으로 거절하는 것은 고객, 은행 각각에게 어떤 위험이 있나?
2. `@ValidMoney` 검증(형식)과 `Account#deposit`의 금액 검증(도메인)이 둘 다 "금액 > 0"을 검사한다. 중복을 없애려면 어느 쪽을 지워야 하나? 지우면 안 되는 이유가 있다면 무엇인가? (Phase 5에서 배치가 `BankService`를 직접 호출하는 경우를 떠올린다)
3. 계좌번호를 `AtomicLong`으로 발급하면 서버를 재시작했을 때와 서버를 2대로 늘렸을 때 각각 무슨 일이 생기나? Phase 5에서 DB 시퀀스나 `AUTO_INCREMENT`로 바꾸면 무엇이 해결되나?
