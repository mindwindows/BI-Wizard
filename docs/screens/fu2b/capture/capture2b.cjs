// FU-2b(데이터셋 보관·복구) 화면 스크린샷 촬영 초안(Playwright, headless Chromium, 1920x1080, deviceScaleFactor 1).
//
// 사용:
//   node capture2b.cjs --origin http://127.0.0.1:36280 --base /bi-wizard --ids ids2b.json --env 임시-env-파일 --out ../
// ids2b.json (seed2b.py가 만든다, 모두 합성 값): definer, active_name, archived(보관 데이터셋 번호), archived_name 등
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

  const pickView = async (page, value) => { await page.getByLabel('보기').selectOption(value); await settle(page); };

  // 1) 목록 기본(보기 '사용 중')과 '전체'(보관 배지, 비활성 팀 소유 보관 행 포함)
  await login(IDS.definer);
  await open(page, '/datasets');
  await shot(page, 'fu2b-s2-list-active');
  await pickView(page, 'all');
  await shot(page, 'fu2b-s2-list-all');

  // 2) 보관 확인창 (확인은 누르지 않는다)
  await pickView(page, 'active');
  await page.getByRole('button', { name: IDS.active_name + ' 보관' }).click();
  await page.getByRole('dialog').waitFor();
  await shot(page, 'fu2b-s2-archive-confirm');
  await page.getByRole('button', { name: '취소' }).click();

  // 3) 보관 중 작업공간: 읽기 전용 배너, 편집 버튼 비활성
  await open(page, `/datasets/${IDS.archived}`);
  await page.getByTestId('archived-banner').waitFor();
  await shot(page, 'fu2b-workspace-archived-banner');

  // 4) 이름 충돌 안내: 보관된 데이터셋과 같은 이름으로 만들기
  await open(page, '/datasets/new');
  await page.getByLabel('이름').fill(IDS.archived_name);
  await page.getByRole('button', { name: '만들기' }).click();
  await page.getByRole('alert').first().waitFor();
  await shot(page, 'fu2b-name-conflict-archived');

  // 5) 입력자(stub-entry)와 소속 없는 관리자: '전체' 보기에서 버튼도 '관리' 열도 없다
  await login('stub-entry');
  await open(page, '/datasets');
  await pickView(page, 'all');
  await shot(page, 'fu2b-s2-nonadmin-no-buttons');
  await login('stub-admin');
  await open(page, '/datasets');
  await pickView(page, 'all');
  await shot(page, 'fu2b-s2-admin-no-buttons');

  // 6) 복구 뒤: 정의 담당자가 보관 행을 복구하고 안내가 보이는 화면
  await login(IDS.definer);
  await open(page, '/datasets');
  await pickView(page, 'all');
  await page.getByRole('button', { name: '임시 실험 복구' }).click();
  await page.getByRole('dialog').waitFor();
  await page.getByRole('dialog').getByRole('button', { name: '복구하기' }).click();
  await page.getByTestId('archive-notice').waitFor();
  // 보기를 바꾸면 안내가 지워지므로 바꾸지 않고 바로 찍는다.
  await shot(page, 'fu2b-s2-restored');

  // 7) 감사 기록: 보관·복구 행 (관리자). 행위 필터로 각각
  await login('stub-admin');
  await open(page, '/admin/audit');
  await page.locator('label', { hasText: /^행위(?!자)/ }).locator('select').selectOption('dataset.archive');
  await page.getByRole('button', { name: '조회' }).click();
  await shot(page, 'fu2b-audit-archive-rows');
  await open(page, '/admin/audit');
  await page.locator('label', { hasText: /^행위(?!자)/ }).locator('select').selectOption('dataset.restore');
  await page.getByRole('button', { name: '조회' }).click();
  await shot(page, 'fu2b-audit-restore-rows');

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
