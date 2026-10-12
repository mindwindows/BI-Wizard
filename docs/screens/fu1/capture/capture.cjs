// FU-1 1a·1b·1c 주요 화면 스크린샷 촬영(Playwright, headless Chromium, 1920x1080, deviceScaleFactor 1).
//
// 사용:
//   node capture.cjs --origin http://127.0.0.1:36173 --base /bi-wizard --ids ids.json --out ../ \
//        --env 임시-env-파일 [--only 이름,이름] [--dump 페이지텍스트덤프.txt]
// 사전 조건: 스택(스텁 켬)이 떠 있고 seed.py로 합성 데이터를 넣은 새 DB. 이 스크립트는 일부 화면을 만들려고
//   스텁 쿠키 + HTTP API로 데이터를 바꾼다(한 번 실행하면 DB가 바뀌므로 다시 찍으려면 새 DB에서 시작한다).
// playwright는 저장소 의존성이 아니다. 외부에 설치하고(PLAYWRIGHT_MODULE 환경변수 또는 NODE_PATH),
//   브라우저 실행 파일은 CHROMIUM_PATH(기본 /opt/pw-browsers/chromium)로 지정한다.
const fs = require('fs');
const path = require('path');

const arg = (name, def) => { const i = process.argv.indexOf('--' + name); return i >= 0 ? process.argv[i + 1] : def; };
const ORIGIN = arg('origin'), BASE = arg('base', ''), OUT = path.resolve(arg('out', '.'));
const IDS = JSON.parse(fs.readFileSync(arg('ids'), 'utf8'));
const ENV_FILE = arg('env'), ONLY = (arg('only', '') || '').split(',').filter(Boolean), DUMP = arg('dump');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const CHROMIUM = process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const S = IDS.sales.cols, W = IDS.wide.cols, D = IDS.defn.cols;

const dumps = [];   // 촬영 순간의 페이지 텍스트·HTML(비밀값 검사용)
const made = [];    // 촬영한 파일
const notes = [];   // 시나리오 점검 메모

