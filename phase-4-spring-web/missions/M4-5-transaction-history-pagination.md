# M4-5 거래내역 조회와 커서 페이지네이션

> 가이드 수준: L2 · 예상 시간: 4~5h · 선행: M4-3

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- `GET /accounts/{number}/transactions`를 커서 방식으로 만들고, 거래 25건을 20건 + 5건 두 페이지로 빠짐없이·중복 없이 받는 테스트를 작성한다.
- 두 페이지 조회 사이에 새 거래가 추가돼도 두 번째 페이지 결과가 바뀌지 않음을 테스트로 보여주고, 같은 상황에서 오프셋 방식은 어떤 거래를 두 번 돌려주는지 TIL에 표로 적는다.
- 시각이 같은 거래 3건이 `size=2`로 나뉘어도 누락·중복이 없음을 보여준다.
- 위조·변조된 커서 5종을 400 `INVALID_CURSOR`로 거절한다.

## 배경
거래내역은 계좌당 수년 치가 쌓이고, 앱은 최신 거래부터 스크롤하며 조금씩 불러온다.
오프셋 방식(`?page=2&size=20`)은 첫 페이지를 본 뒤 새 입금이 1건 들어오면 모든 행이 한 칸씩 밀려, 두 번째 페이지 첫 줄에 이미 본 거래가 다시 나온다. 고객은 같은 입금이 두 번 찍힌 것으로 보고 민원을 넣는다.
커서 방식은 "마지막으로 본 거래보다 오래된 것"을 요청하므로 앞쪽에 행이 추가돼도 결과가 밀리지 않는다. Phase 5에서 DB로 옮기면 오프셋은 앞의 행을 모두 읽고 버리므로 뒤 페이지로 갈수록 느려지는 문제도 생긴다.
M4-3의 오류 형식과 M1-3의 `Ledger`(`history(AccountNumber, LocalDate, LocalDate)`)를 그대로 쓴다.

## 요구사항

### 1. 엔드포인트
`GET /accounts/{number}/transactions?from=&to=&cursor=&size=`

| 파라미터 | 형식 | 기본값 | 규칙 |
|---|---|---|---|
| `from` | `yyyy-MM-dd` | `to` − 30일 | 포함. `Asia/Seoul` 기준 그날 00:00:00부터 |
| `to` | `yyyy-MM-dd` | 오늘 (`Clock` 기준, `Asia/Seoul`) | 포함. 그날 23:59:59.999999999까지 |
| `cursor` | 문자열 | 없음 (첫 페이지) | 이전 응답의 `nextCursor` 값 |
| `size` | 정수 | 20 | 1 이상 100 이하 |

```json
{
  "items": [ /* M4-2의 TransactionResponse, 최신순 */ ],
  "nextCursor": "djF8MTEwLTAwMDAtMDAwMXwy..."   // 다음 페이지가 없으면 null
}
```

### 2. 정렬과 페이지 경계
- 정렬: `occurredAt` 내림차순, 같으면 `transactionId` 문자열 내림차순(`String#compareTo`). 두 키를 합치면 모든 거래의 순서가 하나로 정해진다.
- 다음 페이지 조건: 커서의 (`occurredAt`, `transactionId`)보다 정렬상 뒤에 오는 것. 즉 `occurredAt < c.occurredAt` 또는 (`occurredAt == c.occurredAt` 그리고 `transactionId < c.transactionId`).
- `nextCursor`: `size + 1`건을 조회해 `size`건을 넘으면 `size`번째 항목으로 커서를 만든다. 넘지 않으면 `null`.
- 결과가 0건이면 `200`, `{"items":[],"nextCursor":null}`.

### 3. 커서 형식 (이 레포의 규칙)
클라이언트는 커서를 해석하지 않고 그대로 돌려보낸다(opaque). 서버 내부 형식은 아래로 고정한다.

```
Base64 URL-safe, 패딩 없음 ( UTF-8 문자열 "v1|{계좌번호}|{from}|{to}|{occurredAt}|{transactionId}" )
예: v1|110-0000-0001|2026-10-11|2026-11-10|2026-11-01T09:05:00|3f2c...  → Base64 URL 인코딩
```

- `from`, `to`는 기본값을 적용한 뒤의 실제 값이다. `occurredAt`은 `DateTimeFormatter.ISO_LOCAL_DATE_TIME`으로 쓴다.
- `cursor`와 함께 `from`·`to`를 보내면 커서 안의 값과 같아야 한다. 생략하면 커서 안의 값을 쓴다. `size`는 페이지마다 바꿔도 된다.

