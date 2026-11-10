# Phase 4: Spring Web, API 설계, 보안 (3주)

> 가이드 수준: L2, 선행: Phase 3 완료, 이 Phase의 workspace 시작 방법: Phase 3 workspace 복사 + Spring MVC, Spring Security 스타터 추가

## 학습 목표
이 Phase를 끝내면 다음을 할 수 있다.
- `curl -v` 출력에서 요청 줄, 헤더, 상태 코드, 본문을 구분해 적고, 요청 하나가 `DispatcherServlet` → `HandlerMapping` → `HandlerAdapter` → `HandlerMethodArgumentResolver` → `HttpMessageConverter`를 거치는 순서를 DEBUG 로그 줄로 보여준다.
- 아래 엔드포인트 표의 API 10개(정지, 해제를 따로 셈)를 만들고, 모든 오류를 `ProblemDetail`(RFC 9457) + `code` 필드 형식으로 돌려주며, 400/401/403/404/409/422/503 중 어떤 상태를 쓸지 이 README 2절의 규칙표로 설명한다.
- 같은 `Idempotency-Key`로 이체 요청이 2번 와도 출금이 1번만 일어남을 테스트로 보여준다.
- 금액을 문자열로 직렬화하는 이유를 JavaScript `JSON.parse` 결과(9007199254740993 → 9007199254740992)로 보여준다.
- HTTP Basic + 상태 없는(stateless) `SecurityFilterChain`을 구성하고, 401, 403, 404(남의 계좌) 응답을 테스트로 구분한다.

## 이 Phase의 결과물
Phase 3의 도메인, 이체 엔진 빈 위에 HTTP API 계층이 올라간다. 저장소는 Phase 3와 같은 메모리 구현이다. DB는 Phase 5에서 붙인다.

```
phase-4-spring-web/workspace/
├── build.gradle.kts
├── src/main/resources/application.yml
├── src/main/java/lab/bank/
│   ├── common/ money/ account/ ledger/ interest/ application/ transfer/   # Phase 3에서 복사 (이름 유지)
│   ├── config/                  # TransferProperties(M3-6), Clock 빈
│   ├── web/
│   │   ├── HealthController.java              # M4-1
│   │   ├── AccountController.java             # M4-2
│   │   ├── OpsAccountController.java          # M4-3 (계좌 정지/해제)
│   │   ├── TransferController.java            # M4-4
│   │   ├── TransactionQueryController.java    # M4-5
│   │   ├── dto/                 # 요청, 응답 record (M4-2~M4-5)
│   │   ├── validation/          # @AccountNumberFormat, @ValidMoney (M4-2)
│   │   ├── error/               # GlobalExceptionHandler, WebErrorCode (M4-3)
│   │   ├── idempotency/         # IdempotencyStore (M4-4)
│   │   ├── pagination/          # 커서 인코딩 (M4-5)
│   │   ├── json/                # Money 직렬화기, 역직렬화기 (M4-6)
│   │   └── filter/              # RequestIdFilter (M4-8)
│   └── security/                # SecurityConfig, 401/403 응답 처리 (M4-7)
└── src/test/java/lab/bank/web/  # @SpringBootTest 통합 테스트(M4-1~M4-7), @WebMvcTest 슬라이스 테스트(M4-8)
```

Phase 4가 끝났을 때 있어야 하는 엔드포인트:

| 메서드 | 경로 | 미션 | 인증 |
|---|---|---|---|
| GET | `/health` | M4-1 | 없음 |
| POST | `/accounts` | M4-2 | USER |
| GET | `/accounts/{number}` | M4-2 | USER, 본인 계좌 |
| POST | `/accounts/{number}/deposits` | M4-2 | USER, 본인 계좌 |
| POST | `/accounts/{number}/withdrawals` | M4-2 | USER, 본인 계좌 |
| POST | `/ops/accounts/{number}/freeze`, `/unfreeze` | M4-3 | OPS |
| POST | `/transfers` | M4-4 | USER, 출금 계좌 본인 |
| GET | `/transfers/{transferId}` | M4-4 | USER, 이체 요청자 본인 |
| GET | `/accounts/{number}/transactions` | M4-5 | USER, 본인 계좌 |

## 핵심 개념 정리 (미션 전에 읽기)

### 1. HTTP 메시지의 구조
HTTP/1.1 메시지는 시작 줄, 헤더, 빈 줄, 본문 순서로 된 텍스트다(RFC 9112 2.1절).

