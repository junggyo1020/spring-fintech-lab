# M4-1 HTTP와 첫 컨트롤러

> 가이드 수준: L2, 예상 시간: 3~4h, 선행: M3-6

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- `curl -v` 출력에서 요청 줄, 요청 헤더, 상태 줄, 응답 헤더, 본문을 줄 단위로 구분해 TIL 표에 옮긴다.
- `GET /health` 요청 하나가 `DispatcherServlet`의 5단계(README 3절)를 지나는 것을 DEBUG 로그 줄과 디버거 스크린샷으로 보여준다.
- 200, 404, 405, 406 응답을 각각 만들어 내는 `curl` 명령을 작성하고, 각 응답을 만든 Spring 구성 요소의 이름을 적는다.
- `@SpringBootTest` + `MockMvc`로 HTTP 상태 코드와 JSON 필드를 검증하는 테스트를 작성한다.

## 배경
금융 API 장애의 상당수는 비즈니스 로직이 아니라 HTTP 계층에서 생긴다. 클라이언트가 `Content-Type`을 빠뜨려 415를 받고 "서버 장애"로 신고하거나, 서버가 오류를 200으로 돌려줘 클라이언트의 재시도 로직이 잘못된 분기를 탄다.
HTTP 메시지를 눈으로 읽을 수 없으면 이런 장애를 로그만 보고 원인을 찾을 수 없다.
M3-6까지 만든 Spring Boot 애플리케이션은 웹 서버가 없는 콘솔 형태였다. 이 미션에서 Tomcat을 띄우고 첫 HTTP 엔드포인트를 연다.

## 요구사항
1. README "워크스페이스 만들기"대로 workspace를 만들고 `./gradlew bootRun`으로 애플리케이션을 띄운다. 콘솔에 `Tomcat started on port 8080`이 포함된 줄이 나와야 한다.
2. `lab.bank.web.HealthController`를 만든다.
   - `GET /health` → `200`, `Content-Type: application/json`, 본문 `{"status":"UP"}`
   - 응답 본문은 `record HealthResponse(String status)`로 만든다. `Map`을 반환하지 않는다.
   - 다른 경로, 메서드는 만들지 않는다. `POST /health`는 Spring MVC가 405로 응답하게 둔다.
   - Spring Boot Actuator의 `/actuator/health`를 쓰지 않는다. 이 미션의 목적은 컨트롤러를 직접 만드는 것이다.
3. 아래 7개 명령을 실행하고, 출력 전체를 `til/phase-4/M4-1-curl.md`에 붙인다. 각 출력 아래에 "요청 줄 / 요청 헤더 / 상태 줄 / 응답 헤더 / 본문" 5칸 표를 만들어 해당 줄을 옮긴다.

   ```bash
   curl -v http://localhost:8080/health
   curl -v -I http://localhost:8080/health                                   # HEAD
   curl -v -X POST http://localhost:8080/health                              # 405
   curl -v http://localhost:8080/no-such-path                                # 404
   curl -v -H "Accept: application/xml" http://localhost:8080/health          # 406
   curl -v -H "Accept: application/json" http://localhost:8080/health
   curl -s -o /dev/null -w "%{http_code} %{size_download}\n" http://localhost:8080/health
   ```
4. `application.yml`의 `logging.level.org.springframework.web`을 `DEBUG`로 바꾸고 `GET /health`를 1번 호출한다. 로그에서 아래 4가지에 해당하는 줄을 찾아 TIL에 붙인다. 확인 후 `INFO`로 되돌린다.
   - 요청 수신 (`GET "/health"`가 포함된 줄)
   - 핸들러 매핑 결과 (`Mapped to` 다음에 `HealthController`의 메서드 이름이 나오는 줄)
   - 응답 형식 결정 (`Using 'application/json'`이 포함된 줄)
   - 완료 (`Completed 200`이 포함된 줄)
5. IDE에서 `DispatcherServlet#doDispatch`에 중단점을 걸고 `GET /health`를 호출한다. 아래 표를 TIL에 채운다. 값은 디버거의 Variables 창에서 읽은 클래스 이름이다.

   | 단계 | 확인할 변수 / 메서드 | 기록할 값 |
   |---|---|---|
   | HandlerMapping | `getHandler(processedRequest)`를 실행한 직후 `mappedHandler.getHandler()` | 클래스 이름과 메서드 이름 |
   | HandlerAdapter | `getHandlerAdapter(...)`의 반환값 | 클래스 이름 |
   | ArgumentResolver | (이 메서드는 파라미터가 없다) 요구사항 6의 파라미터 실험 결과 | resolver 클래스 이름 |
   | HttpMessageConverter | `AbstractMessageConverterMethodProcessor#writeWithMessageConverters`에 중단점, 선택된 converter | 클래스 이름 |

