// FU-3(기준값) 화면 스크린샷 촬영 초안(Playwright, headless Chromium, 1920x1080, deviceScaleFactor 1). 아직 실행하지 않았다.
//
// 사용:
//   node capture3.cjs --origin http://127.0.0.1:36280 --base /bi-wizard --ids ids3.json --env 임시-env-파일 --out ../
// 사전 조건: seed3.py가 만든 데이터(기준값 항목 2개, 2027년 값 없음, REF 계산 열이 있는 데이터셋)와 개발용 인증 스텁.
// 파일 이름은 fu3-{화면}-{상태}.png (03b 32-4). 마지막에 --env 파일의 비밀성 값과 화면 글자·HTML을 대조해 발견 건수를 출력한다(0이어야 한다).
// 정정 확인창 장면은 "정정 확인"까지만 누르고 "정정하기"는 누르지 않는다(데이터를 바꾸지 않는다).
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

  // 1) 관리자: 목록과 값 표
  await login(IDS.admin);
  await open(page, '/reference-values');
  await page.getByRole('table', { name: '전기요금_A팀 연도별 값' }).waitFor();
  await shot(page, 'fu3-s11-list');

  // 2) 연도 값 추가 폼(2027년 값 입력 중, 저장은 누르지 않는다)
  await page.getByLabel(/^연도 \(/).fill('2027');
  await page.getByLabel(/^값 \(/).fill('13.75');
  await shot(page, 'fu3-s11-add-value');

  // 3) 정정 확인창: 2026년 값 -> 13.00, 영향 데이터셋 목록(R6)이 보이는 상태. 확인(정정하기)은 누르지 않는다.
  await open(page, '/reference-values');
  await page.getByRole('button', { name: '2026년 값 정정' }).click();
  await page.getByLabel('2026년 새 값').fill('13.00');
  await page.getByRole('button', { name: '정정 확인' }).click();
  await page.getByRole('dialog').waitFor();
  await page.getByText('이 값을 쓰는 데이터셋:').waitFor();
  await shot(page, 'fu3-s11-correct-confirm');
  await page.getByRole('dialog').getByRole('button', { name: '취소' }).click();

  // 4) 수식 편집기의 REF(" 자동완성: 데이터셋 작업공간에서 계산 열 추가 -> 수식 칸에 REF(" 입력
  await login('stub-definer');
  await open(page, `/datasets/${IDS.dataset_id}`);
  await page.getByRole('button', { name: '계산 열 추가' }).first().click();
  const box = page.getByLabel('수식');
  await box.click();
  await box.pressSequentially('[사용량] * REF("');
  await page.getByRole('listbox', { name: '자동완성 후보' }).waitFor();
  await shot(page, 'fu3-editor-ref-autocomplete');

  // 5) E4 칸: 2027-01 행의 '전기요금' 칸이 '기준값 없음'(주황 점선)으로 보인다
  await open(page, `/datasets/${IDS.dataset_id}`);
  await page.locator('[col-id]').filter({ hasText: '기준값 없음' }).first().waitFor();
  await shot(page, 'fu3-cell-e4');

  // 6) 점검 화면 S5: E4 열을 펼친 상태
  await open(page, `/checks?dataset=${IDS.dataset_id}&column=${IDS.formula_column_id}`);
  await page.getByRole('link', { name: '기준값 화면 열기' }).first().waitFor();
  await shot(page, 'fu3-s5-e4-check');

  // 7) 비관리자(입력자): 목록과 값은 보이고 추가·정정 UI는 없다
  await login(IDS.member);
  await open(page, '/reference-values');
  await page.getByRole('table', { name: '전기요금_A팀 연도별 값' }).waitFor();
  await shot(page, 'fu3-s11-nonadmin-readonly');

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
