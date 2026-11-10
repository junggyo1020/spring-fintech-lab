# M0-3 GitHub Actions CI

> 가이드 수준: L1 · 예상 시간: 1~2h · 선행: M0-2

## 목표
이 미션을 끝내면 다음을 할 수 있다.
- 레포 루트에 `.github/workflows/ci.yml`을 작성해, push와 PR마다 빌드 파일이 있는 모든 `phase-*/workspace`에서 `./gradlew test`를 실행한다.
- 테스트 하나를 일부러 실패시킨 PR에서 `ci` 체크가 빨간 X로 표시되고, 고친 뒤 초록 체크로 바뀌는 것을 보여준다.
- Actions 실행 로그에서 어느 workspace의 어느 테스트가 실패했는지 찾아 PR 코멘트에 적는다.

## 배경
테스트를 내 PC에서만 실행하면, 테스트를 깨뜨린 커밋이 실행을 잊은 채 main에 머지될 수 있다. 금융 시스템에서 이자 계산 테스트가 깨진 코드가 배포되면 고객 수만큼 잘못된 이자가 지급된다.
CI(Continuous Integration)는 push와 PR마다 깨끗한 서버에서 빌드와 테스트를 다시 실행해, 실패한 PR을 머지 전에 표시한다.
M0-2에서 만든 Gradle Wrapper가 있어서 CI 서버에 Gradle을 따로 설치하지 않아도 `./gradlew test`가 Gradle 8.14.3으로 실행된다. 이 워크플로는 Phase 8 M8-1에서 Docker 이미지 빌드 단계를 추가할 때까지 계속 쓴다.

## 요구사항

### 1) 파일 위치와 이름
- 레포 루트의 `.github/workflows/ci.yml` (Phase 폴더 안이 아니다. GitHub는 루트의 `.github/workflows/`만 읽는다)
- 워크플로 이름(`name:`)은 `ci`

### 2) 트리거
- 모든 브랜치에 대한 `push`
- 모든 브랜치를 대상으로 하는 `pull_request`

### 3) 실행 환경과 단계
job 하나(`test`)를 `ubuntu-latest`에서 실행한다. 단계는 이 순서다.

| 순서 | 단계 | 사용할 액션 / 명령 | 설정 |
|---|---|---|---|
| 1 | 코드 체크아웃 | `actions/checkout@v7` | 없음 |
| 2 | JDK 설치 | `actions/setup-java@v6` | `distribution: temurin`, `java-version: 21` |
| 3 | Gradle 캐시 설정 | `gradle/actions/setup-gradle@v6` | 없음 |
| 4 | 테스트 실행 | 셸 스크립트 (`run:`) | 아래 4)의 규칙 |

액션 주 버전은 2026-11-10에 각 레포의 최신 릴리스(`actions/checkout` v7.0.1, `actions/setup-java` v6.2.0, `gradle/actions` v6.4.1)로 확인한 값이다.

### 4) 테스트 실행 규칙
- 레포 루트에서 `phase-*/workspace` 디렉터리를 모두 찾는다.
- 디렉터리 안에 `build.gradle.kts`가 있는 경우에만 그 디렉터리로 이동해 `./gradlew test`를 실행한다. 지금은 `phase-0-setup/workspace`만 해당하고, Phase 1을 시작하면 `phase-1-java-foundation/workspace`가 자동으로 추가된다.
- workspace 하나라도 테스트가 실패하면 job 전체가 실패한다. 실패한 뒤에도 나머지 workspace를 실행할지는 정하지 않아도 되지만, 최종 종료 코드는 0이 아니어야 한다.
- 빌드 파일이 있는 workspace가 하나도 없으면 "no workspace to test"를 출력하고 성공으로 끝낸다.
- 각 workspace를 실행하기 전에 디렉터리 이름을 출력해, 로그에서 어느 workspace의 결과인지 구분되게 한다.

### 5) 뼈대 (TODO를 채운다)

```yaml
name: ci

on:
  # TODO: 모든 브랜치의 push와 pull_request

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      # TODO: actions/checkout@v7
      # TODO: actions/setup-java@v6 (temurin, 21)
      # TODO: gradle/actions/setup-gradle@v6
      - name: Test all phase workspaces
        run: |
          # TODO: phase-*/workspace 중 build.gradle.kts가 있는 디렉터리마다 ./gradlew test
          # TODO: 하나라도 실패하면 0이 아닌 종료 코드로 끝내기
          # TODO: 대상이 없으면 "no workspace to test" 출력 후 성공
```

## 테스트 시나리오

