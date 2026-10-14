// FU-2b(데이터셋 보관·복구) 화면 스크린샷 촬영 초안(Playwright, headless Chromium, 1920x1080, deviceScaleFactor 1).
// 초안이다: backend 구현이 끝난 뒤 별도 요청이 있을 때만 실행한다(지금까지 실행하지 않았다).
//
// 사용:
//   node capture2b.cjs --origin http://127.0.0.1:36280 --base /bi-wizard --ids ids2b.json --env 임시-env-파일 --out ../
// ids2b.json (시드가 만든다, 모두 합성 값): { "definer": "<정의 담당자 스텁 로그인 ID>", "active": <사용 중 데이터셋 번호>,
//   "archived": <보관할 데이터셋 번호(촬영 중 보관한다)>, "keep": <보관 상태로 둘 데이터셋 번호>, "keepName": "<그 이름>", "teamId": <팀 번호> }
// 사전 조건: 새 DB 스택(AUTH_STUB_ENABLED=true, APP_ENV=local) + seed-stub-users + 시드(정의 담당자 팀, 데이터셋 3개 이상, 열 몇 개).
// 파일 이름은 fu2b-{화면}-{상태}.png (03b 30-2). 마지막에 --env 파일의 비밀성 값과 화면 글자·HTML을 대조해 발견 건수를 출력한다(0이어야 한다).
const fs = require('fs');
const path = require('path');

const arg = (name, def) => { const i = process.argv.indexOf('--' + name); return i >= 0 ? process.argv[i + 1] : def; };
const ORIGIN = arg('origin'), BASE = arg('base', ''), OUT = path.resolve(arg('out', '.')), ENV_FILE = arg('env');
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
  const login = async (user) => {
    const r = await ctx.request.put(apiUrl('/dev/stub-user'), { data: { login_id: user } });
    if (r.status() !== 204) throw new Error('login ' + user + ' ' + r.status());
  };
  const settle = async (page, ms = 400) => {
    await page.waitForLoadState('networkidle').catch(() => undefined);
    for (let i = 0; i < 40; i++) { if (!(await page.locator('.state-loading').count())) break; await sleep(150); }
    await sleep(ms);
  };
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

  await login(IDS.definer);

  // 1) 목록: 보기 '전체' + 보관 배지 + 보관/복구 버튼 (보관 상태인 데이터셋 하나가 이미 있어야 한다)
  await open(page, '/datasets');
  await page.getByLabel('보기').selectOption('all');
  await settle(page);
  await shot(page, 'fu2b-s2-list-active');

  // 2) 보관 확인창 (확인은 누르지 않는다)
  await page.getByRole('button', { name: /보관$/ }).first().click();
  await page.getByRole('dialog').waitFor();
  await shot(page, 'fu2b-s2-archive-confirm');
  await page.getByRole('button', { name: '취소' }).click();

  // 3) 보관 중 작업공간: 읽기 전용 배너, 편집 버튼 비활성
  await open(page, `/datasets/${IDS.keep}`);
  await page.getByTestId('archived-banner').waitFor();
  await shot(page, 'fu2b-workspace-archived-banner');

  // 4) 이름 충돌 안내: 보관된 데이터셋과 같은 이름으로 만들기
  await open(page, '/datasets/new');
  await page.getByLabel('이름').fill(IDS.keepName);
  await page.getByRole('button', { name: '만들기' }).click();
  await page.getByRole('alert').first().waitFor();
  await shot(page, 'fu2b-name-conflict-archived');

  // 5) 복구 뒤: 목록에서 보관 행을 복구하고 안내가 보이는 화면
  await open(page, '/datasets');
  await page.getByLabel('보기').selectOption('archived');
  await settle(page);
  await page.getByRole('button', { name: /복구$/ }).first().click();
  await page.getByRole('dialog').getByRole('button', { name: '복구하기' }).click();
  await page.getByTestId('archive-notice').waitFor();
  await page.getByLabel('보기').selectOption('all');
  await shot(page, 'fu2b-s2-restored');

  // 비밀값 대조
  let found = 0;
  if (ENV_FILE) {
    const secrets = fs.readFileSync(ENV_FILE, 'utf8').split('\n')
      .map((l) => l.match(/^([A-Z0-9_]*(PASSWORD|SECRET|KEY|TOKEN)[A-Z0-9_]*)=(.+)$/)).filter(Boolean).map((m) => m[3].trim()).filter((v) => v.length >= 8);
    for (const d of dumps) for (const s of secrets) if (d.text.includes(s) || d.html.includes(s)) { found++; console.log('발견', d.name); }
    for (const d of dumps) if (/eyJ[A-Za-z0-9_-]{10,}\./.test(d.text + d.html)) { found++; console.log('토큰 모양', d.name); }
  }
  console.log('비밀값·내부 경로 발견 건수:', found, notes.length ? notes : '');
  await browser.close();
  if (found) process.exit(1);
})();
