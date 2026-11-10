# M4-8 API 테스트와 요청 추적 로그

> 가이드 수준: L2 · 예상 시간: 4~5h · 선행: M4-7

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 엔드포인트 10개의 성공·실패 응답 40종 이상을 `@WebMvcTest` 슬라이스 테스트로 검증하고, 모든 오류 응답이 `ProblemDetail` 6개 필드를 가짐을 공통 검증 메서드 하나로 확인한다.
- `@WebMvcTest`와 `@SpringBootTest` 테스트 클래스의 실행 시간을 Gradle 테스트 리포트에서 읽어 표로 비교한다.
- 모든 응답(401·500 포함)에 `X-Request-Id` 헤더를 넣고, 같은 값이 그 요청의 모든 로그 줄에 찍힘을 `OutputCaptureExtension`으로 보여준다.
- 요청이 끝난 뒤 MDC가 비워짐을 테스트로 보여준다.

## 배경
운영 중 고객이 "이체가 실패했다"고 문의하면, 상담원은 수많은 로그 중 그 요청의 로그만 찾아야 한다. 요청마다 ID를 붙여 응답 헤더로 돌려주고 모든 로그에 같은 ID를 찍으면, 고객 화면(또는 앱 로그)의 ID 하나로 서버 로그를 바로 찾는다.
MDC는 스레드 로컬에 값을 둔다. 요청이 끝날 때 지우지 않으면 Tomcat 스레드가 재사용될 때 다음 요청 로그에 이전 요청의 ID가 찍혀, 엉뚱한 고객의 로그를 보고 원인을 판단하게 된다.
M4-1~M4-7의 테스트는 전부 `@SpringBootTest`로 실제 서비스까지 실행했다. 이 미션은 서비스를 mock으로 바꾼 슬라이스 테스트로 웹 계층(매핑, 검증, 직렬화, 오류 변환, 보안)만 따로 검증한다.

## 요구사항

### 1. `@WebMvcTest` 슬라이스 테스트
- 컨트롤러마다 테스트 클래스 1개: `@WebMvcTest(AccountController.class)` 형식, 패키지는 `lab.bank.web.slice`. `@WebMvcTest`의 패키지는 `org.springframework.boot.webmvc.test.autoconfigure` (Spring Boot 4, `spring-boot-starter-webmvc-test`).
- 서비스·멱등 처리 빈·조회 빈은 `@MockitoBean`(`org.springframework.test.context.bean.override.mockito`)으로 바꾼다. Spring Boot 4에서 `@MockBean`은 제거되었다.
- `@WebMvcTest`는 `@Controller`, `@ControllerAdvice`, `@JacksonComponent`, `Filter`, `WebMvcConfigurer`, `HandlerMethodArgumentResolver` 등만 등록하고 일반 `@Component`·`@Configuration`은 등록하지 않는다. `SecurityConfig`, `UserDetailsService` 설정, M4-3의 `ProblemDetail` 생성 빈처럼 필요한 것은 `@Import`로 넣는다. 사용자 프로퍼티는 `@EnableConfigurationProperties`로 넣는다.
- 인증: 401 테스트는 인증 정보 없이 또는 `httpBasic("alice","wrong")`으로 보낸다(실제 필터 체인 확인). 그 밖의 테스트는 `with(user("alice").roles("USER"))` 또는 `@WithMockUser(username = "alice", roles = "USER")`를 쓴다.
- 모든 오류 응답 검증은 공통 메서드 1개(예: `assertProblem(result, status, code)`)를 거친다. 이 메서드는 `Content-Type`이 `application/problem+json`과 호환되는지, `type`·`title`·`status`·`detail`·`instance`·`code` 6개 필드가 모두 있는지, `status`·`code`가 기대값인지, `type`이 M4-3 규칙(`urn:problem-type:lab-bank:` + code 변환)과 같은지 확인한다.

### 2. 최소 검증 범위 (엔드포인트 × 상태)

| 엔드포인트 | 검증할 상태 (각각 테스트 1개 이상) | 개수 |
|---|---|---|
| `GET /health` | 200 | 1 |
| `POST /accounts` | 201, 400, 401 | 3 |
| `GET /accounts/{number}` | 200, 400, 401, 404 | 4 |
| `POST /accounts/{number}/deposits` | 200, 400, 401, 404, 409, 422 | 6 |
| `POST /accounts/{number}/withdrawals` | 200, 400, 401, 404, 409, 422 | 6 |
| `POST /ops/accounts/{number}/freeze` | 200, 401, 403, 409 | 4 |
| `POST /ops/accounts/{number}/unfreeze` | 200, 409 | 2 |
| `POST /transfers` | 201, 400, 401, 404, 409, 422, 503 | 7 |
| `GET /transfers/{transferId}` | 200, 401, 404 | 3 |
| `GET /accounts/{number}/transactions` | 200, 400, 401, 404 | 4 |
| 합계 | | 40 |