```
POST /accounts/110-0000-0001/deposits HTTP/1.1      ← 요청 줄: 메서드, 대상, 버전
Host: localhost:8080                                ← 헤더
Content-Type: application/json                      ← 본문의 형식
Accept: application/json                            ← 받고 싶은 응답 형식
Content-Length: 58
                                                    ← 빈 줄
{"money":{"amount":"10000","currency":"KRW"},"memo":"급여"}

HTTP/1.1 200                                        ← 상태 줄 (Tomcat은 사유 구절을 보내지 않는다)
Content-Type: application/json
...
```

| 개념 | 금융 API에서 문제가 되는 지점 |
|---|---|
| 메서드의 안전성, 멱등성 (RFC 9110 9.2절) | GET, PUT, DELETE는 멱등, POST는 멱등이 아니다. 클라이언트가 타임아웃 후 POST 이체를 재시도하면 이중 출금이 된다 → M4-4 |
| `Content-Type` / `Accept` | 서버가 `Content-Type: application/json`이 아닌 본문을 받으면 415, `Accept`에 맞는 형식을 만들 수 없으면 406 |
| 상태 코드 | 클라이언트(앱, 다른 서버)는 본문보다 상태 코드로 먼저 분기한다. 잔액 부족을 200으로 돌려주면 재시도 로직이 잘못 동작한다 |

### 2. REST 리소스 설계와 상태 코드
리소스는 명사(`/accounts`, `/transfers`), 행위는 메서드로 표현한다. 입금처럼 "행위"로 보이는 것은 하위 리소스 생성(`POST /accounts/{number}/deposits`)으로 표현한다.

**이 레포의 상태 코드 규칙** (M4-3에서 코드로 만든다). 422와 409의 경계는 표준이 정하지 않는다. RFC 9110은 409를 "대상 리소스의 현재 상태와 충돌"(15.5.10절), 422를 "요청 내용의 형식은 맞지만 처리할 수 없음"(15.5.21절)으로만 정의한다. 아래 표는 이 레포의 팀 규칙이다.

| 상태 | 판단 기준 (위에서부터 먼저 해당하는 것) | 예 |
|---|---|---|
| 400 | 서버 데이터를 조회하지 않고 요청만 보고 판단할 수 있는 오류 | JSON 문법 오류, 필드 검증 실패, `Idempotency-Key` 누락, 같은 계좌로 이체, 위조된 커서 |
| 401 | 인증 정보가 없거나 틀림 | `Authorization` 헤더 없음, 비밀번호 틀림 |
| 403 | 인증은 됐지만 역할(role)이 부족함 | USER가 `/ops/**` 호출 |
| 404 | 리소스가 없거나, 있지만 요청자의 것이 아님 | 없는 계좌, 남의 계좌 (M4-7) |
| 409 | 리소스의 `status`(상태) 또는 처리 중인 다른 요청과 충돌 | `FROZEN` 계좌에 입금, 같은 키의 요청이 처리 중 |
| 422 | 형식, 상태는 문제없지만 서버 데이터(잔액, 한도, 통화, 저장된 멱등 요청)와 비교한 규칙 위반 | 잔액 부족, 1일 한도 초과, 통화 불일치, 같은 키에 다른 본문 |
| 503 | 일시적으로 처리 불가, 같은 요청을 재시도하면 성공할 수 있음 | 락 획득 3초 초과 |
| 500 | 위에 해당하지 않는 예상 못 한 예외 | `NullPointerException` |

성공 응답: 새 리소스를 만들고 그 리소스를 조회하는 URI가 있으면 `201 Created` + `Location` 헤더(RFC 9110 15.3.2절, 10.2.2절). 조회 URI가 없는 입금, 출금은 `200 OK`.

### 3. `DispatcherServlet`의 요청 처리 흐름
Spring MVC는 서블릿 하나(`DispatcherServlet`)가 모든 요청을 받아 아래 순서로 넘긴다.

| 순서 | 구성 요소 | 하는 일 | 이 Phase에서 쓰는 구현체 |
|---|---|---|---|
| 0 | 서블릿 필터 (`Filter`) | `DispatcherServlet` 앞에서 요청, 응답을 가로챈다 | Spring Security 필터 체인(M4-7), `RequestIdFilter`(M4-8) |
| 1 | `HandlerMapping` | URL, 메서드로 실행할 컨트롤러 메서드를 찾는다 | `RequestMappingHandlerMapping` |
| 2 | `HandlerAdapter` | 찾은 메서드를 호출할 방법을 안다 | `RequestMappingHandlerAdapter` |
| 3 | `HandlerMethodArgumentResolver` | 메서드 파라미터 값을 만든다 (`@PathVariable`, `@RequestHeader`, `@RequestBody`) | `PathVariableMethodArgumentResolver`, `RequestResponseBodyMethodProcessor` 등 |
| 4 | `HttpMessageConverter` | 본문 JSON ↔ 자바 객체 변환 | `JacksonJsonHttpMessageConverter` (Spring Framework 7, Jackson 3 기반) |
| 5 | `HandlerExceptionResolver` | 1~4에서 난 예외를 응답으로 바꾼다 | `@RestControllerAdvice`를 처리하는 `ExceptionHandlerExceptionResolver` (M4-3) |

