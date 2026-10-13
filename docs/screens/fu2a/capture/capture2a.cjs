// FU-2a(감사 로그, S10) 화면 스크린샷 촬영 초안(Playwright, headless Chromium, 1920x1080, deviceScaleFactor 1).
// 초안이다: backend 구현이 끝나기 전에 쓴 것이므로 실행해 보지 않았다. 처음 돌릴 때 선택자와 시드 순서를 확인한다.
//
// 사용:
//   node capture2a.cjs --origin http://127.0.0.1:36180 --base /bi-wizard --out ../ [--dump 페이지텍스트덤프.txt]
// 사전 조건: 스택(AUTH_STUB_ENABLED=true, APP_ENV=local) + 새 DB + `python -m app.cli seed-stub-users`.
//   - 빈 상태 장면은 감사 기록이 0건일 때 가장 먼저 찍는다(그래서 단계가 'empty' -> 'seed' -> 'list' 순서다).
//   - 시드 단계는 합성 데이터로 관리자 API를 호출해 기록을 만든다(팀·사용자·소속·데이터셋·열·수식·대시보드 연결). 비밀값은 쓰지 않는다.
// playwright는 저장소 의존성이 아니다(PLAYWRIGHT_MODULE, CHROMIUM_PATH 환경변수). 파일 이름은 fu2a-{화면}-{상태}.png.
const fs = require('fs');
const path = require('path');

const arg = (name, def) => { const i = process.argv.indexOf('--' + name); return i >= 0 ? process.argv[i + 1] : def; };
const ORIGIN = arg('origin'), BASE = arg('base', ''), OUT = path.resolve(arg('out', '.')), DUMP = arg('dump');
const pw = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { chromium } = pw;
const CHROMIUM = process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const dumps = [], made = [], notes = [];

(async () => {
  const browser = await chromium.launch({ executablePath: CHROMIUM, args: ['--no-sandbox'], ignoreDefaultArgs: ['--hide-scrollbars'] });
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1, locale: 'ko-KR', timezoneId: 'Asia/Seoul' });
  const apiUrl = (p) => `${ORIGIN}${BASE}/api${p}`;
  const api = async (user, p, method = 'GET', data) => {
    const r = await ctx.request.fetch(apiUrl(p), { method, data, headers: { cookie: 'bi_stub_login=' + user, 'content-type': 'application/json' } });
    let j = null; try { j = await r.json(); } catch (e) { /* 본문 없음 */ }
    return [r.status(), j];
  };
  const login = async (user) => {
    const r = await ctx.request.put(apiUrl('/dev/stub-user'), { data: { login_id: user } });
    if (r.status() !== 204) throw new Error('login ' + user + ' ' + r.status());
  };
  const settle = async (page, ms = 400) => {
    await page.waitForLoadState('networkidle').catch(() => undefined);
    for (let i = 0; i < 40; i++) { if (!(await page.locator('.state-loading').count())) break; await sleep(150); }
    await sleep(ms);
  };
  // 화면 글자와 HTML을 모아 두었다가 비밀값 대조에 쓴다(촬영한 DOM에 토큰·비밀번호·행 값 모양이 없는지).
  const shot = async (page, name) => {
    await page.mouse.move(1910, 1070);
    await settle(page);
    const text = await page.evaluate(() => document.body.innerText);
    if (/불러오는 중/.test(text)) throw new Error(name + ': 아직 불러오는 중이다');
    const html = await page.evaluate(() => document.documentElement.outerHTML);
    await page.screenshot({ path: path.join(OUT, name + '.png'), animations: 'disabled', caret: 'hide' });
    dumps.push({ name, text, html }); made.push(name + '.png');
    console.log('촬영', name);
  };
  const open = async (page, route) => { await page.goto(`${ORIGIN}${BASE}${route}`, { waitUntil: 'networkidle' }); await settle(page, 300); };
  const page = await ctx.newPage();
  page.on('pageerror', (e) => notes.push('pageerror: ' + String(e).slice(0, 200)));

  // 1) 빈 상태: 기록이 0건일 때(새 DB 직후, 시드 전)
  await login('stub-admin');
  await open(page, '/admin/audit');
  await shot(page, 'fu2a-s10-empty-no-records');

  // 2) 시드: 합성 데이터로 기록을 만든다(행위를 두루 포함). 상세 호출은 05 계약을 따른다.
  //    예) 팀 만들기(A3), 사용자 등록(A6), 소속 지정(A8), 데이터셋 만들기(B2), 열 추가(B5), 수식 열 추가(D4), 대시보드 연결(E4) 등.
  //    TODO(backend 구현 뒤): 시드 호출을 채우고, 서버 명령 행(user.bootstrap_admin)은 시드 DB에 이미 있는 create-admin 기록을 쓴다.

  // 3) 목록(기본 화면)
  await open(page, '/admin/audit');
  await shot(page, 'fu2a-s10-list-default');

  // 4) 필터: 행위 하나와 대상 종류를 골라 조회한 결과(조건 입력이 보이는 상태)
  await page.getByLabel('대상 종류').selectOption('dataset');
  await page.getByLabel('대상 번호').fill('1');
  await page.getByLabel('행위').selectOption('column.add');
  await page.getByRole('button', { name: '조회' }).click();
  await shot(page, 'fu2a-s10-list-filtered');

  // 5) 빈 상태: 필터는 있고 결과가 없음(없는 데이터셋 번호)
  await page.getByLabel('대상 번호').fill('999999');
  await page.getByRole('button', { name: '조회' }).click();
  await shot(page, 'fu2a-s10-empty-no-match');

  // 6) 비관리자 직접 접근 거부
  await login('stub-entry');
  await open(page, '/admin/audit');
  await shot(page, 'fu2a-s10-forbidden-non-admin');

  fs.writeFileSync(DUMP || path.join(OUT, 'capture2a-dump.txt'), dumps.map((d) => `=== ${d.name}\n${d.text}\n`).join('\n'));
  console.log(made.length + '장 촬영', notes.length ? notes : '');
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