(async () => {
  const browser = await chromium.launch({ executablePath: CHROMIUM, args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1, locale: 'ko-KR', timezoneId: 'Asia/Seoul' });
  const apiUrl = (p) => `${ORIGIN}${BASE}/api${p}`;
  const loginAs = async (user) => {
    if (user === null) return ctx.request.delete(apiUrl('/dev/stub-user'));
    if (user.startsWith('!')) { // 등록되지 않은 로그인 ID: 스텁 API는 거부하므로 쿠키를 직접 심는다.
      await ctx.request.delete(apiUrl('/dev/stub-user'));
      return ctx.addCookies([{ name: 'bi_stub_login', value: user.slice(1), domain: new URL(ORIGIN).hostname, path: BASE || '/' }]);
    }
    const r = await ctx.request.put(apiUrl('/dev/stub-user'), { data: { login_id: user } });
    if (r.status() !== 204) throw new Error('login ' + user + ' ' + r.status());
  };
  const api = async (user, p, method = 'GET', data) => {
    const r = await ctx.request.fetch(apiUrl(p), { method, data, headers: { cookie: 'bi_stub_login=' + user, 'content-type': 'application/json' } });
    let j = null; try { j = await r.json(); } catch (e) { /* 본문 없음 */ }
    return [r.status(), j];
  };
  const newPage = async () => {
    const page = await ctx.newPage();
    page.on('pageerror', (e) => notes.push('pageerror: ' + String(e).slice(0, 200)));
    page.on('console', (m) => { if (m.type() === 'error') notes.push('console.error: ' + m.text().slice(0, 200)); });
    return page;
  };
  const settle = async (page, ms = 600) => {
    await page.waitForLoadState('networkidle').catch(() => undefined);
    for (let i = 0; i < 40; i++) {
      const loading = await page.locator('.state-loading').count();
      if (!loading) break;
      await sleep(150);
    }
    await sleep(ms);
  };
  const shot = async (page, name, opts = {}) => {
    await page.mouse.move(1910, 1070);
    await settle(page, opts.wait ?? 500);
    const text = await page.evaluate(() => document.body.innerText);
    if (/불러오는 중/.test(text) && !opts.allowLoading) throw new Error(name + ': 아직 불러오는 중이다');
    const file = path.join(OUT, name + '.png');
    await page.screenshot({ path: file, animations: 'disabled', caret: 'hide' });
    dumps.push({ name, text, html: await page.evaluate(() => document.documentElement.outerHTML) });
    made.push(name + '.png');
    console.log('촬영', name);
  };
  const open = async (page, route) => { await page.goto(`${ORIGIN}${BASE}${route}`, { waitUntil: 'networkidle' }); await settle(page, 300); };
  // 네이티브 <select>의 펼침 목록은 headless 스크린샷에 나오지 않으므로 같은 선택지를 목록 상자로 펼쳐 보여 준다(촬영 전용 표시).
  const expandSelect = (page, selector) => page.evaluate((sel) => {
    const el = document.querySelector(sel);
    const box = el.getBoundingClientRect();
    const clone = el.cloneNode(true);
    clone.removeAttribute('id'); clone.value = el.value; clone.size = el.options.length;
    Object.assign(clone.style, { position: 'fixed', zIndex: '1000', height: 'auto', left: box.left + 'px', top: (box.bottom + 2) + 'px', width: Math.max(box.width, 150) + 'px', background: '#fff', color: '#111', border: '1px solid #444' });
    document.body.appendChild(clone);
  }, selector);
  const cell = (page, row, col) => page.locator(`[role=row][row-id="${row}"] [col-id="${col}"]`);
  const paste = (page, txt) => page.evaluate((t) => {
    const el = document.activeElement || document.body; const dt = new DataTransfer(); dt.setData('text/plain', t);
    const ev = new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }); el.dispatchEvent(ev); return ev.defaultPrevented;
  }, txt);
  const rowsOf = async (user, ds) => (await api(user, `/datasets/${ds.id}/rows?order=desc&limit=200`))[1];
  const rowByDate = async (user, ds, dateColName, date) => (await rowsOf(user, ds)).items.find((r) => r.cells[ds.cols[dateColName]] === date);
  const verOf = async (user, ds) => (await api(user, `/datasets/${ds.id}`))[1].def_version;
  const gridReady = async (page) => { await page.waitForSelector('[role=row][row-id^="r"]'); await settle(page, 500); };

  const scenarios = {
    // ---------------------------------------------------------------- 1a
    async 'fu1a-home'() {
      const page = await newPage();
      await loginAs('stub-admin'); await open(page, '/');
      await page.waitForSelector('[data-testid=stub-switcher]'); await shot(page, 'fu1a-s1-shell-home-admin');
      await loginAs('stub-entry'); await open(page, '/');
      await shot(page, 'fu1a-s1-shell-home-entry');
      await page.close();
    },
    async 'fu1a-denied'() {
      const page = await newPage();
      await loginAs('!ghost-user'); await open(page, '/');
      await page.waitForSelector('text=접근 권한이 없습니다'); await shot(page, 'fu1a-s1-access-denied-unregistered');
      await loginAs('stub-inactive'); await open(page, '/');
      await page.waitForSelector('text=접근 권한이 없습니다'); await shot(page, 'fu1a-s1-access-denied-inactive');
      await loginAs(null); await open(page, '/');
      await page.waitForSelector('text=접근 권한이 없습니다'); await shot(page, 'fu1a-s1-access-denied-no-identity');
      await page.close();
    },
    async 'fu1a-workteam'() {
      const page = await newPage();
      await loginAs('stub-multi'); await open(page, '/');
      await page.waitForSelector('.work-team select');
      await expandSelect(page, '.work-team select');
      await shot(page, 'fu1a-s1-work-team-select-open-inactive-team');
      await page.close();
    },
    async 'fu1a-stub'() {
      const page = await newPage();
      await loginAs('stub-definer'); await open(page, '/');
      await page.waitForSelector('[data-testid=stub-switcher]');
      await expandSelect(page, '[data-testid=stub-switcher] select');
      await shot(page, 'fu1a-s1-dev-identity-switcher-open');
      await page.close();
    },
    async 'fu1a-s6'() {
      const page = await newPage();
      await loginAs('stub-admin'); await open(page, '/admin/permissions');
      await page.waitForSelector('table.matrix'); await shot(page, 'fu1a-s6-permissions-grid');
      // 변경 쌓기
      await page.getByLabel('김비소속 - 시험 A팀 역할').selectOption('entry');
      await page.getByLabel('이영업 - 시험 B팀 역할').selectOption('definer');
      await page.getByLabel('박재무 - 시험 A팀 역할').selectOption('');
      const teamForm = page.locator('form[aria-label="팀 만들기"]');
      await teamForm.getByLabel('팀 코드').fill('finance_1'); await teamForm.getByLabel('팀 이름').fill('재무기획팀');
      await teamForm.getByRole('button', { name: '변경 목록에 담기' }).click();
      const userForm = page.locator('form[aria-label="사용자 사전 등록"]');
      await userForm.getByLabel('로그인 ID').fill('han-new'); await userForm.getByLabel('표시 이름').fill('한신규');
      await userForm.getByRole('button', { name: '변경 목록에 담기' }).click();
      await page.getByRole('button', { name: '시험 열람자 수정' }).click();
      const uedit = page.locator('form[aria-label^="사용자 수정"]');
      await uedit.getByLabel('표시 이름').fill('시험 열람자(수정)'); await uedit.getByRole('button', { name: '변경 목록에 담기' }).click();
      await page.getByRole('button', { name: '시험 B팀 수정' }).click();
      const tedit = page.locator('form[aria-label^="팀 수정"]');
      await tedit.getByLabel('팀 이름').fill('시험 B팀(개편)'); await tedit.getByRole('button', { name: '변경 목록에 담기' }).click();
      await page.locator('section.pending').scrollIntoViewIfNeeded();
      await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
      await shot(page, 'fu1a-s6-changes-staged');
      await page.getByRole('button', { name: '저장하기' }).click();
      await page.waitForSelector('[role=dialog]'); await shot(page, 'fu1a-s6-confirm-dialog');
      await page.getByRole('button', { name: '돌아가기' }).click();
      await page.close();
      // LAST_ADMIN: 마지막 활성 관리자 해제 + 앞선 정상 변경 1건(소속 지정)
      const p2 = await newPage();
      await open(p2, '/admin/permissions'); await p2.waitForSelector('table.matrix');
      await p2.getByLabel('김비소속 - 시험 A팀 역할').selectOption('entry');
      await p2.getByRole('button', { name: '시험 관리자 수정' }).click();
      const ue = p2.locator('form[aria-label^="사용자 수정"]');
      await ue.getByLabel('관리자', { exact: true }).uncheck(); await ue.getByRole('button', { name: '변경 목록에 담기' }).click();
      await p2.getByRole('button', { name: '저장하기' }).click();
      await p2.getByRole('button', { name: '확인하고 저장' }).click();
      await p2.waitForSelector('text=저장 결과'); await sleep(500);
      await shot(p2, 'fu1a-s6-last-admin-error-result');
      await p2.close();
      // 일반 사용자 직접 접속
      const p3 = await newPage();
      await loginAs('stub-entry'); await open(p3, '/admin/permissions');
      await p3.waitForSelector('text=관리자만 사용할 수 있는'); await shot(p3, 'fu1a-s6-non-admin-notice');
      await p3.close();
    },
    // ---------------------------------------------------------------- 1b
    async 'fu1b-list'() {
      const page = await newPage();
      await loginAs('stub-admin'); await open(page, '/datasets'); await page.waitForSelector('table.list-table');
      await shot(page, 'fu1b-s2-dataset-list-admin-no-create-button');
      await loginAs('stub-definer'); await open(page, '/datasets'); await page.waitForSelector('table.list-table');
      await shot(page, 'fu1b-s2-dataset-list-definer-with-create-button');
      await page.close();
    },
    async 'fu1b-create'() {
      const page = await newPage();
      await loginAs('stub-definer'); await open(page, '/datasets/new'); await page.waitForSelector('form[aria-label="데이터셋 만들기"]');
      await shot(page, 'fu1b-s3-create-form-default');
      await page.getByRole('button', { name: '만들기' }).click(); await sleep(300);
      await shot(page, 'fu1b-s3-create-form-error-empty-name');
      await page.getByLabel('이름').fill('월별 매출'); await page.getByLabel('날짜 단위').selectOption('month');
      await page.getByRole('button', { name: '만들기' }).click(); await page.waitForSelector('[role=alert]:has-text("같은 이름")');
      await shot(page, 'fu1b-s3-create-form-error-duplicate-name');
      await page.close();
      const p2 = await newPage();
      await loginAs('stub-admin'); await open(p2, '/datasets/new'); await p2.waitForSelector('[data-testid=no-definer-team]');
      await shot(p2, 'fu1b-s3-no-definer-team-admin');
      await p2.close();
    },
    async 'fu1b-workspace'() {
      const page = await newPage();
      await loginAs('stub-definer'); await open(page, `/datasets/${IDS.sales.id}`); await gridReady(page);
      await shot(page, 'fu1b-s4-workspace-three-pane-definer');
      await page.locator('.column-list button', { hasText: '매출' }).click(); await sleep(300);
      await page.waitForSelector('[data-testid=type-locked]');
      await shot(page, 'fu1b-s4-inspector-column-edit-type-locked');
      await page.locator('.column-list button', { hasText: '구분' }).click(); await sleep(300);
      await shot(page, 'fu1b-s4-inspector-column-edit-choice-options');
      // 열 추가 폼: 숫자 규칙
      await page.getByRole('button', { name: '열 추가', exact: true }).first().click(); await sleep(300);
      const form = page.locator('form[aria-label="열 추가"]');
      await form.getByLabel('열 이름').fill('할인액'); await form.getByLabel('타입').selectOption('number');
      await form.getByLabel('필수 입력').check();
      await form.getByLabel('최솟값').fill('0'); await form.getByLabel('최댓값').fill('100000.50'); await form.getByLabel('소수 자릿수').fill('2');
      await form.getByLabel('구분 태그').fill('비용');
      await shot(page, 'fu1b-s4-inspector-add-column-number-rules');
      await form.getByLabel('열 이름').fill('team'); await sleep(300);
      await shot(page, 'fu1b-s4-inspector-add-column-error-reserved-name');
      await form.getByLabel('열 이름').fill('매출[합계]'); await sleep(300);
      await shot(page, 'fu1b-s4-inspector-add-column-error-forbidden-char');
      // 데이터셋 설정: 행이 있어 DATASET_HAS_ROWS
      await page.getByRole('button', { name: '데이터셋 설정' }).click(); await sleep(300);
      const sf = page.locator('form[aria-label="데이터셋 설정"]');
      await sf.getByLabel('날짜 단위').selectOption('day');
      await sf.getByRole('button', { name: '저장' }).click();
      await page.waitForSelector('[role=alert]'); await sleep(400);
      await shot(page, 'fu1b-s4-dataset-settings-error-has-rows');
      await page.close();
    },
    async 'fu1b-mismatch'() {
      const page = await newPage();
      await loginAs('stub-definer'); await open(page, `/datasets/${IDS.defn.id}`); await page.waitForSelector('.column-list');
      await page.getByRole('button', { name: '열 추가', exact: true }).first().click(); await sleep(300);
      const form = page.locator('form[aria-label="열 추가"]');
      await form.getByLabel('열 이름').fill('비고'); await form.getByLabel('타입').selectOption('text');
      // 다른 사람이 먼저 정의를 바꾼다(API)
      const v = await verOf('stub-definer', IDS.defn);
      const [st] = await api('stub-definer', `/datasets/${IDS.defn.id}/columns`, 'POST', { expected_version: v, display_name: '메모', type: 'text' });
      notes.push('mismatch 선행 API 상태 ' + st);
      await form.getByRole('button', { name: '열 추가' }).click();
      await page.waitForSelector('text=다른 사람이 먼저'); await sleep(600);
      await shot(page, 'fu1b-s4-version-mismatch-reload-notice');
      await page.close();
    },
    async 'fu1b-readonly'() {
      const page = await newPage();
      await loginAs('stub-viewer'); await open(page, `/datasets/${IDS.sales.id}`); await gridReady(page);
      await page.locator('.column-list button', { hasText: '매출' }).click(); await sleep(300);
      await page.waitForSelector('[data-testid=readonly-notice]');
      await shot(page, 'fu1b-s4-inspector-readonly-no-define-permission');
      await page.close();
    },
    // ---------------------------------------------------------------- 1c
    async 'fu1c-grid'() {
      const page = await newPage();
      await loginAs('stub-entry'); await open(page, `/datasets/${IDS.sales.id}`); await gridReady(page);
      await shot(page, 'fu1c-s4-entry-grid-overview');
      // 칸 편집 중
      await cell(page, 'r13', S['매출']).dblclick(); await sleep(250);
      await page.keyboard.press('Control+A'); await page.keyboard.type('224870.4');
      await shot(page, 'fu1c-s4-entry-grid-cell-editing');
      await page.keyboard.press('Escape'); await sleep(300);
      // 임시 새 행
      await page.locator(`[role=row][row-id="entry"] [col-id="${S['기준월']}"]`).dblclick(); await sleep(250);
      await page.keyboard.type('2026-11-01'); await page.keyboard.press('Enter'); await sleep(700);
      await page.waitForSelector('[aria-label="저장 전 새 행"]');
      await shot(page, 'fu1c-s4-entry-grid-draft-new-row');
      await page.getByRole('button', { name: '버리기' }).first().click().catch(() => undefined); await sleep(300);
      // 검증 오류 칸: 최솟값 0 미만
      await cell(page, 'r12', S['매출']).dblclick(); await sleep(250);
      await page.keyboard.press('Control+A'); await page.keyboard.type('-5'); await page.keyboard.press('Enter'); await sleep(1200);
      await page.waitForSelector('[aria-label="확인이 필요한 칸"]');
      await shot(page, 'fu1c-s4-entry-grid-validation-error');
      await page.close();
    },
    async 'fu1c-readonly'() {
      const page = await newPage();
      await loginAs('stub-viewer'); await open(page, `/datasets/${IDS.sales.id}`); await gridReady(page);
      await page.waitForSelector('[role=note]');
      await shot(page, 'fu1c-s4-entry-grid-readonly');
      await page.close();
    },
    async 'fu1c-wide'() {
      const page = await newPage();
      await loginAs('stub-multi'); await open(page, '/'); // 두 팀 소속: 작업 팀은 첫 활성 팀(A)이지만 열람은 어느 팀이든 가능
      await open(page, `/datasets/${IDS.wide.id}`); await gridReady(page);
      await shot(page, 'fu1c-s4-entry-grid-wide-scroll-left');
      await page.evaluate(() => { document.querySelector('.ag-body-horizontal-scroll-viewport').scrollLeft = 99999; });
      await sleep(500);
      await shot(page, 'fu1c-s4-entry-grid-wide-scroll-right-pinned-period');
      await page.close();
    },
    async 'fu1c-paste'() {
      const page = await newPage();
      await loginAs('stub-entry'); await open(page, `/datasets/${IDS.sales.id}`); await gridReady(page);
      // 혼합: 가장 오래된 기존 행(2025-10-01)부터 기존 1행 + 새 2행
      const oldest = await rowByDate('stub-entry', IDS.sales, '기준월', '2025-10-01');
      await cell(page, 'r' + oldest.row_id, S['기준월']).click(); await sleep(250);
      const dp = await paste(page, '2025-10-01\t125000.5\t김민수\r\n2025-09-01\t90000\t박지연\r\n2025-08-01\t80500.25\t\r\n');
      notes.push('mixed paste defaultPrevented=' + dp);
      await page.waitForSelector('[aria-label="붙여넣기 확인"]');
      await shot(page, 'fu1c-s4-paste-confirm-mixed-existing-and-new');
      await page.locator('[aria-label="붙여넣기 확인"] button.primary').click();
      await page.waitForSelector('[aria-label="붙여넣기 결과"]'); await sleep(700);
      await shot(page, 'fu1c-s4-paste-result-ok');
      await page.close();
    },
    async 'fu1c-paste-conflict'() {
      const page = await newPage();
      await loginAs('stub-entry'); await open(page, `/datasets/${IDS.sales.id}`); await gridReady(page);
      const oldest = await rowByDate('stub-entry', IDS.sales, '기준월', '2025-08-01');
      if (!oldest) throw new Error('먼저 fu1c-paste를 실행해야 한다');
      await cell(page, 'r' + oldest.row_id, S['기준월']).click(); await sleep(250);
      await paste(page, '2025-08-01\t11111\t가나다\r\n2025-07-01\t22222\t라마바\r\n');
      await page.waitForSelector('[aria-label="붙여넣기 확인"]');
      // 확인창이 열린 사이 다른 클라이언트가 같은 칸을 바꾸고, 새 행 기간을 먼저 만든다
      const v = await verOf('stub-definer', IDS.sales);
      const s1 = await api('stub-definer', `/datasets/${IDS.sales.id}/rows/${oldest.row_id}`, 'PATCH', { expected_version: v, changes: [{ column_id: S['매출'], expected: oldest.cells[S['매출']], value: '33333' }] });
      const s2 = await api('stub-definer', `/datasets/${IDS.sales.id}/rows`, 'POST', { expected_version: v, cells: { [S['기준월']]: '2025-07-01', [S['매출']]: '44444' } });
      notes.push(`paste-conflict 선행 API ${s1[0]}/${s2[0]}`);
      await page.locator('[aria-label="붙여넣기 확인"] button.primary').click();
      await page.waitForSelector('[aria-label="붙여넣기 결과"]'); await sleep(700);
      await shot(page, 'fu1c-s4-paste-conflict-all-cancelled');
      await page.close();
    },
    async 'fu1c-cell-conflict'() {
      const page = await newPage();
      await loginAs('stub-entry'); await open(page, `/datasets/${IDS.sales.id}`); await gridReady(page);
      const newest = await rowByDate('stub-entry', IDS.sales, '기준월', '2026-10-01');
      const v = await verOf('stub-definer', IDS.sales);
      const r = await api('stub-definer', `/datasets/${IDS.sales.id}/rows/${newest.row_id}`, 'PATCH', { expected_version: v, changes: [{ column_id: S['담당'], expected: newest.cells[S['담당']], value: '정이후' }] });
      notes.push('cell-conflict 선행 API ' + r[0]);
      await cell(page, 'r' + newest.row_id, S['담당']).dblclick(); await sleep(250);
      await page.keyboard.press('Control+A'); await page.keyboard.type('내가입력'); await page.keyboard.press('Enter');
      await page.waitForSelector('[aria-label="충돌 목록"]'); await sleep(700);
      await shot(page, 'fu1c-s4-cell-conflict-orange-border');
      await page.close();
    },
    async 'fu1c-too-many'() {
      const page = await newPage();
      await loginAs('stub-entry'); await open(page, `/datasets/${IDS.sales.id}`); await gridReady(page);
      await page.locator(`[role=row][row-id="entry"] [col-id="${S['기준월']}"]`).click(); await sleep(250);
      const lines = []; for (let i = 0; i < 5001; i++) lines.push(`2100-01-${String((i % 28) + 1).padStart(2, '0')}\t${i}`);
      await paste(page, lines.join('\r\n') + '\r\n');
      await page.waitForSelector('[aria-label="붙여넣기 오류"]');
      await shot(page, 'fu1c-s4-paste-rejected-over-5000-rows');
      await page.close();
    },
  };

  const order = Object.keys(scenarios);
  for (const name of order) {
    if (ONLY.length && !ONLY.includes(name)) continue;
    try { await scenarios[name](); } catch (e) { console.log('실패', name, String(e.message).slice(0, 300)); notes.push('실패 ' + name + ': ' + String(e.message).slice(0, 200)); }
  }
  await browser.close();

  // 비밀값 검사: 임시 env의 비밀성 값이 촬영 순간의 DOM(텍스트·HTML)에 있는지, 내부 경로·예외 흔적이 있는지
  const secrets = [];
  if (ENV_FILE) for (const line of fs.readFileSync(ENV_FILE, 'utf8').split('\n')) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/); if (m && /PASSWORD|SECRET|KEY|TOKEN/.test(m[1]) && m[2].length >= 6) secrets.push([m[1], m[2]]);
  }
  const patterns = [/qaDummy/i, /Traceback/, /\/home\//, /\/app\//, /postgres(ql)?:\/\//i, /bi_stub_login/, /Authorization/i, /Bearer /];
  let hits = 0;
  for (const d of dumps) {
    for (const [k, v] of secrets) if (d.text.includes(v) || d.html.includes(v)) { hits++; console.log('비밀값 발견', d.name, k); }
    for (const p of patterns) if (p.test(d.text) || p.test(d.html)) { hits++; console.log('의심 패턴', d.name, String(p)); }
  }
  console.log(`비밀값 검사: 대상 ${dumps.length}장, 비밀 변수 ${secrets.length}개, 발견 ${hits}건`);
  if (DUMP) fs.writeFileSync(DUMP, dumps.map((d) => `=== ${d.name}\n${d.text}\n`).join('\n'));
  console.log('메모:', JSON.stringify(notes, null, 1));
  console.log('촬영 파일', made.length);
})().catch((e) => { console.log('스크립트 오류', e.stack); process.exit(1); });
