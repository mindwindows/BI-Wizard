// FU-4(계산 열 이름·위치·태그) 화면 스크린샷 촬영 초안(Playwright, headless Chromium, 1920x1080, deviceScaleFactor 1).
//
// 사용:
//   node capture4.cjs --origin http://127.0.0.1:36280 --base /bi-wizard --ids ids4.json --env 임시-env-파일 --out ../
// 사전 조건: seed4.py가 만든 데이터(계산 열 3개가 있는 '월별 전력', 보관된 '작년 전력')와 개발용 인증 스텁.
// 파일 이름은 fu4-{화면}-{상태}.png. 마지막에 --env 파일의 비밀성 값과 화면 글자·HTML을 대조해 발견 건수를 출력한다(0이어야 한다).
// 데이터를 바꾸는 장면(태그 저장, 위치 이동, 이름 변경)은 뒤에 두었다. 다시 찍으려면 새 DB에서 seed4.py부터 실행한다.
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

  // 1) 이름 중복 안내(저장 거부, 데이터 불변)
  await login(IDS.definer);
  await open(page, `/datasets/${IDS.dataset_id}`);
  await pick('부가세');
  await reveal();
  await nameForm().getByLabel('열 이름').fill('사용량');
  await manage().getByRole('button', { name: '이름·태그 저장' }).click();
  await page.getByText('같은 이름의 열이 이미 있습니다.').waitFor();
  await reveal();
  await shot(page, 'fu4-rename-error');

  // 2) 입력자(정의 담당자가 아님): 읽기 전용
  await login(IDS.member);
  await open(page, `/datasets/${IDS.dataset_id}`);
  await pick('전기요금');
  await reveal();
  await shot(page, 'fu4-readonly-nonDefiner');

  // 3) 보관된 데이터셋: 비활성
  await login(IDS.definer);
  await open(page, `/datasets/${IDS.archived_id}`);
  await pick('전기요금');
  await reveal();
  await shot(page, 'fu4-archived-disabled');

  // 4) 태그 편집: 전기요금의 태그 '비용' -> '에너지비' 저장 뒤
  await open(page, `/datasets/${IDS.dataset_id}`);
  await pick('전기요금');
  await reveal();
  await nameForm().getByLabel('구분 태그').fill('에너지비');
  await manage().getByRole('button', { name: '이름·태그 저장' }).click();
  await page.getByRole('status').filter({ hasText: '열을 저장했습니다.' }).waitFor();
  await reveal();
  await shot(page, 'fu4-inspector-formula-tag');

  // 5) 위치 이동: 구분(맨 뒤)을 위로 한 칸 -> 열 목록·그리드 순서가 바뀐다
  await pick('구분');
  await reveal();
  await manage().getByRole('button', { name: '위로 이동' }).click();
  await page.getByRole('status').filter({ hasText: '열 순서를 바꿨습니다.' }).waitFor();
  await reveal();
  await shot(page, 'fu4-inspector-formula-move');

  // 6) 이름 변경: 부가세 -> '부가세(10%)' (저장 직전 입력 상태가 아니라 저장 뒤 목록·수식 보기)
  await pick('부가세');
  await reveal();
  await nameForm().getByLabel('열 이름').fill('부가세(10%)');
  await shot(page, 'fu4-inspector-formula-rename-input');
  await manage().getByRole('button', { name: '이름·태그 저장' }).click();
  await page.getByRole('status').filter({ hasText: '열을 저장했습니다.' }).waitFor();
  await reveal();
  await shot(page, 'fu4-inspector-formula-rename');

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