Spring Boot 4는 Jackson 3를 쓴다. 패키지가 `com.fasterxml.jackson`에서 `tools.jackson`으로 바뀌었고, 애너테이션(`@JsonProperty` 등)만 `com.fasterxml.jackson.annotation` 패키지에 남았다. Spring Boot 3.x 기준 글(2025년 11월 Spring Boot 4.0 출시 전)의 Jackson 2 코드를 그대로 옮기면 컴파일되지 않는다.

### 4. 입력 검증 (Bean Validation)
요청 DTO(`record`)의 컴포넌트에 `@NotBlank`, `@Size`, `@Pattern` 같은 제약을 붙이고 `@Valid @RequestBody`로 받으면, 실패 시 `MethodArgumentNotValidException`이 난다.
`@PathVariable`, `@RequestParam`에 제약을 직접 붙이면 Spring Framework 6.1부터 내장 메서드 검증이 동작하고 `HandlerMethodValidationException`이 난다.

| 검증 위치 | 검사하는 것 | 실패 시 |
|---|---|---|
| Bean Validation (DTO) | 형식: 필수값, 길이, 패턴, 금액 소수 자리 | 400 `VALIDATION_FAILED` |
| 도메인 (`Account`, `TransferEngine`) | 상태, 잔액, 한도 | 409 / 422 |

도메인 검증을 컨트롤러로 옮기지 않는다. 컨트롤러는 "DTO → 도메인 호출 → 응답 DTO" 변환만 한다. 같은 규칙이 Phase 5에서 배치, 메시지 컨슈머 등 HTTP가 아닌 입구에서도 지켜져야 하기 때문이다.

### 5. `ProblemDetail` (RFC 9457)
RFC 9457(2023)은 RFC 7807을 대체한 HTTP API 오류 응답 형식이다. 미디어 타입은 `application/problem+json`이다.

| 멤버 | 의미 (RFC 9457 3.1절) | 이 레포의 값 |
|---|---|---|
| `type` | 문제 유형을 식별하는 URI | `urn:problem-type:lab-bank:{code를 소문자, 하이픈으로}` 예: `urn:problem-type:lab-bank:insufficient-balance` |
| `title` | 유형의 짧은 요약, 같은 유형이면 항상 같은 값 | `잔액 부족` |
| `status` | HTTP 상태 코드 (숫자) | `422` |
| `detail` | 이번 발생 건의 설명 | `잔액이 부족합니다. 계좌 110-****-0001` |
| `instance` | 이번 발생 건을 가리키는 URI | 요청 경로 `/accounts/110-0000-0001/withdrawals` |
| `code` (확장 멤버, 3.2절) | 클라이언트가 분기에 쓰는 기계용 코드 | `INSUFFICIENT_BALANCE` |

Spring의 `ProblemDetail` 클래스는 `setProperty("code", ...)`로 넣은 확장 멤버를 JSON 최상위 필드로 쓴다.

### 6. 멱등성과 `Idempotency-Key`
네트워크가 끊겨 클라이언트가 응답을 못 받았을 때, 이체가 실행됐는지 클라이언트는 알 수 없다. 재시도하면 이중 출금 위험이 있고, 안 하면 이체 누락 위험이 있다.
클라이언트가 요청마다 고유 키를 헤더에 넣고, 서버는 키별로 첫 응답을 저장해 두었다가 같은 키의 재시도에는 저장된 응답을 다시 보낸다.

IETF httpapi 워킹그룹의 Internet-Draft "The Idempotency-Key HTTP Header Field"(draft-ietf-httpapi-idempotency-key-header-08, 2026-10-22, RFC 아님)가 이 헤더를 정의한다. 드래프트 2.7절의 권고: 헤더 누락 400, 같은 키에 다른 본문 422, 처리 중인 키로 재요청 409. 이 레포는 이 권고를 그대로 따른다(M4-4).
Phase 2 `TransferEngine`의 `requestId` 멱등성은 "한 JVM 안에서 같은 이체를 두 번 실행하지 않는다"까지만 보장한다. HTTP 계층에서는 "같은 응답(상태 코드 + 본문)을 다시 준다"와 "다른 본문으로 키를 재사용하면 거절한다"가 추가로 필요하다.

