# M4-6 금액, 날짜 직렬화

> 가이드 수준: L2, 예상 시간: 3~4h, 선행: M4-2

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 금액을 JSON 숫자로 보냈을 때 JavaScript가 `9007199254740993`을 `9007199254740992`로 읽는 것을 `curl` + `node` 출력으로 보여준다.
- Jackson 3의 `ValueSerializer`, `ValueDeserializer`로 `Money` ↔ `{"amount":"1000.00","currency":"USD"}` 변환기를 만들고, 경계 입력 10종을 테스트로 검증한다.
- 거래 시각을 `2026-11-10T14:30:00+09:00`처럼 오프셋이 붙은 ISO-8601 문자열로 내보낸다.
- 이 변경으로 M4-2~M4-5 테스트의 기대값 중 무엇이 바뀌는지 표로 정리하고 테스트를 고친다.

## 배경
JSON 명세는 숫자의 정밀도를 정하지 않지만, 브라우저와 Node.js의 `JSON.parse`는 모든 숫자를 IEEE 754 배정밀도(`Number`)로 읽는다. 정확히 표현되는 정수의 최댓값은 `Number.MAX_SAFE_INTEGER` = 2^53 − 1 = 9,007,199,254,740,991이다.
원화 잔액 9,007,199,254,740,993원은 현실에 없지만, 소수 둘째 자리까지 있는 달러 금액 90,071,992,547,409.93은 `JSON.parse` 후 90,071,992,547,409.94가 된다. 웹 화면에 표시되는 금액과 원장 금액이 1센트 달라지고, 그 값을 다시 서버로 보내면 잘못된 금액으로 이체된다.
그래서 금융 API는 금액을 문자열로 주고받는 경우가 많다. M4-2에서 `MoneyDto(String, String)`로 이 형식을 먼저 정했다. 이 미션은 그 이유를 실험으로 확인하고, DTO 없이 도메인 `Money`가 직접 같은 JSON 형식으로 변환되게 바꾼다.

## 요구사항

### 1. 정밀도 손실 실험 (실험 후 코드 삭제)
1. 임시 컨트롤러 `GET /experiments/precision`을 만들어 `record PrecisionSample(BigDecimal krw, BigDecimal usd)`를 반환한다. 값: `krw` = `9007199254740993`, `usd` = `90071992547409.93`.
2. 아래 명령을 실행하고 출력 두 줄을 `til/phase-4/M4-6-precision.md`에 붙인다.

   ```bash
   curl -s localhost:8080/experiments/precision
   curl -s localhost:8080/experiments/precision | node -e '
     let s=""; process.stdin.on("data", d => s += d).on("end", () => {
       const o = JSON.parse(s); console.log(o.krw, o.usd, Number.MAX_SAFE_INTEGER); });'
   ```

   두 번째 명령의 기대 출력: `9007199254740992 90071992547409.94 9007199254740991` (Node.js 23.9.0에서 확인. `Number`가 IEEE 754 배정밀도인 모든 버전에서 같다).
3. 같은 TIL에 "서버가 보낸 값 / JS가 읽은 값 / 차이" 3열 표를 만든다. 실험이 끝나면 임시 컨트롤러와 `PrecisionSample`을 삭제한다.

### 2. `Money` JSON 변환기 (Jackson 3)
Spring Boot 4는 Jackson 3를 쓴다. Jackson 2와 다른 점:

| 항목 | Jackson 2 (Spring Boot 3.x) | Jackson 3 (Spring Boot 4.x) |
|---|---|---|
| 패키지 | `com.fasterxml.jackson.databind` | `tools.jackson.databind` |
| 직렬화기 기반 클래스 | `JsonSerializer<T>` | `ValueSerializer<T>` |
| 역직렬화기 기반 클래스 | `JsonDeserializer<T>` | `ValueDeserializer<T>` |
| 직렬화 메서드의 세 번째 인자 | `SerializerProvider` | `SerializationContext` |
| Spring Boot 등록 애너테이션 | `@JsonComponent` | `@JacksonComponent` (`org.springframework.boot.jackson`). `@JsonComponent`는 Jackson 2용 deprecated 모듈 `spring-boot-jackson2`에만 남아 있어 기본 의존성으로는 컴파일되지 않는다 |
| 애너테이션(`@JsonProperty` 등) 패키지 | `com.fasterxml.jackson.annotation` | 변경 없음 (`com.fasterxml.jackson.annotation`) |