| 커서 거절 조건 | 응답 |
|---|---|
| Base64 URL 디코딩 실패 (`!!!`) | 400 `INVALID_CURSOR` |
| `\|`로 나눈 조각이 6개가 아님, 첫 조각이 `v1`이 아님 | 400 `INVALID_CURSOR` |
| 날짜·시각 파싱 실패 | 400 `INVALID_CURSOR` |
| 커서의 계좌번호 ≠ 경로의 `{number}` | 400 `INVALID_CURSOR` |
| 커서의 `from`/`to` ≠ 쿼리의 `from`/`to` (쿼리에 보낸 경우) | 400 `INVALID_CURSOR` |

표 안의 `\|`는 마크다운 표를 깨지 않기 위한 표기이며 실제 구분자는 `|` 하나다.

### 4. 기간 검증

| 입력 | 응답 |
|---|---|
| `from` > `to` | 400 `INVALID_DATE_RANGE` |
| `to` − `from` > 365일 | 400 `INVALID_DATE_RANGE` |
| `from=2026-13-01` (파싱 실패) | 400 `VALIDATION_FAILED`, `errors[0]` = `{field:"from", code:"TypeMismatch"}` |
| `size=0` / `size=101` / `size=abc` | 400 `VALIDATION_FAILED`, `errors[0].code` = `"Min"` / `"Max"` / `"TypeMismatch"`, `field` = `"size"` |

검사 순서: 경로 `{number}` 형식 → 쿼리 파라미터 형식(`size`, `from`, `to`) → 계좌 존재(404) → 기간 → 커서.

### 5. 핵심 시그니처

```java
public interface CursorCodec {
    String encode(TransactionCursor cursor);
    TransactionCursor decode(String encoded);   // 거절 조건이면 예외 → 400 INVALID_CURSOR
}
```

`TransactionCursor`의 필드와 조회 서비스의 메서드는 직접 설계한다.

## 테스트 시나리오
`@SpringBootTest` + `@AutoConfigureMockMvc`, 테스트용 `Clock`. 조회 시점의 `Clock`은 `2026-11-10T14:30:00+09:00`. `A`는 테스트마다 새로 만든 KRW 계좌.
"25건 준비" = `Clock`을 `2026-11-01T09:00:00+09:00`부터 1분씩 앞으로 옮기며 `A`에 1,000원씩 25번 입금(i = 0..24, i번째 거래 시각 09:i분, `balanceAfter` = (i+1) × 1,000).

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 25건 준비 | `GET /accounts/A/transactions` | `200`, `$.items.length()` = `20`, `$.items[0].occurredAt` = `"2026-11-01T09:24:00"`, `$.items[0].balanceAfter.amount` = `"25000"`, `$.items[19].balanceAfter.amount` = `"6000"`, `$.nextCursor` ≠ `null` |
| 2 | 1번 이후 | `GET ...?cursor={1번 nextCursor}` | `200`, `items.length()` = `5`, `items[0].balanceAfter.amount` = `"5000"`, `items[4].balanceAfter.amount` = `"1000"`, `$.nextCursor` = `null`. 1·2번 `transactionId` 25개가 모두 다름 |
| 3 | 1번 이후 `Clock`을 `2026-11-01T09:25:00`으로 옮겨 1,000원 입금, 조회 시점 `Clock`으로 복귀 | 2번과 같은 요청 | 2번과 같은 5건 (`balanceAfter` 5000, 4000, 3000, 2000, 1000) |
| 4 | 25건 준비 | `size=100` | `items.length()` = `25`, `nextCursor` = `null` |
| 5 | 25건 준비 | `size=25` | `items.length()` = `25`, `nextCursor` = `null` (`size + 1`건 조회로 판정) |
| 6 | 25건 준비 | `size=24` → 다음 페이지 | 첫 페이지 24건 + `nextCursor` ≠ `null`, 다음 페이지 1건(`balanceAfter` `"1000"`) + `nextCursor` = `null` |
| 7 | `Clock`을 `2026-11-01T10:00:00`에 고정하고 `A`에 1,000원 3번 입금 (시각이 모두 같음) | `size=2` → 다음 페이지 | 첫 페이지 2건, 둘째 페이지 1건, `transactionId` 3개 모두 다름, 첫 페이지 2개 ID가 둘째 페이지 ID보다 문자열 비교로 큼 |
| 8 | `A`에 `2026-10-31T23:59:59`, `2026-11-01T23:59:59`, `2026-11-02T00:00:00` 입금 | `from=2026-11-01&to=2026-11-01` | `items.length()` = `1`, `items[0].occurredAt` = `"2026-11-01T23:59:59"` |
| 9 | 거래 없는 `A` | 파라미터 없음 | `200`, `$.items` = `[]`, `$.nextCursor` = `null` |
| 10 | 없음 | `GET /accounts/110-9999-0000/transactions` | `404`, `$.code` = `"ACCOUNT_NOT_FOUND"` |
| 11 | `A` | `from=2026-11-02&to=2026-11-01` | `400`, `$.code` = `"INVALID_DATE_RANGE"` |
| 12 | `A` | `from=2025-11-10&to=2026-11-10` (365일) | `200` |
| 13 | `A` | `from=2025-11-09&to=2026-11-10` (366일) | `400`, `$.code` = `"INVALID_DATE_RANGE"` |
| 14 | `A` | `from=2026-11-11` (`to` 생략 → 2026-11-10) | `400`, `$.code` = `"INVALID_DATE_RANGE"` |
| 15 | `A` | `size=0` | `400`, `$.errors[0].field` = `"size"`, `$.errors[0].code` = `"Min"` |
| 16 | `A` | `size=101` | `400`, `$.errors[0].code` = `"Max"` |
| 17 | `A` | `size=abc` | `400`, `$.errors[0].code` = `"TypeMismatch"` |
| 18 | `A` | `from=2026-13-01` | `400`, `$.errors[0].field` = `"from"`, `$.errors[0].code` = `"TypeMismatch"` |
| 19 | `A` | `cursor=!!!` | `400`, `$.code` = `"INVALID_CURSOR"` |
| 20 | `A` | `cursor` = Base64 URL(`"hello"`) = `aGVsbG8` | `400`, `$.code` = `"INVALID_CURSOR"` |
| 21 | `A`·`B` 모두 25건 준비 | `GET /accounts/B/transactions?cursor={A의 1번 nextCursor}` | `400`, `$.code` = `"INVALID_CURSOR"` |
| 22 | 1번 이후 | `?cursor={1번 nextCursor}&from=2026-11-01` (커서 안의 `from`은 `2026-10-11`) | `400`, `$.code` = `"INVALID_CURSOR"` |
| 23 | 1번 이후 | `cursor` = Base64 URL(`"v2\|"` + 1번 커서를 디코딩한 문자열의 4번째 문자부터) | `400`, `$.code` = `"INVALID_CURSOR"` |

