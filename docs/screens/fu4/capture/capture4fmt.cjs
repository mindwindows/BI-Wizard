// FU-4 표시 형식(display_decimals·display_thousands) 화면 스크린샷 촬영(Playwright, headless Chromium, 1920x1080, deviceScaleFactor 1).
//
// 사용:
//   node capture4fmt.cjs --origin http://127.0.0.1:36280 --base /bi-wizard --ids ids4fmt.json --env 임시-env-파일 --out ../
// 사전 조건: seed4fmt.py가 만든 데이터(계산 열 3개가 있는 '월별 전력', 보관된 '작년 전력')와 개발용 인증 스텁.
// 파일 이름은 fu4-{화면}-{상태}.png. 마지막에 --env 파일의 비밀성 값과 화면 글자·HTML을 대조해 발견 건수를 출력한다(0이어야 한다).
// 데이터를 바꾸는 장면(태그 저장, 위치 이동, 이름 변경)은 뒤에 두었다. 다시 찍으려면 새 DB에서 seed4fmt.py부터 실행한다.
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

  const pick = async (name) => { await page.getByRole('region', { name: '열 목록' }).getByRole('button', { name: new RegExp('^' + name) }).click(); await settle(page, 300); };
  const manage = () => page.getByRole('region', { name: '계산 열 관리' });
  const reveal = async () => { await manage().waitFor(); await manage().scrollIntoViewIfNeeded(); await sleep(200); };
  const nameForm = () => manage().getByRole('form', { name: '계산 열 이름·태그' });

  const fmt = () => manage().getByRole('form', { name: '표시 형식' });
  const save = () => manage().getByRole('button', { name: '표시 형식 저장' });
  const saved = () => page.getByRole('status').filter({ hasText: '열을 저장했습니다.' }).waitFor();

  await login(IDS.definer);
  await open(page, `/datasets/${IDS.dataset_id}`);

  // 1) 설정 전: 연도 열이 쉼표 때문에 2,026으로 보인다
  await pick('연도');
  await reveal();
  await shot(page, 'fu4-format-year-before');

  // 2) 표시 형식 구역(단가당 사용량, 자릿수 2 입력 후 저장 전)
  await pick('단가당 사용량');
  await reveal();
  await fmt().getByLabel(/소수 자릿수/).fill('2');
  await fmt().scrollIntoViewIfNeeded();
  await shot(page, 'fu4-format-inspector');

  // 3) 서버 검증 오류: 화면은 0~10만 보내므로, 요청 본문만 11로 바꿔 실제 서버가 422를 돌려주게 한다(서버 응답은 실제 것)
  await page.route('**/api/datasets/*/columns/*', async (route) => {
    const req = route.request();
    if (req.method() !== 'PATCH') return route.continue();
    const body = JSON.parse(req.postData() || '{}');
    if (body.rules && body.rules.display_decimals !== undefined) body.rules.display_decimals = 11;
    return route.continue({ postData: JSON.stringify(body) });
  });
  await save().click();
  await page.getByRole('alert').filter({ hasText: '허용 범위' }).waitFor();
  await page.evaluate(() => window.scrollTo(0, 0));
  await sleep(300);
  await shot(page, 'fu4-format-error');
  await page.unroute('**/api/datasets/*/columns/*');

  // 4) 정상 저장: 자릿수 2 적용된 그리드
  await fmt().getByLabel(/소수 자릿수/).fill('2');
  await save().click();
  await saved();
  await reveal();
  await shot(page, 'fu4-format-grid-decimals');

  // 5) 연도 열 쉼표 끄기
  await pick('연도');
  await reveal();
  await fmt().getByLabel('천 단위 쉼표').uncheck();
  await save().click();
  await saved();
  await reveal();
  await shot(page, 'fu4-format-year-thousands-off');

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