- `MoneyJsonSerializer extends ValueSerializer<Money>`, `MoneyJsonDeserializer extends ValueDeserializer<Money>`를 `lab.bank.web.json`에 만들고 `@JacksonComponent`로 등록한다.
- `Money` 클래스에는 Jackson 애너테이션을 붙이지 않는다. 도메인이 JSON 라이브러리에 의존하지 않게 한다.
- M4-2의 `MoneyDto`와 `@ValidMoney`를 삭제하고, 요청, 응답 DTO의 금액 필드 타입을 `Money`로 바꾼다. JSON 형식은 M4-2와 같다.

**직렬화 규칙**: `{"amount": "<통화 scale로 맞춘 BigDecimal#toPlainString()>", "currency": "<KRW|USD>"}`. 지수 표기(`1E+3`)를 쓰지 않는다.

**역직렬화 규칙** (위반하면 Jackson 예외 → `HttpMessageNotReadableException` → 400 `INVALID_REQUEST_BODY`):

| 입력 | 결과 |
|---|---|
| `money` 값이 객체가 아님 (`"money": "1000"`, `"money": 1000`) | 400 `INVALID_REQUEST_BODY` |
| `amount` 누락, `null`, 또는 JSON 문자열이 아님 (`"amount": 10000`) | 400 `INVALID_REQUEST_BODY` |
| `amount`가 M4-2의 정규식, 18자리, 소수 자리 규칙 위반 (`"-100"`, `"010000"`, `"1e3"`, `""`, KRW `"10000.0"`, USD `"10.123"`) | 400 `INVALID_REQUEST_BODY` |
| `currency` 누락, `null`, `"KRW"`/`"USD"` 이외 | 400 `INVALID_REQUEST_BODY` |
| `money` 객체 안의 다른 필드 (`"foo": 1`) | 무시 |
| `"amount": "0"` | `Money` 생성 성공 (Phase 1 `Money`는 0을 허용). 이후 도메인이 `InvalidAmountException` → 400 `INVALID_AMOUNT` |
| `"money": null` | 역직렬화기는 호출되지 않는다. DTO의 `@NotNull` → 400 `VALIDATION_FAILED` |

- 숫자 `amount`를 거절하는 이유: 클라이언트가 숫자로 보냈다면 클라이언트 쪽에서 이미 정밀도가 손실됐을 수 있다. 서버가 받아 주면 손실된 값을 정상 값으로 처리하게 된다.
- `INVALID_REQUEST_BODY`의 `detail`은 `"요청 본문을 읽을 수 없습니다."`로 고정한다. Jackson 예외 메시지(클래스 이름, 입력 일부 포함)를 넣지 않는다.

### 3. 날짜, 시각 형식
- `TransactionResponse.occurredAt`, `TransferResponse.executedAt`의 타입을 `OffsetDateTime`으로 바꾼다. 도메인의 `LocalDateTime`(Phase 1, `Asia/Seoul` `Clock` 기준)을 `ZoneId.of("Asia/Seoul")`의 오프셋 `+09:00`으로 변환한다.
- 출력 예: `"2026-11-10T14:30:00+09:00"`. 나노초가 0이 아니면 소수 초가 붙는다(`"2026-11-10T14:30:00.123+09:00"`). 이 미션의 테스트는 초 단위로 고정한 `Clock`을 쓴다.
- Jackson 3는 `java.time` 지원이 기본 포함이고, 날짜를 타임스탬프 숫자가 아닌 ISO-8601 문자열로 쓰는 것이 기본값이다. Jackson 2처럼 `JavaTimeModule`을 등록하거나 `WRITE_DATES_AS_TIMESTAMPS`를 끌 필요가 없다.
- 쿼리 파라미터 `from`, `to`(M4-5)는 `LocalDate` 그대로 둔다.