계산: 1번 `items[19]`는 i = 24 − 19 = 5 → (5+1) × 1,000 = 6,000. 2번 `items[0]`은 i = 4 → 5,000. 13번 2025-11-09 ~ 2026-11-10은 366일(2026년 2월은 28일). 14번 기본 `from`은 2026-11-10 − 30일 = 2026-10-11이지만 `from`을 직접 보냈으므로 `from` = 2026-11-11 > `to` = 2026-11-10.

## 제약
- 오프셋(`page`, `offset`) 파라미터를 만들지 않는다.
- 커서에 계좌 소유자 이름·잔액을 넣지 않는다. Base64는 암호화가 아니라 누구나 디코딩할 수 있다.
- 매 요청마다 계좌의 전체 거래를 정렬한 복사본을 만드는 것은 이 미션(메모리 저장소)에서는 허용한다. 대신 TIL에 Phase 5에서 바꿔야 할 지점으로 적는다.

## 힌트
<details>
<summary>힌트 1: 오프셋 방식과 비교표 만들기</summary>

시나리오 3 상황에서 오프셋 방식(`skip(20).limit(20)`)이었다면 두 번째 페이지 첫 항목의 `balanceAfter`는 얼마인가? 새 거래(26,000)가 맨 앞에 끼어 모든 항목이 한 칸 밀렸다. TIL 표의 열: "방식 / 2페이지 항목의 balanceAfter 목록 / 중복된 거래 / 누락된 거래".
</details>

## 완료 기준
- [ ] `./gradlew test --tests "*TransactionQuery*"`에서 시나리오 23개에 해당하는 테스트가 통과한다.
- [ ] `til/phase-4/M4-5-pagination.md`에 커서 vs 오프셋 비교표(힌트 1의 4열)가 있다.
- [ ] 서버를 띄우고 `curl`로 첫 페이지와 `nextCursor`를 넣은 둘째 페이지를 받은 출력이 같은 TIL에 있다.

## 생각해볼 질문
1. 정렬 키에서 `transactionId`를 빼고 `occurredAt`만 쓰면 시나리오 7에서 어떤 거래가 누락되거나 중복되나? 구체적인 3건으로 예를 든다.
2. 이 커서는 형식만 맞으면 다른 위치를 가리키도록 직접 만들어 보낼 수 있다(본인 계좌 안에서). 이것이 보안 문제인가? HMAC 서명을 붙이면 무엇을 막을 수 있고, 키 교체 시 무엇이 깨지나?
3. Phase 5에서 MySQL로 옮기면 "다음 페이지 조건"은 `WHERE (occurred_at, id) < (?, ?) ORDER BY occurred_at DESC, id DESC LIMIT ?`가 된다. 이 쿼리가 빠르려면 어떤 컬럼 순서의 인덱스가 필요한가? 오프셋 `LIMIT 20 OFFSET 100000`과 읽는 행 수를 비교한다.