- 404·409·422·503은 mock 서비스가 해당 도메인 예외를 던지게 해서 만든다. 예: 출금 422는 mock이 `InsufficientBalanceException`을 던진다.
- 성공 테스트는 응답 JSON의 모든 필드를 검증한다(금액은 문자열, 시각은 `+09:00` 오프셋).
- mock 호출 인자 검증: 성공 테스트마다 서비스가 기대한 인자(계좌번호, `Money`, 요청자 username)로 정확히 1번 호출됐는지 `verify`로 확인한다. 400·401·403 테스트에서는 서비스가 한 번도 호출되지 않았는지 `verifyNoInteractions`로 확인한다.

### 3. `RequestIdFilter`

| 항목 | 규칙 |
|---|---|
| 클래스 | `lab.bank.web.filter.RequestIdFilter extends OncePerRequestFilter` |
| 순서 | Spring Security 필터 체인보다 먼저 실행 (`Ordered.HIGHEST_PRECEDENCE`). Spring Boot가 등록하는 Security 필터의 기본 순서는 `-100`이다 |
| 입력 헤더 | `X-Request-Id`. 값이 정규식 `^[A-Za-z0-9._-]{1,64}$`와 일치하면 그대로 쓴다 |
| 생성 | 헤더가 없거나, 빈 값이거나, 정규식과 다르면 `UUID.randomUUID().toString()`으로 새로 만든다 (거절하지 않는다) |
| 응답 헤더 | `X-Request-Id`에 위 값을 넣는다. `filterChain.doFilter` 호출 **전**에 설정한다(응답이 커밋된 뒤에는 헤더를 추가할 수 없다) |
| MDC | 키 `requestId`. `doFilter` 전에 넣고 `finally`에서 `MDC.remove("requestId")` |
| 완료 로그 | `finally`에서 INFO 1줄: `요청 완료 method={메서드} path={경로} status={상태} elapsedMs={밀리초}`. 경로 안의 계좌번호(`[0-9]{3}-[0-9]{4}-[0-9]{4}`)는 `110-****-0001` 형식으로 마스킹 |

`application.yml`에 로그 패턴을 추가한다:

```yaml
logging:
  pattern:
    console: "%d{yyyy-MM-dd'T'HH:mm:ss.SSSXXX} %5p [%X{requestId:-no-request}] %logger{36} : %m%n"
```

## 테스트 시나리오
2절 표의 40개는 표 자체가 시나리오다. 아래는 `RequestIdFilter` 시나리오다. `@WebMvcTest`(필터는 `Filter` 타입이라 자동 등록된다) + `@ExtendWith(OutputCaptureExtension.class)`.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 없음 | `X-Request-Id` 없이 `GET /health` | 응답 `X-Request-Id`가 `^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`와 일치 |
| 2 | 없음 | `X-Request-Id: abc-123` | 응답 `X-Request-Id` = `abc-123` |
| 3 | 없음 | `X-Request-Id:` 64자 (`a` × 64) | 응답 값 = 입력 값 |
| 4 | 없음 | `X-Request-Id:` 65자 (`a` × 65) | 응답 값 ≠ 입력 값, 1번의 UUID 정규식과 일치 |
| 5 | 없음 | `X-Request-Id: <script>` / `X-Request-Id: abc 123` / 빈 값 | 3건 모두 응답 값이 UUID 정규식과 일치 |
| 6 | 없음 | 헤더 없이 2번 요청 | 두 응답의 `X-Request-Id`가 다름 |
| 7 | 없음 | 인증 없이 `GET /accounts/110-0000-0001`, `X-Request-Id: req-401` | `401`, 응답 `X-Request-Id` = `req-401` |
| 8 | 테스트 전용 컨트롤러 `GET /test/boom` (M4-3 시나리오 16) | `X-Request-Id: req-500` | `500`, 응답 `X-Request-Id` = `req-500`, 캡처한 출력에서 `ERROR`가 포함된 줄에 `[req-500]` 포함 |
| 9 | 없음 | `X-Request-Id: req-mdc`로 요청 1번 | 요청이 끝난 뒤 테스트 스레드에서 `MDC.get("requestId")` = `null` |
| 10 | 없음 | `X-Request-Id: first-id`로 요청 → 같은 테스트에서 헤더 없이 요청 | 캡처한 출력 중 두 번째 요청의 "요청 완료" 줄에 `first-id` 미포함 |
| 11 | mock 서비스가 계좌 반환 | `X-Request-Id: req-mask`, `GET /accounts/110-0000-0001` | "요청 완료" 줄에 `[req-mask]`, `path=/accounts/110-****-0001`, `status=200` 포함, `110-0000-0001` 미포함 |
| 12 | 없음 | `X-Request-Id: req-405`, `DELETE /accounts/110-0000-0001` | 응답 `X-Request-Id` = `req-405`, "요청 완료" 줄에 `status=405` |

