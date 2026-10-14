// FU-2a(감사 로그, S10) 화면 스크린샷 촬영(Playwright, headless Chromium, 1920x1080, deviceScaleFactor 1).
//
// 사용(단계 둘로 나눠 실행한다. seed2a.py와 create-admin은 두 단계 사이에 실행):
//   node capture2a.cjs --origin http://127.0.0.1:36280 --base /bi-wizard --ids ids2a.json --env 임시-env-파일 --out ../ --only empty
//   (seed2a.py 실행, `python -m app.cli create-admin --login-id cli-admin --display-name "서버 관리자"` 실행)
//   node capture2a.cjs ... --only main
// 사전 조건: 새 DB 스택(AUTH_STUB_ENABLED=true, APP_ENV=local) + seed-stub-users. 'empty' 단계는 감사 기록이 0건일 때만 맞다.
// 마지막에 --env 파일의 비밀성 값(*PASSWORD*, *SECRET*, *KEY*, *TOKEN*)과 화면 글자·HTML을 대조해 발견 건수를 출력한다(0이어야 한다).
// playwright는 저장소 의존성이 아니다(PLAYWRIGHT_MODULE, CHROMIUM_PATH 환경변수). 파일 이름은 fu2a-{상태}.png.
const fs = require('fs');
const path = require('path');

const arg = (name, def) => { const i = process.argv.indexOf('--' + name); return i >= 0 ? process.argv[i + 1] : def; };
const ORIGIN = arg('origin'), BASE = arg('base', ''), OUT = path.resolve(arg('out', '.')), DUMP = arg('dump');
const ONLY = arg('only', 'main'), ENV_FILE = arg('env');
const IDS = arg('ids') ? JSON.parse(fs.readFileSync(arg('ids'), 'utf8')) : {};
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

  if (ONLY === 'empty') {
    // 빈 상태(필터 없음): 기록 0건
    await login('stub-admin');
    await open(page, '/admin/audit');
    await shot(page, 'fu2a-empty-state-no-records');
  } else {
    await login('stub-admin');
    // 목록(기본 화면): 최신 기록부터 50건
    await open(page, '/admin/audit');
    await shot(page, 'fu2a-list-default');
    // 다음 쪽(오래된 기록)
    await page.getByRole('button', { name: '다음' }).click();
    await shot(page, 'fu2a-list-page2');
    // 필터 적용: 데이터셋(번호) + 기간 + 행위 없음 -> 그 데이터셋의 정의 이력
    await open(page, '/admin/audit');
    await page.getByLabel('대상 종류').selectOption('dataset');
    await page.getByLabel('대상 번호').fill(String(IDS.dataset));
    await page.getByRole('button', { name: '조회' }).click();
    await shot(page, 'fu2a-filter-applied');
    // 필터 적용: 행위 하나(대시보드 수정)
    await open(page, '/admin/audit');
    await page.locator('label', { hasText: /^행위(?!자)/ }).locator('select').selectOption('dashboard.update');
    await page.getByRole('button', { name: '조회' }).click();
    await shot(page, 'fu2a-filter-applied-action');
    // 필터 적용: 서버 명령 행(행위자 '서버 명령')
    await open(page, '/admin/audit');
    await page.locator('label', { hasText: /^행위(?!자)/ }).locator('select').selectOption('user.bootstrap_admin');
    await page.getByRole('button', { name: '조회' }).click();
    await shot(page, 'fu2a-filter-applied-server-command');
    // 빈 상태(필터 있음): 없는 사용자 번호
    await page.locator('label', { hasText: /^행위(?!자)/ }).locator('select').selectOption('');
    await page.getByLabel('대상 종류').selectOption('user');
    await page.getByLabel('대상 번호').fill('999999');
    await page.getByRole('button', { name: '조회' }).click();
    await shot(page, 'fu2a-empty-state-filtered');
    // 비관리자 직접 접근
    await login('stub-entry');
    await open(page, '/admin/audit');
    await shot(page, 'fu2a-forbidden-nonadmin');
  }

  fs.writeFileSync(DUMP || path.join(OUT, 'capture2a-dump.txt'), dumps.map((d) => `=== ${d.name}\n${d.text}\n`).join('\n'));
  // 비밀값 대조
  let hits = 0;
  if (ENV_FILE) {
    const secrets = fs.readFileSync(ENV_FILE, 'utf8').split('\n').map((l) => l.split(/=(.*)/s)).filter(([k, v]) => k && v && v.length >= 8 && /PASSWORD|SECRET|KEY|TOKEN/.test(k)).map(([, v]) => v);
    for (const d of dumps) for (const v of secrets) if (d.text.includes(v) || d.html.includes(v)) { hits++; console.log('비밀 일치', d.name); }
    for (const d of dumps) if (/eyJ[A-Za-z0-9_-]{8,}\.|Traceback|\/app\/|\/usr\/lib/.test(d.text + d.html)) { hits++; console.log('토큰·내부 경로 모양', d.name); }
  }
  console.log('비밀값·내부 경로 발견 건수:', hits);
  console.log(made.length + '장 촬영', notes.length ? notes : '');
  await browser.close();
})().catch((e) => { console.error(e); process.exit(1); });
