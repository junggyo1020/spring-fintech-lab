# M4-7 Spring Security 인증, 인가

> 가이드 수준: L2, 예상 시간: 5~6h, 선행: M4-4

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- Spring Security 7의 람다 DSL로 `SecurityFilterChain` 빈 1개를 구성하고, HTTP Basic, stateless 세션, CSRF 비활성화 각각의 근거를 TIL에 적는다.
- 401(인증 실패), 403(역할 부족), 404(남의 계좌)를 각각 재현하는 테스트를 작성하고, 남의 계좌 응답이 없는 계좌 응답과 `status`, `code`, `title`이 같음을 보여준다.
- 비밀번호를 `{bcrypt}` 접두사가 붙은 해시로만 저장하고, 평문 비밀번호가 `src/main`에 없음을 `grep`으로 보여준다.
- 멱등 키 범위를 (사용자, 키)로 바꿔, 두 사용자가 같은 키를 써도 서로의 응답이 재전송되지 않음을 테스트로 보여준다.

## 배경
M4-6까지의 API는 계좌번호만 알면 누구나 남의 잔액을 보고 출금할 수 있다. 계좌번호는 통장 사본, 이체 확인증에 그대로 적혀 다니는 정보다.
인증(누구인가)과 인가(그 계좌를 다룰 수 있는가)가 없으면 계좌번호를 1부터 차례로 넣어 보는 공격만으로 모든 계좌의 잔액이 드러난다.
남의 계좌에 403을 주면 "그 번호의 계좌가 존재한다"는 사실이 새어 나간다. 이 레포는 남의 계좌를 없는 계좌와 똑같이 404로 응답해 계좌 존재 여부를 숨긴다.
M4-4의 이체 API와 멱등 키를 사용자 단위로 나누고, M4-3의 오류 형식을 401, 403에도 쓴다.

## 요구사항

### 1. 의존성 (README "워크스페이스 만들기"의 주석을 푼다)

```kotlin
implementation("org.springframework.boot:spring-boot-starter-security")
testImplementation("org.springframework.boot:spring-boot-starter-security-test")
```

Spring Boot 4에서 `@WithMockUser`와 `SecurityMockMvcRequestPostProcessors`는 `spring-boot-starter-security-test`가 있어야 동작한다.

### 2. 사용자 (메모리, 이 레포의 테스트용 계정)

| username | 평문 비밀번호 (테스트 코드에서만 사용) | 역할 |
|---|---|---|
| `alice` | `alice-pass-1234` | `USER` |
| `bob` | `bob-pass-1234` | `USER` |
| `ops` | `ops-pass-1234` | `OPS` |

- `application.yml`에 `lab.security.users[*].username`, `password`, `roles`로 넣는다. `password`는 `{bcrypt}$2a$10$...` 형식의 해시만 넣는다. 해시는 `PasswordEncoderFactories.createDelegatingPasswordEncoder().encode("alice-pass-1234")`를 한 번 실행해 만든다.
- `PasswordEncoder` 빈은 `PasswordEncoderFactories.createDelegatingPasswordEncoder()`(`DelegatingPasswordEncoder`, 새 비밀번호를 `{bcrypt}`로 인코딩)를 쓴다. `{noop}`을 쓰지 않는다.
- `UserDetailsService` 빈은 위 프로퍼티로 `InMemoryUserDetailsManager`를 만든다. `User.withDefaultPasswordEncoder()`를 쓰지 않는다(평문이 코드에 남는다).

### 3. `SecurityFilterChain` (핵심 시그니처만 제공)

```java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception
```

| 설정 | 값 | 근거 (TIL에 자기 말로 다시 적는다) |
|---|---|---|
| `authorizeHttpRequests` | `/health`, `/error` → `permitAll` / `/ops/**` → `hasRole("OPS")` / `/accounts/**`, `/transfers/**` → `hasRole("USER")` / 나머지 → `authenticated` | 경로별 역할 |
| `httpBasic` | 사용, realm `lab-bank`, 401 응답은 4절의 `AuthenticationEntryPoint` | 토큰 발급 서버 없이 요청마다 자격 증명을 보낸다 |
| `sessionManagement` | `SessionCreationPolicy.STATELESS` | 요청마다 인증하므로 서버에 세션을 만들지 않는다. 응답에 `Set-Cookie`가 없다 |
| `csrf` | 비활성화 | 아래 설명 |
| `formLogin`, `logout` | 설정하지 않음 (비활성) | 브라우저 로그인 화면이 없는 API |
| `exceptionHandling` | 4절의 `AuthenticationEntryPoint`, `AccessDeniedHandler` | 401, 403도 `ProblemDetail` 형식 |

