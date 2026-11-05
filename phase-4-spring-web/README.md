# Phase 4 — Spring Web MVC & API 설계 (2주)

## 학습 목표
- HTTP 요청이 컨트롤러에 도달하고 응답이 나가기까지의 흐름(`DispatcherServlet` → `HandlerMapping` → `HandlerAdapter` → `ArgumentResolver` → `MessageConverter`)을 설명한다.
- 금융 API에 맞는 **에러 응답 규격, 금액 직렬화, 입력 검증**을 설계한다.
- 컨트롤러를 MockMvc로 테스트한다.

## 주제
| 주 | 주제 |
|---|---|
| 1주 | REST 리소스 설계, 상태 코드, DTO(`record`) ↔ 도메인 변환, Bean Validation(커스텀 validator 포함), Jackson과 `BigDecimal`/`LocalDateTime` 직렬화 |
| 2주 | `@RestControllerAdvice` + `ProblemDetail`(RFC 9457), `ErrorCode` 체계, 페이지네이션, `Idempotency-Key` 헤더, MockMvc/`@WebMvcTest`, API 문서화 |

## 미션 (상세 문서는 Phase 3 완료 후 작성)
- **M4-1 계좌 API**: `POST /accounts`, `GET /accounts/{number}`, `POST /accounts/{number}/deposits`, `.../withdrawals`
- **M4-2 이체 API**: `POST /transfers` + `Idempotency-Key` 헤더 → Phase 2 멱등성 로직과 연결
- **M4-3 거래내역 조회 API**: 기간 필터, 커서 기반 페이지네이션
- **M4-4 에러 응답 표준화**: Phase 1의 `BankException`/`ErrorCode` → HTTP 상태 + `ProblemDetail` 매핑. 검증 실패 시 필드별 오류
- **M4-5 금액 직렬화 함정**: JSON에서 금액을 숫자로 보낼 때 JavaScript 정밀도 문제(`2^53`) → 문자열로 직렬화하는 커스텀 Serializer
- **M4-6 테스트**: 모든 API의 성공/실패 케이스 MockMvc 테스트 + 서블릿 필터로 요청 ID(MDC) 로깅

## 완료 기준
- [ ] 400 / 404 / 409 / 422 를 언제 쓰는지 근거를 가지고 선택
- [ ] 컨트롤러에 비즈니스 로직이 없다
- [ ] 엔티티(도메인 객체)를 API 응답으로 직접 노출하지 않는다