### 4. 기대값 변경표
이 미션 전에 작성한 테스트를 아래 표대로 고친다. 표에 없는 테스트는 수정 없이 통과해야 한다.

| 미션, 시나리오 | 이전 기대값 | 바뀐 기대값 |
|---|---|---|
| M4-2 #11, #13~#16, #19, #20 (금액 형식 위반) | `400` (M4-3 이후 `VALIDATION_FAILED`) | `400`, `$.code` = `"INVALID_REQUEST_BODY"`, `$.errors` 없음 |
| M4-2 #12 (`"0"`) | `400` `VALIDATION_FAILED` | `400`, `$.code` = `"INVALID_AMOUNT"` |
| M4-3 #9 (KRW `"10000.0"`) | `VALIDATION_FAILED`, `errors[0].code` = `"ValidMoney"` | `INVALID_REQUEST_BODY` |
| `occurredAt`, `executedAt`을 검증하는 모든 시나리오 (M4-5 #1, #8 등) | `"2026-11-01T09:24:00"` | `"2026-11-01T09:24:00+09:00"` |

## 테스트 시나리오
1~10은 `@JsonTest`로 Jackson 설정만 띄운 테스트(`JacksonTester` 사용), 11~15는 `@SpringBootTest` + `@AutoConfigureMockMvc`. `@JsonTest`를 쓰려면 `testImplementation("org.springframework.boot:spring-boot-starter-jackson-test")`를 추가한다. `@JsonTest`의 패키지는 `org.springframework.boot.test.autoconfigure.json`이다 (Boot 4.1.2에서 확인).

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | `Money.of("1000", USD)` | 직렬화 | `{"amount":"1000.00","currency":"USD"}` |
| 2 | `Money.zero(KRW)` | 직렬화 | `{"amount":"0","currency":"KRW"}` |
| 3 | `Money.of("9007199254740993", KRW)` | 직렬화 | `$.amount` = `"9007199254740993"` (문자열) |
| 4 | `Money.won(-500)` | 직렬화 | `$.amount` = `"-500"` |
| 5 | `{"amount":"1000.5","currency":"USD"}` | 역직렬화 | `Money.of("1000.50", USD)`와 `equals` |
| 6 | `{"amount":1000,"currency":"KRW"}` | 역직렬화 | Jackson 예외 (`tools.jackson.core.JacksonException`의 하위 타입) |
| 7 | `{"amount":"10.123","currency":"USD"}` | 역직렬화 | Jackson 예외 |
| 8 | `{"amount":"100","currency":"JPY"}` | 역직렬화 | Jackson 예외 |
| 9 | `{"currency":"KRW"}` / `{"amount":"100"}` / `{"amount":null,"currency":"KRW"}` | 역직렬화 | 3건 모두 Jackson 예외 |
| 10 | `{"amount":"0","currency":"KRW","foo":1}` | 역직렬화 | `Money.zero(KRW)`와 `equals` |
| 11 | KRW 계좌 `A` | 입금 `{"money":{"amount":"9007199254740993","currency":"KRW"}}` | `200`, `$.balanceAfter.amount` = `"9007199254740993"`. 응답을 `node`로 `JSON.parse`한 `balanceAfter.amount`도 `"9007199254740993"` (TIL에 출력 첨부) |
| 12 | `A` | 입금 `{"money":{"amount":10000,"currency":"KRW"}}` | `400`, `$.code` = `"INVALID_REQUEST_BODY"`, `$.detail` = `"요청 본문을 읽을 수 없습니다."`, `A` 잔액 `"0"` |
| 13 | `A` | 입금 `{"money":"10000"}` | `400`, `$.code` = `"INVALID_REQUEST_BODY"` |
| 14 | `A` | 입금 `{"money":{"amount":"0","currency":"KRW"}}` | `400`, `$.code` = `"INVALID_AMOUNT"` |
| 15 | `Clock` = `2026-11-10T14:30:00+09:00`, `A` | 입금 1,000 KRW | `$.occurredAt` = `"2026-11-10T14:30:00+09:00"` |

## 제약
- `Money`, `Currency`, `Account` 등 도메인 클래스에 `com.fasterxml.jackson.annotation`, `tools.jackson` import를 넣지 않는다.
- `spring.jackson.*` 프로퍼티나 `JsonMapper` 전역 설정으로 모든 `BigDecimal`을 문자열로 바꾸지 않는다(`WRITE_BIGDECIMAL_AS_PLAIN`, `NumberSerializer` 전역 교체 등). 금액이 아닌 `BigDecimal`(예: 이자율)까지 영향을 받는다. 변환은 `Money` 타입에만 건다.
- Jackson 2 패키지(`com.fasterxml.jackson.databind`)를 import하지 않는다. `grep -rn "com.fasterxml.jackson.databind" src` 결과가 0줄이어야 한다.

## 힌트
<details>
<summary>힌트 1: 역직렬화기에서 토큰 타입 확인</summary>

`ValueDeserializer#deserialize(JsonParser, DeserializationContext)`에서 객체 전체를 트리(`JsonNode`)로 읽은 뒤 `amount` 노드가 문자열 노드인지 확인하는 방법과, 토큰을 하나씩 읽는 방법이 있다. 잘못된 입력에서는 `DeserializationContext`가 제공하는 보고 메서드(`reportInputMismatch` 계열)로 Jackson 예외를 만든다. 직접 `IllegalArgumentException`을 던지면 Spring이 400으로 바꾸는지 직접 실험해 보고 TIL에 결과를 적는다.
</details>

<details>
<summary>힌트 2: 시각이 `Z`로 나올 때</summary>

출력이 `"2026-11-10T05:30:00Z"`라면 Jackson이 `OffsetDateTime`을 컨텍스트 시간대(UTC)로 바꿔 쓴 것이다. README "워크스페이스 만들기"의 `spring.jackson.time-zone: Asia/Seoul` 설정이 적용됐는지, Jackson 3의 `DateTimeFeature` 중 컨텍스트 시간대 조정 기능이 무엇인지 확인한다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 이 미션의 시나리오 15개와 4절 변경표를 반영한 M4-2~M4-5 테스트가 모두 통과한다.
- [ ] `til/phase-4/M4-6-precision.md`에 1절 실험 출력 2줄, 3열 표, 시나리오 11의 `node` 출력이 있다.
- [ ] `src/main/java/lab/bank/web/dto/MoneyDto.java`, `ValidMoney.java`가 삭제되었다.
- [ ] `grep -rn "jackson" src/main/java/lab/bank/money src/main/java/lab/bank/account` 결과가 0줄이다.

## 생각해볼 질문
1. M4-2 방식(`MoneyDto` + `@ValidMoney`)은 `errors`에 어느 필드가 틀렸는지 알려 줬지만, 이 미션의 방식은 `INVALID_REQUEST_BODY` 하나로 뭉뚱그린다. 두 방식의 장단점을 클라이언트 개발자 입장에서 비교한다. 역직렬화 오류에서 필드 경로를 꺼내 `errors`를 채울 방법이 있을까?
2. 금액을 정수 최소 단위(센트, `"amount": 100050`)로 보내는 API도 있다. 문자열 소수(`"1000.50"`)와 비교해 통화가 바뀔 때(소수 자리 0 → 2), 그리고 2^53을 넘는 값에서 각각 어떤 차이가 있나?
3. Phase 5에서 `Money`를 MySQL `DECIMAL(p, s)` 컬럼에 저장한다. 이 미션의 "정수부 18자리, 소수 2자리" 규칙을 지키려면 `p`, `s`는 얼마여야 하나?