Spring Security 7에서는 `and()` 체이닝과 `authorizeRequests()`가 제거되었다. `http.csrf(csrf -> csrf.disable())`처럼 람다로만 설정한다.

**CSRF를 끄는 근거와 한계**: CSRF 공격은 브라우저가 다른 사이트에서 온 요청에도 쿠키를 자동으로 붙이는 동작을 악용한다. 이 API는 세션 쿠키를 만들지 않고(stateless), 클라이언트는 `curl`, 서버, 모바일 앱이다. 다만 브라우저는 HTTP Basic 자격 증명을 기억했다가 같은 사이트 요청에 자동으로 다시 보내므로, 브라우저 클라이언트가 생기면 HTTP Basic + CSRF 비활성화 조합은 안전하지 않다. 그때는 JavaScript가 직접 헤더에 넣는 토큰(JWT, OAuth2 액세스 토큰) 방식으로 바꾼다. 이 Phase에서는 구현하지 않는다.

### 4. 401, 403 응답
두 응답은 `DispatcherServlet` 앞(필터)에서 만들어지므로 `GlobalExceptionHandler`를 거치지 않는다. 직접 `application/problem+json`을 쓴다.

| 상황 | 상태 | `code` | title | 추가 헤더 |
|---|---|---|---|---|
| `Authorization` 없음, 형식 오류, 사용자 없음, 비밀번호 틀림 | 401 | `UNAUTHENTICATED` | 인증 필요 | `WWW-Authenticate: Basic realm="lab-bank"` |
| 인증됐지만 역할 부족 | 403 | `ACCESS_DENIED` | 권한 없음 | 없음 |

- 사용자 없음과 비밀번호 틀림의 응답 본문은 `instance`를 빼고 완전히 같다. `detail`은 `"인증 정보가 없거나 올바르지 않습니다."`로 고정한다(어느 쪽이 틀렸는지 알려 주지 않는다).
- `WWW-Authenticate` 헤더는 직접 만든 `AuthenticationEntryPoint`에서 `Basic realm="lab-bank"`로 쓴다. Spring Security 기본 `BasicAuthenticationEntryPoint`에 맡기면 `Basic realm="lab-bank", charset="UTF-8"`이 나가 시나리오 2의 값과 다르다 (Spring Boot 4.1.2 실행으로 확인).
- `permitAll` 경로(`/health`)라도 `Authorization` 헤더를 보냈는데 틀리면 401이다. `BasicAuthenticationFilter`는 인가 규칙보다 앞에서 인증을 시도하고, 실패하면 `AuthenticationEntryPoint`를 호출한다.

### 5. 계좌 소유자 검증
- `Account`에 `ownerId`(username, `String`) 필드를 추가한다. `POST /accounts`는 인증된 사용자의 username을 `ownerId`로 쓴다. 요청 본문의 `ownerName`(표시 이름)은 그대로 둔다.
- 소유자 검사는 애플리케이션 서비스 계층에서 한다(컨트롤러나 `SecurityFilterChain`의 경로 규칙이 아님). 요청자 username을 서비스 메서드 인자로 넘긴다.
- 남의 계좌는 `AccountNotFoundException`을 던진다 → 404 `ACCOUNT_NOT_FOUND`. 없는 계좌와 `detail` 형식도 같다(`계좌를 찾을 수 없습니다: 110-****-0002`).

| API | 검사 대상 | 남의 것일 때 |
|---|---|---|
| `GET /accounts/{number}`, 입금, 출금, 거래내역 | `{number}` | 404 `ACCOUNT_NOT_FOUND` |
| `POST /transfers` | `fromAccount`만 (`toAccount`는 누구 것이든 가능, 존재만 확인) | 404 `ACCOUNT_NOT_FOUND` |
| `GET /transfers/{transferId}` | 그 이체를 요청한 사용자 | 404 `TRANSFER_NOT_FOUND` |
| `/ops/accounts/{number}/*` | 소유자 검사 없음 (`OPS` 역할이면 모든 계좌) |: |