### 7. Spring Security 필터 체인
Spring Security는 서블릿 필터 하나(`DelegatingFilterProxy` → `FilterChainProxy`)로 들어와, 요청 경로에 맞는 `SecurityFilterChain`의 필터들을 순서대로 실행한다. 컨트롤러에 도달하기 전에 인증(누구인가)과 인가(할 수 있는가)가 끝난다.

```
요청 → [RequestIdFilter] → FilterChainProxy
          └ SecurityFilterChain: ... → BasicAuthenticationFilter → ... → ExceptionTranslationFilter → AuthorizationFilter
       → DispatcherServlet → 컨트롤러
```

| 상황 | 처리하는 곳 | 응답 |
|---|---|---|
| 인증 정보 없음/틀림 | `ExceptionTranslationFilter` → `AuthenticationEntryPoint` | 401 + `WWW-Authenticate` 헤더 |
| 인증됐지만 권한 부족 | `ExceptionTranslationFilter` → `AccessDeniedHandler` | 403 |
| 남의 계좌 | 컨트롤러 뒤 서비스 계층의 소유자 검사 | 404 |

401, 403은 `DispatcherServlet` 앞에서 결정되므로 `@RestControllerAdvice`가 처리하지 못한다. M4-7에서 두 핸들러가 직접 `ProblemDetail` JSON을 쓴다.
Spring Security 7은 `HttpSecurity`의 `and()`와 `authorizeRequests()`를 제거했다. 람다 DSL(`http.csrf(csrf -> ...)`)과 `authorizeHttpRequests`만 쓴다.

## 워크스페이스 만들기
레포 루트에서 실행한다.

```bash
cp -R phase-3-spring-core/workspace/. phase-4-spring-web/workspace/
cd phase-4-spring-web/workspace
./gradlew test   # Phase 3 테스트가 모두 통과하는지 먼저 확인
```

`settings.gradle.kts`의 `rootProject.name`을 `"phase-4-spring-web"`으로 바꾼다. `build.gradle.kts`의 Spring Boot 플러그인 버전은 Phase 3와 같은 4.1.x(2026-11-10 기준 최신 4.1.2)를 유지하고, `dependencies` 블록을 아래로 바꾼다.

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webmvc")      // Spring MVC + Tomcat + Jackson 3
    implementation("org.springframework.boot:spring-boot-starter-validation")  // Bean Validation (Hibernate Validator)
    implementation("org.springframework.boot:spring-boot-starter-aspectj")     // Phase 3 M3-5 AuditAspect(@Aspect)가 계속 컴파일되도록 유지
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")   // Phase 3 M3-6 설정 메타데이터
    // M4-7에서 추가: implementation("org.springframework.boot:spring-boot-starter-security")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.boot:spring-boot-starter-webmvc-test")  // @WebMvcTest, @AutoConfigureMockMvc
    testImplementation("org.springframework.boot:spring-boot-starter-validation-test")
    // M4-7에서 추가: testImplementation("org.springframework.boot:spring-boot-starter-security-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
```

Spring Boot 4.0에서 `spring-boot-starter-web`은 `spring-boot-starter-webmvc`로 이름이 바뀌었다. 테스트 지원도 기술별 모듈로 나뉘어, `@WebMvcTest`, `@AutoConfigureMockMvc`는 `spring-boot-starter-webmvc-test`를 추가해야 쓸 수 있다(패키지 `org.springframework.boot.webmvc.test.autoconfigure`).
Phase 3에 `spring-boot-starter` 의존성이 있었다면 지운다. `spring-boot-starter-webmvc`가 포함한다. `spring-boot-starter-aspectj`는 지우지 않는다. `aspectjweaver`(`@Aspect` 애너테이션 포함)를 가져오는 스타터는 이것뿐이라, 지우면 M3-5의 `AuditAspect`가 컴파일되지 않는다 (Boot 4.1.2 `./gradlew dependencies`로 확인).
Spring Security 스타터는 M4-7에서 추가한다. 처음부터 넣으면 Spring Boot 기본 설정이 모든 경로에 인증을 요구해서 M4-1~M4-6의 모든 요청에 비밀번호가 필요해진다.

`src/main/resources/application.yml`에 추가한다 (Phase 3 설정은 유지):

```yaml
server:
  port: 8080
spring:
  jackson:
    time-zone: Asia/Seoul
logging:
  level:
    org.springframework.web: INFO   # M4-1 관찰할 때만 DEBUG로 바꾼다