6. ArgumentResolver 관찰용으로 `GET /health`에 `@RequestHeader(value = "User-Agent", required = false) String userAgent` 파라미터를 잠시 추가하고, `HandlerMethodArgumentResolverComposite#resolveArgument`에서 선택된 resolver 클래스 이름을 기록한다. 기록 후 파라미터를 지운다.
7. `HealthControllerTest`를 `@SpringBootTest` + `@AutoConfigureMockMvc`로 작성한다. Spring Boot 4부터 `@SpringBootTest`만으로는 `MockMvc`가 주입되지 않는다. `@AutoConfigureMockMvc`가 필요하다.

## 테스트 시나리오

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | 애플리케이션 컨텍스트 기동 | `GET /health` | `200`, `Content-Type`이 `application/json`과 호환, `$.status` = `"UP"` |
| 2 | 같음 | `HEAD /health` | `200`, `Content-Type`이 `application/json`과 호환. 본문 길이는 단언하지 않는다 (`MockMvc`는 서블릿 컨테이너가 하는 HEAD 본문 제거를 하지 않아 GET과 같은 본문 15바이트가 남는다. Boot 4.1.2에서 확인). 본문 길이 0은 요구사항 3의 `curl -v -I` 출력으로 확인한다 |
| 3 | 같음 | `POST /health` (본문 없음) | `405`, 응답 헤더 `Allow`에 `GET` 포함 |
| 4 | 같음 | `GET /no-such-path` | `404` |
| 5 | 같음 | `GET /health`, `Accept: application/xml` | `406` |
| 6 | 같음 | `GET /health`, `Accept: application/json` | `200`, `$.status` = `"UP"` |
| 7 | 같음 | `GET /health/` (끝에 `/`) | `404` (Spring Framework 6.0부터 끝 슬래시 매칭이 기본으로 꺼져 있다) |

시나리오 3~5의 응답 본문 형식은 이 미션에서 검증하지 않는다. M4-3에서 `ProblemDetail`로 바꾼다. 지금 본문이 어떤 모양인지는 요구사항 3의 TIL에 기록만 한다.

## 제약
- 컨트롤러가 `ResponseEntity<String>`에 JSON 문자열을 직접 만들어 넣지 않는다. 직렬화는 `HttpMessageConverter`가 해야 4단계를 관찰할 수 있다.
- `@CrossOrigin`, CORS 설정을 추가하지 않는다. 이 Phase의 클라이언트는 `curl`과 테스트다.
- 포트를 테스트에서 고정하지 않는다. `MockMvc`는 실제 포트를 열지 않는다(`webEnvironment` 기본값 `MOCK`).

## 힌트
<details>
<summary>힌트 1: 406과 405는 누가 만드는가</summary>

406은 `HttpMediaTypeNotAcceptableException`, 405는 `HttpRequestMethodNotSupportedException`이다. 둘 다 컨트롤러 메서드가 호출되기 전에 난다. 어느 단계(README 3절 표)에서 나는지 DEBUG 로그의 마지막 줄을 보고 판단한다. 404는 Spring Framework 6.1부터 `NoResourceFoundException`으로 바뀌었다.
</details>

<details>
<summary>힌트 2: `curl -v`의 기호</summary>

`>`로 시작하는 줄은 curl이 보낸 것, `<`로 시작하는 줄은 받은 것, `*`는 curl 자신의 연결 정보다. 응답 본문은 기호 없이 출력된다. `Transfer-Encoding: chunked`와 `Content-Length` 중 무엇이 왔는지도 표에 적는다.
</details>

## 완료 기준
- [ ] `./gradlew test --tests "*HealthControllerTest"`에서 테스트 7개가 통과한다.
- [ ] `til/phase-4/M4-1-curl.md`에 curl 출력 7개와 각각의 5칸 표가 있다.
- [ ] 같은 TIL에 DEBUG 로그 4줄과 요구사항 5의 4행 표가 채워져 있다.
- [ ] `HealthController`에 메서드가 1개(`GET /health`)만 있다.

## 생각해볼 질문
1. `HEAD /health`는 컨트롤러에 매핑하지 않았는데 왜 200이 나왔나? Spring MVC 레퍼런스 "Request Mapping > HTTP HEAD, OPTIONS"에서 근거를 찾아 적는다.
2. 406(`Accept` 불일치)과 415(`Content-Type` 불일치)는 각각 요청의 어느 헤더 때문에 나는가? 이체 API를 호출하는 모바일 앱이 415를 받으면 앱 개발자는 무엇을 고쳐야 하나?
3. `/health`가 항상 `UP`을 돌려주면 로드밸런서는 이 서버가 DB에 연결되지 않은 상태(Phase 5)에서도 트래픽을 보낸다. DB 연결을 확인하는 헬스 체크와 프로세스 생존만 확인하는 헬스 체크를 나눠야 하는 이유는 무엇인가? (Spring Boot Actuator의 liveness/readiness 구분과 비교)