- 멱등 키 범위를 (username, 키)로 바꾼다. `IdempotencyStore`의 저장 키가 (username, 키) 쌍이 된다. `TransferCommand.requestId`는 M4-4와 같이 등록 시 만든 UUID다.
- 소유자 검사로 404가 난 이체 요청도 M4-4 4절 규칙대로 저장되어 재전송된다.

### 6. 기존 테스트
M4-1~M4-6의 `@SpringBootTest` 테스트는 이제 401을 받는다. `/health`를 제외한 모든 요청에 `SecurityMockMvcRequestPostProcessors.httpBasic("alice", "alice-pass-1234")`를 붙여 다시 통과시킨다. 실제 필터 체인으로 인증하도록 `@WithMockUser`가 아니라 `httpBasic(...)`을 쓴다.

## 테스트 시나리오
`@SpringBootTest` + `@AutoConfigureMockMvc`. `A`는 alice가 개설한 KRW 계좌(잔액 100,000), `B`는 bob이 개설한 KRW 계좌, `alice:pw`는 `httpBasic("alice","alice-pass-1234")`.

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 없음 | 인증 없이 `GET /health` | `200`, `$.status` = `"UP"` |
| 2 | `A` | 인증 없이 `GET /accounts/A` | `401`, `WWW-Authenticate` = `Basic realm="lab-bank"`, `Content-Type` `application/problem+json` 호환, `$.code` = `"UNAUTHENTICATED"`, `$.instance` = `/accounts/A` |
| 3 | `A` | `httpBasic("alice","wrong")`로 `GET /accounts/A` | `401`, `$.code` = `"UNAUTHENTICATED"`, `$.detail` = `"인증 정보가 없거나 올바르지 않습니다."` |
| 4 | `A` | `httpBasic("mallory","alice-pass-1234")`로 `GET /accounts/A` | `401`, 응답 본문이 3번과 같음 |
| 5 | 없음 | 헤더 `Authorization: Basic !!!`로 `GET /accounts/110-0000-0001` | `401`, `$.code` = `"UNAUTHENTICATED"` |
| 6 | 없음 | `httpBasic("alice","wrong")`로 `GET /health` | `401` |
| 7 | 없음 | `alice:pw`로 `POST /accounts` `{"ownerName":"앨리스","currency":"KRW"}` → `GET` `Location` | `201` → `200`, 응답에 `Set-Cookie` 헤더 없음 |
| 8 | 없음 | `alice:pw`로 `POST /accounts` (CSRF 토큰 없음) | `201` (CSRF 비활성화 확인) |
| 9 | `A` | `bob:pw`로 `GET /accounts/A` | `404`, `$.code` = `"ACCOUNT_NOT_FOUND"` |
| 10 | 없음 | `bob:pw`로 `GET /accounts/110-9999-0000` | `404`, `$.status`, `$.code`, `$.title`이 9번과 같음, `$.detail` 형식(`계좌를 찾을 수 없습니다: 110-****-` + 끝 4자리)이 같음 |
| 11 | `A` | `bob:pw`로 `POST /accounts/A/withdrawals` 10,000 | `404`, 이후 alice로 조회한 `A` 잔액 `"100000"` |
| 12 | `A` | `bob:pw`로 `GET /accounts/A/transactions` | `404`, `$.code` = `"ACCOUNT_NOT_FOUND"` |
| 13 | `A`, `B` | `bob:pw`로 `POST /transfers` (`from` = `A`, `to` = `B`, 30,000), 키 `K1` | `404`, `$.code` = `"ACCOUNT_NOT_FOUND"`, `A` 잔액 `"100000"` |
| 14 | `A`, `B` | `alice:pw`로 `POST /transfers` (`from` = `A`, `to` = `B`, 30,000), 키 `K1` | `201`, `A` 잔액 `"70000"`, bob으로 조회한 `B` 잔액 `"30000"` |
| 15 | `A`(alice), `B`(bob, 잔액 100,000), 각자 상대 계좌가 있음 | alice가 키 `K1`로 `A`→`B` 10,000, bob이 같은 키 `K1`로 `B`→`A` 10,000 | 두 응답 모두 `201`, 둘 다 `Idempotent-Replayed` 없음, `transferId` 서로 다름 |
| 16 | 14번 완료 | `bob:pw`로 `GET /transfers/{14번 transferId}` | `404`, `$.code` = `"TRANSFER_NOT_FOUND"` |
| 17 | `A` | `alice:pw`로 `POST /ops/accounts/A/freeze` | `403`, `$.code` = `"ACCESS_DENIED"`, `WWW-Authenticate` 헤더 없음 |
| 18 | `A` | `ops:pw`로 `POST /ops/accounts/A/freeze` | `200`, `$.status` = `"FROZEN"` |
| 19 | `A` | `ops:pw`로 `GET /accounts/A` | `403`, `$.code` = `"ACCESS_DENIED"` |
| 20 | 없음 | 인증 없이 `POST /ops/accounts/110-0000-0001/freeze` | `401` |
| 21 | 없음 | `alice:pw`로 `GET /no-such-path` / 인증 없이 같은 요청 | `404` `RESOURCE_NOT_FOUND` / `401` |
| 22 | 애플리케이션 컨텍스트 | `UserDetailsService#loadUserByUsername("alice").getPassword()` | `"{bcrypt}$2"`로 시작 |
| 23 | M4-1~M4-6 테스트에 `httpBasic` 추가 | `./gradlew test` | 모두 통과 |

