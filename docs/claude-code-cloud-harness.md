클라우드 Claude Code + revfactory/harness 적용 메모
작성일: 2026-10-11
목적: claude.ai 대화에서 정리한 내용을 Claude Code 세션이 읽을 수 있도록 저장소에 보관.
Claude Code는 claude.ai 채팅 기록을 읽지 못하므로, 세션 시작 시 이 파일을 먼저 읽도록 지시한다.
---
1. 작업 환경 결정 사항
클라우드 기반 Claude Code(claude.ai/code)에서 작업한다.
개인 작업이므로 GitLab은 사용하지 않고 개인 GitHub 계정의 저장소를 사용한다.
저장소는 GitHub 웹(github.com/new)에서 먼저 생성했다. 클라우드 Claude Code 안에서는 새 저장소를 만들 수 없다.
비공개 저장소이므로 해당 GitHub 계정에 Claude GitHub App을 설치했다(저장소 범위는 선택 저장소로 한정).
나중에 회사 Claude Enterprise 계정으로 전환할 가능성이 있다. 전환 시 확인할 것:
회사 claude.ai/code 에 GitHub 로그인 버튼이 뜨는지 (조직 Owner가 GitHub 커넥터를 켜 두어야 함)
조직 정책으로 클라우드 세션이 꺼져 있지 않은지
개인 GitHub 저장소라면 GitHub 쪽 앱 설치는 본인 권한으로 가능
2. 클라우드 세션에서 되는 것 / 안 되는 것
저장소에 커밋되면 세션이 자동으로 읽는 것
`CLAUDE.md`
`.claude/skills/`, `.claude/agents/`, `.claude/commands/`
`.claude/rules/`
`.claude/settings.json`의 hooks·permission 규칙 (저장소 1개 세션일 때)
`.mcp.json` (저장소 1개 세션일 때)
클라우드 세션에서 안 되는 것
`/plugin` 명령 자체가 없음
내 PC에 설치한 플러그인·스킬·에이전트(`~/.claude/…`)는 로드되지 않음
저장소 `.claude/settings.json`에 `enabledPlugins` / `extraKnownMarketplaces`로 선언해 둔 플러그인도 설치되지 않음
`/reload-plugins`, `/clear`, `/resume` 등 터미널 전용 명령 없음
claude.ai 채팅 기록 참조 불가
그 외 제약
세션 VM: Ubuntu 24.04 x86_64, 4 vCPU / 16GB RAM / 30GB 디스크
네트워크: 기본 Trusted 레벨(패키지 레지스트리·GitHub 등 허용 목록만). 다른 도메인이 필요하면 환경 설정에서 Custom으로 추가
추가 패키지는 환경 설정의 Setup script에 넣어야 다음 세션에도 유지됨(세션 중 설치한 것은 사라짐)
3. revfactory/harness 적용 방식
플러그인 마켓플레이스(`/plugin marketplace add revfactory/harness`) 경로는 클라우드 세션에서 쓸 수 없다.
대신 revfactory/harness가 공식 지원하는 스킬 폴더 복사 방식을 쓴다.
revfactory/harness 저장소의 `skills/harness` 폴더 내용을 이 저장소의 `.claude/skills/harness/`에 커밋한다.
클라우드 환경 설정(claude.ai/code 환경 선택기 → 환경 편집)의 환경변수에 다음을 추가한다.
```
   CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
   ```
클라우드 세션은 agent teams가 기본으로 꺼져 있고, harness는 이 기능에 의존한다.
세션에서 자연어로 호출한다. 예: `Build a harness for <도메인 설명>`
harness가 생성한 `.claude/agents/`, `.claude/skills/` 결과물을 커밋하면 이후 세션에서도 자동 인식된다.
참고: 환경변수 변경은 기존 세션에는 바로 반영되지 않는다. 새 세션을 열거나 VM이 재생성될 때 적용된다.
4. 세션 시작 시 지시 예시
```
docs/claude-code-cloud-harness.md 를 먼저 읽고 시작해.
```
5. 다음 단계 (진행 순서)
[ ] `.claude/skills/harness/` 커밋
[ ] 환경변수 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 설정
[ ] 새 세션에서 harness 호출 테스트
[ ] 생성된 에이전트·스킬 검토 후 커밋
6. 참고 문서
Claude Code in the cloud: https://code.claude.com/docs/en/claude-code-on-the-web
Configure cloud environments (What carries over): https://code.claude.com/docs/en/cloud-environments
Install and manage plugins (Cloud session 탭): https://code.claude.com/docs/en/plugins/install
Get started with Claude Code in the cloud: https://code.claude.com/docs/en/web-quickstart
revfactory/harness: https://github.com/revfactory/harness