MockMvc는 요청을 테스트 스레드에서 실행하므로 시나리오 9·10으로 같은 스레드의 MDC 정리를 확인할 수 있다.

## 제약
- 슬라이스 테스트에서 `@SpringBootTest`를 쓰지 않는다. 슬라이스 테스트 클래스에서 실제 `BankService`·`TransferEngine`이 생성되면 안 된다(mock만).
- MDC 값을 `finally` 밖에서 지우지 않는다. 예외가 나도 지워져야 한다.
- 로그에 전체 계좌번호, 비밀번호, `Authorization` 헤더 값을 남기지 않는다.
- `Thread.sleep`으로 로그 출력 순서를 맞추지 않는다.

## 힌트
<details>
<summary>힌트 1: 로그 캡처</summary>

`OutputCaptureExtension`(`org.springframework.boot.test.system`)을 붙이면 테스트 메서드 파라미터로 `CapturedOutput`을 받을 수 있다. `getOut()` 문자열을 줄 단위로 나눠 "요청 완료"가 포함된 줄만 골라 검사한다. 캡처는 콘솔 출력 기준이므로 2절의 `logging.pattern.console`이 테스트에도 적용되는지 확인한다.
</details>

## 완료 기준
- [ ] `./gradlew test`가 통과하고, `@WebMvcTest` 클래스의 테스트 수 합계가 2절 표의 40 + 이 미션의 시나리오 12 = 52 이상이다 (`build/reports/tests/test/index.html`에서 확인).
- [ ] `til/phase-4/M4-8-test-timing.md`에 "테스트 클래스 / 종류(`@WebMvcTest`·`@SpringBootTest`) / 테스트 수 / 실행 시간(초)" 4열 표가 있다. 값은 `./gradlew test --rerun-tasks` 1회 실행 후 Gradle 테스트 리포트에서 옮긴다.
- [ ] 서버를 띄우고 `curl -v -H "X-Request-Id: demo-1" -u alice:alice-pass-1234 localhost:8080/accounts/110-0000-0001` 출력의 `< X-Request-Id: demo-1`과, 같은 ID가 찍힌 서버 로그 줄이 같은 TIL에 있다.
- [ ] `grep -rnE "@MockBean|@SpringBootTest" src/test/java/lab/bank/web/slice` 결과가 0줄이다.

## 생각해볼 질문
1. 2절 40개 테스트에서 mock 서비스가 던진 예외와 실제 서비스가 던지는 예외가 달라지면(예: 실제로는 `CurrencyMismatchException`을 먼저 던짐) 슬라이스 테스트는 통과하고 운영에서는 다른 응답이 나간다. `@SpringBootTest` 통합 테스트와 슬라이스 테스트를 각각 어떤 비율로, 무엇을 검증하는 데 쓸지 자기 기준을 적는다.
2. 클라이언트가 보낸 `X-Request-Id`를 그대로 믿으면 생기는 문제는 무엇인가? (같은 ID를 일부러 반복해서 보내는 경우, 로그 주입) 이 미션의 정규식이 막는 것과 막지 못하는 것을 구분한다.
3. 이 필터의 요청 ID는 이 서버 안에서만 이어진다. Phase 8에서 계좌 서비스 → 주문 서비스로 HTTP·Kafka 호출이 이어질 때 같은 ID를 넘기려면 무엇이 필요한가? W3C Trace Context의 `traceparent` 헤더와 비교한다.
4. 이 Phase의 모든 데이터(계좌, 거래, 멱등 키)는 메모리에 있어 서버를 재시작하면 사라진다. 재시작 직후 클라이언트가 M4-4의 키로 재시도하면 무슨 일이 생기나? Phase 5에서 DB로 옮길 때 어떤 테이블과 제약(유니크 키)이 필요한지 목록으로 적는다.