```

## 주차별 계획
| 주 | 미션 | 개념 학습 범위 |
|---|---|---|
| 1주 (12~15h) | M4-1, M4-2, M4-3 | 이 README 1~5절, RFC 9110 9.2, 15절, Spring MVC 레퍼런스 "DispatcherServlet", "Annotated Controllers", "Validation", "Error Responses" |
| 2주 (9~12h) | M4-4, M4-5 | 이 README 6절, Idempotency-Key 드래프트 2절 전체 |
| 3주 (12~15h) | M4-6, M4-7, M4-8 | Jackson 3 마이그레이션 가이드, 이 README 7절, Spring Security 레퍼런스 "Servlet Applications > Architecture", "Authentication > Username/Password > Basic", "Testing" |

## 미션
| 미션 | 주제 | 예상 시간 |
|---|---|---|
| [M4-1](missions/M4-1-http-first-controller.md) | HTTP와 첫 컨트롤러 | 3~4h |
| [M4-2](missions/M4-2-account-api-validation.md) | 계좌 API와 입력 검증 | 5~6h |
| [M4-3](missions/M4-3-error-response.md) | 에러 응답 표준화 | 4~5h |
| [M4-4](missions/M4-4-transfer-api-idempotency.md) | 이체 API와 `Idempotency-Key` | 5~7h |
| [M4-5](missions/M4-5-transaction-history-pagination.md) | 거래내역 조회와 커서 페이지네이션 | 4~5h |
| [M4-6](missions/M4-6-money-serialization.md) | 금액, 날짜 직렬화 | 3~4h |
| [M4-7](missions/M4-7-spring-security.md) | Spring Security 인증, 인가 | 5~6h |
| [M4-8](missions/M4-8-api-test-request-tracing.md) | API 테스트와 요청 추적 로그 | 4~5h |

합계 33~42h (주 12h 기준 3주).

## 읽을거리
- RFC 9110 HTTP Semantics: 9.2(안전, 멱등 메서드), 9.3.1(GET), 9.3.3(POST), 10.2.2(`Location`), 11.6.1(`WWW-Authenticate`), 15.3.2(201), 15.5.1(400), 15.5.2(401), 15.5.4(403), 15.5.5(404), 15.5.10(409), 15.5.16(415), 15.5.21(422), 15.6.4(503)
- RFC 9112 HTTP/1.1: 2.1(메시지 형식), 3(요청 줄)
- RFC 9457 Problem Details for HTTP APIs: 3(멤버 정의), 3.2(확장 멤버), 4(새 문제 유형 정의)
- draft-ietf-httpapi-idempotency-key-header-08: 2.1~2.7절
- Spring Framework Reference, "Web on Servlet Stack > Spring Web MVC": "DispatcherServlet"(Special Bean Types, Processing), "Annotated Controllers"(Request Mapping, Handler Methods, Validation), "Error Responses", "Filters"
- Spring Boot Reference, "Testing > Testing Spring Boot Applications": "Auto-configured Spring MVC Tests", "Testing With a Mock Environment"
- Spring Boot Wiki, "Spring Boot 4.0 Migration Guide": Starters, Jackson 3, `@MockBean` 제거 절
- Spring Security Reference (7.x), "Servlet Applications > Architecture", "Servlet Applications > Authentication > Username/Password > Reading the Username & Password > Basic", "Password Storage", "Servlet Applications > Testing > MockMvc Support"
- Jackson 3.0 릴리스 노트 (jackson-databind 3.0): 패키지 변경, 기본값 변경 목록

## 완료 기준
- [ ] `./gradlew test`가 통과하고, M4-1~M4-8 문서의 테스트 시나리오가 전부 테스트 메서드로 있다.
- [ ] 위 엔드포인트 표의 10개 엔드포인트를 `curl`로 호출한 요청, 응답 기록이 `til/phase-4/` 아래 있다.
- [ ] 모든 오류 응답이 `Content-Type: application/problem+json`이고 `type`, `title`, `status`, `detail`, `instance`, `code` 6개 필드를 가진다 (M4-8 테스트로 확인).
- [ ] 컨트롤러 클래스에 `if`로 잔액, 상태, 한도를 검사하는 코드가 없다 (도메인으로 위임).
- [ ] 도메인 클래스(`Account`, `Transaction`)를 컨트롤러 반환 타입으로 쓰지 않는다. `grep -rnE "public Account |ResponseEntity<Account>" src/main/java/lab/bank/web` 결과가 0줄이다.
- [ ] [레벨 진단](../docs/self-check.md) Phase 4 항목을 말로 설명할 수 있다