| # | 준비(Given) | 실행(When) | 기대 결과(Then) |
|---|---|---|---|
| 1 | M0-2 workspace가 있는 브랜치 | 브랜치 push | Actions 탭에 `ci` 실행이 생기고 초록 체크로 끝난다. 로그에 `phase-0-setup/workspace`와 PASSED 5줄이 보인다 |
| 2 | 1의 브랜치로 PR 생성 | PR 화면 확인 | PR 하단 Checks에 `ci / test`가 초록 체크로 표시된다 |
| 3 | `GreeterTest`의 기대값을 `"안녕, 민수님"`으로 바꾼 커밋 | push | `ci`가 빨간 X로 끝나고, 로그에 `GreeterTest > 이름을 받아 인사말을 만든다 FAILED`가 보인다 (Gradle은 `@DisplayName` 값을 테스트 이름으로 출력한다) |
| 4 | 3의 기대값을 되돌린 커밋 | push | 같은 PR의 체크가 초록 체크로 바뀐다 |
| 5 | `phase-1-java-foundation/workspace`에 `.gitkeep`만 있는 상태 | push | Phase 1 workspace는 건너뛰고 Phase 0만 실행한다 |
| 6 | `gradlew` 실행 권한이 없는 커밋 (Windows에서 만든 경우) | push | `Permission denied`로 실패한다. 힌트 2로 고친 뒤 다시 push하면 통과한다 |

## 제약
- `gradle test`가 아니라 `./gradlew test`를 실행한다. CI 서버의 Gradle 버전과 무관하게 Wrapper에 적힌 8.14.3으로 빌드해야 로컬과 같은 결과가 나온다.
- workspace 경로(`phase-0-setup/workspace` 등)를 YAML에 하나씩 하드코딩하지 않는다. Phase가 추가될 때마다 `ci.yml`을 고치지 않아도 되어야 한다.
- 시나리오 3의 실패 커밋은 확인 후 되돌린다. main에 실패하는 테스트를 머지하지 않는다.

## 힌트
<details>
<summary>힌트 1: 셸에서 디렉터리 순회와 실패 처리</summary>

bash의 `for d in phase-*/workspace; do ... done`, 파일 존재 검사 `[ -f "$d/build.gradle.kts" ]`, 서브셸 `( cd "$d" && ./gradlew test )`를 찾아본다.
GitHub Actions의 `run:` 단계는 기본으로 `bash -e`(명령 하나가 실패하면 즉시 종료)로 실행된다. GitHub Docs "Workflow syntax for GitHub Actions"의 `jobs.<job_id>.steps[*].shell` 절에서 기본 셸 옵션을 확인한다.
</details>

<details>
<summary>힌트 2: gradlew Permission denied</summary>

Windows에서 만든 `gradlew`는 Git에 실행 권한 없이 저장될 수 있다. `git ls-files -s phase-0-setup/workspace/gradlew` 출력의 첫 숫자가 `100755`면 실행 권한이 있고 `100644`면 없다.
`git update-index --chmod=+x phase-0-setup/workspace/gradlew`로 권한을 추가하고 커밋한다.
</details>

<details>
<summary>힌트 3: setup-gradle이 하는 일</summary>

`gradle/actions` 레포의 `docs/setup-gradle.md`에서 캐시 대상(`~/.gradle/caches`, Wrapper 배포판)을 확인한다. 두 번째 실행부터 Actions 로그의 Gradle 다운로드 시간이 줄어드는지 첫 실행과 비교한다.
</details>

## 완료 기준
- [ ] 레포 루트에 `.github/workflows/ci.yml`이 있고 main에 머지되어 있다
- [ ] Actions 탭에서 시나리오 1의 초록 체크 실행과 시나리오 3의 빨간 X 실행을 각각 찾을 수 있다
- [ ] 시나리오 3 실행 로그에서 실패한 테스트 이름을 찾아 PR 코멘트로 남겼다
- [ ] `ci.yml`에 workspace 경로가 하드코딩되어 있지 않다

## 생각해볼 질문
1. `push`와 `pull_request`를 모두 트리거로 두면 PR 브랜치에 push할 때 워크플로가 몇 번 실행되는가? 두 실행은 각각 어떤 커밋(브랜치 HEAD, main과의 머지 커밋)을 테스트하는가?
2. 테스트가 실패한 PR을 머지 버튼으로 막으려면 GitHub 레포 설정의 어느 기능(브랜치 보호 규칙 / Rulesets)에서 무엇을 켜야 하는가?
3. Phase 5부터는 Testcontainers가 Docker로 MySQL을 띄운다. `ubuntu-latest` 러너에서 Docker를 쓸 수 있는지 GitHub Docs의 러너 이미지 설명에서 확인하고, 이 워크플로에 무엇을 바꿔야 하는지 적는다.