## 제약
- `WebSecurityConfigurerAdapter`(Spring Security 6에서 제거), `and()`, `authorizeRequests()`를 쓰지 않는다.
- 평문 비밀번호를 `src/main` 아래에 두지 않는다. `grep -rn "alice-pass-1234" src/main` 결과가 0줄이어야 한다(테스트 코드에는 있어도 된다).
- 컨트롤러에서 `if (!account.ownerId().equals(...))`로 소유자를 검사하지 않는다. 서비스 계층 한 곳에서만 검사한다.
- 남의 계좌에 403을 쓰지 않는다(배경의 계좌 존재 여부 노출).

## 힌트
<details>
<summary>힌트 1: 컨트롤러에서 현재 사용자 꺼내기</summary>

`@AuthenticationPrincipal UserDetails`, `Principal`, `Authentication` 파라미터 중 무엇을 쓸 수 있는지 Spring Security 레퍼런스 "Servlet Applications > Integrations > Spring MVC Integration > @AuthenticationPrincipal"을 확인한다. 서비스에는 username 문자열만 넘겨 서비스가 Spring Security에 의존하지 않게 한다.
</details>

<details>
<summary>힌트 2: 필터에서 `ProblemDetail` JSON 쓰기</summary>

`AuthenticationEntryPoint#commence`, `AccessDeniedHandler#handle`에서 `HttpServletResponse`에 상태, 헤더, 본문을 직접 쓴다. 본문은 Spring Boot가 만든 `JsonMapper` 빈(Jackson 3)을 주입받아 `ProblemDetail`을 직렬화한다. M4-3에서 `ProblemDetail`을 만드는 코드를 별도 빈으로 뺐다면 여기서도 쓴다.
</details>

## 완료 기준
- [ ] `./gradlew test`에서 이 미션의 시나리오 23개와 기존 테스트가 모두 통과한다.
- [ ] `curl -v localhost:8080/accounts/110-0000-0001` 출력에 `< HTTP/1.1 401`과 `< WWW-Authenticate: Basic realm="lab-bank"`가 보이고, `curl -v -u alice:alice-pass-1234 ...`로 같은 요청을 보낸 출력이 함께 `til/phase-4/M4-7-security.md`에 있다.
- [ ] 같은 TIL에 3절 표의 "근거" 열을 자기 말로 다시 쓴 표와, 401, 403, 404를 구분하는 순서도가 있다.
- [ ] `grep -rn "pass-1234" src/main` 결과가 0줄이다.

## 생각해볼 질문
1. BCrypt strength 10으로 비밀번호 1개를 검증하는 데 내 PC에서 몇 ms 걸리나? (같은 해시로 `matches`를 10회 실행한 중앙값) HTTP Basic은 요청마다 이 검증을 하는데, 초당 1,000건 API라면 CPU에 어떤 영향이 있나? 세션, JWT가 이 문제를 어떻게 피하는지 비교한다.
2. 남의 계좌에 404를 주는 방식의 단점은 무엇인가? 고객센터가 "계좌가 없다고 나와요" 문의를 받았을 때 원인을 구분하려면 로그에 무엇을 남겨야 하나?
3. Phase 5에서 사용자를 DB 테이블로 옮기면 `UserDetailsService`의 어느 부분만 바뀌나? 비밀번호 해시 알고리즘을 BCrypt에서 Argon2로 바꿀 때 `{id}` 접두사가 기존 사용자 비밀번호를 어떻게 살려 두는지 설명한다.
