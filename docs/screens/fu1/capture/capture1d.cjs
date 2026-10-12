// FU-1 1d(수식 열) 화면 스크린샷 촬영(Playwright, headless Chromium, 1920x1080, deviceScaleFactor 1).
//
// 사용:
//   node capture1d.cjs --origin http://127.0.0.1:65173 --base /bi-wizard --ids ids1d.json --out ../ \
//        --env 임시-env-파일 [--only 이름,이름] [--dump 페이지텍스트덤프.txt]
// 사전 조건: 스택(스텁 켬) + seed-stub-users + seed1d.py로 합성 데이터를 넣은 새 DB.
// 단계(--only로 나눠 실행한다. 사이에 DB 조작이 필요하다):
//   1) editor-* , grid, formula-view, s5, s9-ok       (읽기 위주; editor-* 는 저장하지 않는다)
//   2) (셸에서) 뷰 두 개를 DROP VIEW로 깨뜨리고 데이터셋 행 잠금을 쥔 채 backend 재시작 -> s9-failed
//   3) fixdata (0으로 나눔 원인 값을 고침), s5-empty, result-type-changed(마지막: 등급 열의 결과 종류를 바꾼다)
// playwright는 저장소 의존성이 아니다(PLAYWRIGHT_MODULE, CHROMIUM_PATH 환경변수).
const fs = require('fs');
const path = require('path');

const arg = (name, def) => { const i = process.argv.indexOf('--' + name); return i >= 0 ? process.argv[i + 1] : def; };
const ORIGIN = arg('origin'), BASE = arg('base', ''), OUT = path.resolve(arg('out', '.'));
const IDS = JSON.parse(fs.readFileSync(arg('ids'), 'utf8'));
const ENV_FILE = arg('env'), ONLY = (arg('only', '') || '').split(',').filter(Boolean), DUMP = arg('dump');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const CHROMIUM = process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const PL = IDS.pl, AR = IDS.ar;

const dumps = [], made = [], notes = [];

(async () => {
  const browser = await chromium.launch({ executablePath: CHROMIUM, args: ['--no-sandbox'], ignoreDefaultArgs: ['--hide-scrollbars'] });
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1, locale: 'ko-KR', timezoneId: 'Asia/Seoul' });
  const apiUrl = (p) => `${ORIGIN}${BASE}/api${p}`;
  const loginAs = async (user) => {
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
  const settle = async (page, ms = 400) => {
    await page.waitForLoadState('networkidle').catch(() => undefined);
    for (let i = 0; i < 40; i++) {
      if (!(await page.locator('.state-loading').count())) break;
      await sleep(150);
    }
    await sleep(ms);
  };
  const shot = async (page, name, opts = {}) => {
    await page.mouse.move(1910, 1070);
    await settle(page, opts.wait ?? 400);
    const text = await page.evaluate(() => document.body.innerText);
    if (/불러오는 중/.test(text) && !opts.allowLoading) throw new Error(name + ': 아직 불러오는 중이다');
    await page.screenshot({ path: path.join(OUT, name + '.png'), animations: 'disabled', caret: 'hide' });
    dumps.push({ name, text, html: await page.evaluate(() => document.documentElement.outerHTML) });
    made.push(name + '.png');
    console.log('촬영', name);
  };
  const open = async (page, route) => { await page.goto(`${ORIGIN}${BASE}${route}`, { waitUntil: 'networkidle' }); await settle(page, 300); };
  const gridReady = async (page) => { await page.waitForSelector('[role=row][row-id^="r"]'); await settle(page, 500); };
  const workspace = async (page, user, ds) => { await loginAs(user); await open(page, `/datasets/${ds.id}`); await gridReady(page); };
  const colBtn = (page, name) => page.locator('.column-list button', { hasText: name }).first();
  const editorBox = (page) => page.locator('form.formula-editor');
  const expr = (page) => page.locator('form.formula-editor textarea');
  const openAddFormula = async (page) => {
    await page.getByRole('button', { name: '계산 열 추가', exact: true }).first().click();
    await page.waitForSelector('form.formula-editor');
    await sleep(300);
  };
  const scrollTo = (page, selector, block = 'start') => page.evaluate(([sel, b]) => { const el = document.querySelector(sel); if (el) el.scrollIntoView({ block: b }); }, [selector, block]);
  const waitCheck = (page) => page.waitForFunction(() => /수식에 문제가 없습니다|수식에 고칠 곳이 있습니다|수식을 확인하지 못했습니다/.test(document.querySelector('[data-testid=check-status]')?.textContent || ''), null, { timeout: 8000 });
  const waitPreview = (page) => page.waitForSelector('[data-testid=preview-summary]', { timeout: 10000 });
  const typeExpr = async (page, text) => { await expr(page).fill(text); await expr(page).evaluate((el) => el.setSelectionRange(el.value.length, el.value.length)); };

  const scenarios = {
    // ---------------------------------------------------------------- 수식 편집기
    async 'editor-empty'() {
      const page = await newPage();
      await workspace(page, 'stub-definer', PL);
      await openAddFormula(page);
      await shot(page, 'fu1d-editor-empty-new-formula-column');
      await page.close();
    },
    async 'editor-chip'() {
      const page = await newPage();
      await workspace(page, 'stub-definer', PL);
      await openAddFormula(page);
      await page.locator('form.formula-editor input').first().fill('인당 매출 시험');
      await expr(page).click();
      const chip = (n) => page.locator('.formula-chips button', { hasText: new RegExp('^' + n + '$') });
      await chip('매출').click();
      await page.keyboard.type(' / ');
      await chip('인원').click();
      await shot(page, 'fu1d-editor-column-chip-inserted', { wait: 100 });
      await page.close();
    },
    async 'editor-autocomplete'() {
      const page = await newPage();
      await workspace(page, 'stub-definer', PL);
      await openAddFormula(page);
      await expr(page).click();
      await page.keyboard.type('RO');
      await page.waitForSelector('[role=listbox]');
      await page.keyboard.press('ArrowDown');
      await shot(page, 'fu1d-editor-autocomplete-function-list', { wait: 50 });
      await expr(page).fill('');
      await page.keyboard.type('[');
      await page.waitForSelector('[role=listbox]');
      await shot(page, 'fu1d-editor-autocomplete-column-list', { wait: 50 });
      await expr(page).fill('');
      await page.keyboard.type('SUMTAG("');
      await page.waitForSelector('[role=listbox]');
      await shot(page, 'fu1d-editor-autocomplete-tag-list', { wait: 50 });
      await page.close();
    },
    async 'editor-errors'() {
      const page = await newPage();
      await workspace(page, 'stub-definer', PL);
      await openAddFormula(page);
      const cases = [
        ['[없는열]*2', 'fu1d-editor-error-unknown-column'],
        ['ROUND([매출])', 'fu1d-editor-error-arg-count'],
        ['[담당]+1', 'fu1d-editor-error-type-mismatch-text-plus-number'],
        ['LEFT([담당],2)&"-"&[1인당 매출]', 'fu1d-editor-error-type-mismatch-ampersand-number'],
        ['ROUND([매출]/3, 2', 'fu1d-editor-error-unclosed-parenthesis'],
      ];
      for (const [text, name] of cases) {
        await typeExpr(page, text);
        await page.waitForSelector('.formula-errors', { timeout: 8000 });
        await sleep(300);
        await scrollTo(page, 'form.formula-editor .formula-input', 'start');
        await shot(page, name, { wait: 200 });
      }
      await page.close();
    },
    async 'editor-preview-ok'() {
      const page = await newPage();
      await workspace(page, 'stub-definer', PL);
      await openAddFormula(page);
      await typeExpr(page, '[매출]-[물류비]');
      await waitCheck(page);
      await waitPreview(page);
      await sleep(400);
      await shot(page, 'fu1d-editor-check-ok-top', { wait: 100 });
      await scrollTo(page, 'section.formula-preview', 'start');
      await shot(page, 'fu1d-editor-preview-ok-20-rows', { wait: 200 });
      await page.close();
    },
    async 'editor-preview-mixed'() {
      const page = await newPage();
      await workspace(page, 'stub-definer', PL);
      await openAddFormula(page);
      await typeExpr(page, '[매출]/[인원]');
      await waitCheck(page);
      await waitPreview(page);
      await sleep(400);
      await scrollTo(page, 'section.formula-preview', 'start');
      await shot(page, 'fu1d-editor-preview-error-and-empty-cells', { wait: 200 });
      await page.close();
    },
    async 'editor-preview-busy'() {
      // PREVIEW_BUSY는 실제 서버에서 재현하기 어려워(사용자당 동시 1건이 너무 빨리 끝난다) 브라우저에서 미리보기 응답만 429로 바꿔 화면 상태를 촬영한다(모의).
      const page = await newPage();
      await workspace(page, 'stub-definer', PL);
      await page.route('**/formulas/preview', (route) => route.fulfill({
        status: 429, contentType: 'application/json', headers: { 'Retry-After': '5' },
        body: JSON.stringify({ error: { code: 'PREVIEW_BUSY', message: '지금 계산 요청이 많습니다. 잠시 뒤 다시 시도해 주세요.', details: { retry_after: 5 }, request_id: 'shot-mock' } }),
      }));
      await openAddFormula(page);
      await typeExpr(page, '[매출]-[물류비]');
      await waitCheck(page);
      await page.waitForSelector('text=자동으로 다시 시도합니다', { timeout: 8000 });
      await scrollTo(page, 'section.formula-preview', 'start');
      await shot(page, 'fu1d-editor-preview-busy-auto-retrying', { wait: 100 });
      await page.waitForSelector('button:has-text("다시 시도")', { timeout: 15000 });
      await scrollTo(page, 'section.formula-preview', 'start');
      await shot(page, 'fu1d-editor-preview-busy-retry-button', { wait: 100 });
      await page.close();
    },
    async 'editor-circular'() {
      const page = await newPage();
      await workspace(page, 'stub-definer', PL);
      await colBtn(page, '손익').click();
      await page.getByRole('button', { name: '수식 고치기' }).click();
      await page.waitForSelector('form.formula-editor');
      await typeExpr(page, '[손익률]+1');
      await waitCheck(page);
      await sleep(500);
      const checkText = await page.locator('[data-testid=check-status]').innerText();
      notes.push('circular 검사 문구: ' + checkText);
      await scrollTo(page, '.formula-errors', 'center');
      await shot(page, 'fu1d-editor-circular-after-check', { wait: 150 });
      if (await page.locator('.formula-errors').count() === 0) {
        await page.getByRole('button', { name: '수식 저장' }).click();
        await page.waitForSelector('text=순환', { timeout: 8000 });
        await scrollTo(page, 'form.formula-editor h2', 'start');
        await shot(page, 'fu1d-editor-circular-path-on-save', { wait: 200 });
      } else {
        // 검사 단계에서 이미 오류면 저장 시도는 막힌다
        notes.push('circular: 검사 단계에서 오류 표시(저장 버튼 막힘)');
      }
      await page.close();
    },
    async 'editor-readonly'() {
      const page = await newPage();
      await workspace(page, 'stub-viewer', PL);
      await colBtn(page, '1인당 매출').click();
      await page.waitForSelector('[data-testid=formula-readonly]');
      await scrollTo(page, 'section.formula-view', 'start');
      await shot(page, 'fu1d-formula-view-readonly-no-define-permission-viewer');
      await page.close();
    },
    // ---------------------------------------------------------------- 입력 그리드
    async 'grid'() {
      const page = await newPage();
      await workspace(page, 'stub-entry', PL);
      await shot(page, 'fu1d-grid-calculated-columns-overview');
      await page.evaluate(() => { document.querySelector('.ag-body-horizontal-scroll-viewport').scrollLeft = 99999; });
      await sleep(500);
      await shot(page, 'fu1d-grid-calculated-columns-scrolled-right');
      // 계산 열 칸 편집 시도(읽기 전용)
      const errCell = page.locator('.cell-formula.cell-error').first();
      await errCell.dblclick().catch(() => notes.push('오류 칸 더블클릭 실패'));
      await sleep(400);
      const editing = await page.locator('.ag-cell-inline-editing, .ag-cell-editing-input').count();
      notes.push('계산 열 칸 더블클릭 후 편집기 수 ' + editing);
      await page.keyboard.type('123');
      await sleep(300);
      await shot(page, 'fu1d-grid-calculated-cell-edit-attempt', { wait: 200 });
      // 열 폭을 마우스로 넓혀(사용자 조작) 오류 칸의 코드(E1)와 값 전체가 보이게 한다.
      await page.keyboard.press('Escape');
      await page.evaluate(() => { document.querySelector('.ag-body-horizontal-scroll-viewport').scrollLeft = 0; });
      const hdr = page.locator(`.ag-header-cell[col-id="${PL.cols['1인당 매출']}"]`);
      await hdr.scrollIntoViewIfNeeded();
      await page.evaluate((id) => { const h = document.querySelector(`.ag-header-cell[col-id="${id}"]`); h.scrollIntoView({ inline: 'center' }); }, String(PL.cols['1인당 매출']));
      await sleep(300);
      const rz = await page.locator(`.ag-header-cell[col-id="${PL.cols['1인당 매출']}"] .ag-header-cell-resize`).boundingBox();
      if (rz) {
        await page.mouse.move(rz.x + rz.width / 2, rz.y + rz.height / 2);
        await page.mouse.down(); await page.mouse.move(rz.x + 120, rz.y + rz.height / 2, { steps: 8 }); await page.mouse.up();
        await sleep(400);
        await shot(page, 'fu1d-grid-error-cell-e1-and-blank-cells-widened-column', { wait: 200 });
      } else notes.push('열 폭 조절 손잡이를 찾지 못함');
      await page.close();
    },
    // ---------------------------------------------------------------- 수식 보기
    async 'formula-view'() {
      const page = await newPage();
      await workspace(page, 'stub-entry', PL);
      await colBtn(page, '1인당 매출').click();
      await page.waitForSelector('[data-testid=formula-text]');
      await scrollTo(page, 'section.formula-view', 'start');
      await shot(page, 'fu1d-formula-view-division-with-error-cells-entry');
      await colBtn(page, '총비용').click();
      await page.waitForSelector('[data-testid=formula-tag-columns]');
      await scrollTo(page, 'section.formula-view', 'start');
      await shot(page, 'fu1d-formula-view-sumtag-with-tag-columns-entry');
      await page.close();
      const p2 = await newPage();
      await workspace(p2, 'stub-definer', PL);
      await colBtn(p2, '손익률').click();
      await p2.waitForSelector('[data-testid=formula-text]');
      await scrollTo(p2, 'section.formula-view', 'start');
      await shot(p2, 'fu1d-formula-view-definer-with-edit-button');
      await p2.getByRole('button', { name: '수식 고치기' }).click();
      await p2.waitForSelector('form.formula-editor');
      await sleep(900);
      await scrollTo(p2, 'section.formula-view', 'start');
      await shot(p2, 'fu1d-formula-edit-opened-definer');
      await p2.close();
    },
    // ---------------------------------------------------------------- S5
    async 's5'() {
      const page = await newPage();
      await loginAs('stub-viewer'); await open(page, '/checks');
      await page.waitForSelector('table[aria-label="계산 오류 칸이 있는 열"]');
      await shot(page, 'fu1d-s5-checks-error-columns-list');
      await page.getByRole('button', { name: '오류 칸 보기' }).first().click();
      await page.waitForSelector('[role=group].error-cells table');
      await shot(page, 'fu1d-s5-checks-error-cells-expanded');
      await page.close();
      const p2 = await newPage();
      await open(p2, `/checks?dataset=${PL.id}&column=${PL.cols['1인당 매출']}`);
      await p2.waitForSelector('[role=group].error-cells table');
      await shot(p2, 'fu1d-s5-checks-deeplink-from-formula-view');
      await p2.close();
    },
    // ---------------------------------------------------------------- S9
    async 's9-ok'() {
      const page = await newPage();
      await loginAs('stub-admin'); await open(page, '/admin/status');
      await page.waitForSelector('section[aria-label="뷰 재생성"] [data-testid=views-summary]');
      await scrollTo(page, 'section[aria-label="뷰 재생성"]', 'start');
      await shot(page, 'fu1d-s9-views-section-normal');
      await page.close();
    },
    async 's9-failed'() {
      // 사전: 셸에서 DROP VIEW 두 개 + 데이터셋 행 잠금을 쥔 채 backend 재시작(시작 때 LOCK_TIMEOUT으로 실패 기록). 잠금은 LOCK_RELEASE_MS 뒤 풀린다.
      const page = await newPage();
      await loginAs('stub-admin'); await open(page, '/admin/status');
      await page.waitForSelector('table[aria-label="뷰 재생성 실패 목록"]');
      await scrollTo(page, 'section[aria-label="뷰 재생성"]', 'start');
      await shot(page, 'fu1d-s9-views-section-failed-list');
      // 잠금이 아직 있는 동안 다시 시도하면 다시 실패한다(또는 다른 작업 진행 중 안내)
      await page.getByRole('button', { name: '이 데이터셋 다시 시도' }).first().click();
      await sleep(4000);
      await scrollTo(page, 'section[aria-label="뷰 재생성"]', 'start');
      await shot(page, 'fu1d-s9-views-section-retry-while-locked');
      // 잠금이 풀릴 때까지 기다린 뒤 다시 시도
      await sleep(Number(process.env.LOCK_WAIT_MS || 0));
      await open(page, '/admin/status');
      await page.waitForSelector('button:has-text("이 데이터셋 다시 시도")');
      await page.getByRole('button', { name: '이 데이터셋 다시 시도' }).first().click();
      await page.waitForSelector('[data-testid=views-retry-result]');
      await sleep(800);
      await scrollTo(page, 'section[aria-label="뷰 재생성"]', 'start');
      await shot(page, 'fu1d-s9-views-section-after-single-retry');
      if (await page.getByRole('button', { name: '실패한 항목 전부 다시 시도' }).count()) {
        await page.getByRole('button', { name: '실패한 항목 전부 다시 시도' }).click();
        await page.waitForSelector('[data-testid=no-failed-views]', { timeout: 15000 });
      }
      await sleep(500);
      await scrollTo(page, 'section[aria-label="뷰 재생성"]', 'start');
      await shot(page, 'fu1d-s9-views-section-recovered');
      await page.close();
    },
    // ---------------------------------------------------------------- 데이터 고치기 후
    async 'fixdata'() {
      for (const [ds, colName, user] of [[PL, '인원', 'stub-definer'], [AR, '청구', 'stub-multi']]) {
        const rows = (await api(user, `/datasets/${ds.id}/rows?order=desc&limit=200`))[1].items;
        const cid = String(ds.cols[colName]);
        for (const r of rows) {
          if (r.cells[cid] === '0' || r.cells[cid] === 0 || /^0(\.0+)?$/.test(String(r.cells[cid]))) {
            const v = (await api(user, `/datasets/${ds.id}`))[1].def_version;
            const [st] = await api(user, `/datasets/${ds.id}/rows/${r.row_id}`, 'PATCH', { expected_version: v, changes: [{ column_id: ds.cols[colName], expected: r.cells[cid], value: '5' }] });
            notes.push(`fixdata ${ds.id}/${r.row_id} ${st}`);
          }
        }
      }
    },
    async 's5-empty'() {
      const page = await newPage();
      await loginAs('stub-viewer'); await open(page, '/checks');
      await page.waitForSelector('[data-testid=no-formula-errors]');
      await shot(page, 'fu1d-s5-checks-empty-no-errors');
      await page.close();
      const p2 = await newPage();
      await workspace(p2, 'stub-entry', PL);
      await colBtn(p2, '1인당 매출').click();
      await p2.waitForSelector('[data-testid=formula-text]');
      await scrollTo(p2, 'section.formula-view', 'start');
      await shot(p2, 'fu1d-formula-view-no-error-cells-entry');
      await p2.close();
    },
    async 'result-type-changed'() {
      const page = await newPage();
      await workspace(page, 'stub-definer', PL);
      await colBtn(page, '등급').click();
      await page.getByRole('button', { name: '수식 고치기' }).click();
      await page.waitForSelector('form.formula-editor');
      const cur = await expr(page).inputValue();   // 다시 실행해도 결과 종류가 바뀌도록 번갈아 쓴다
      await typeExpr(page, cur.includes('"A"') ? 'IF([매출]>1000000,1,0)' : 'IF([매출]>1000000,"A","B")');
      await waitCheck(page);
      await waitPreview(page);
      await page.getByRole('button', { name: '수식 저장' }).click();
      await page.waitForSelector('text=결과 종류가 바뀌었습니다', { timeout: 8000 });
      await sleep(500);
      await page.locator('text=결과 종류가 바뀌었습니다').first().scrollIntoViewIfNeeded();
      await shot(page, 'fu1d-editor-result-type-changed-notice', { wait: 200 });
      await page.close();
    },
  };

  for (const name of Object.keys(scenarios)) {
    if (ONLY.length && !ONLY.includes(name)) continue;
    try { await scenarios[name](); } catch (e) { console.log('실패', name, String(e.message).slice(0, 400)); notes.push('실패 ' + name + ': ' + String(e.message).slice(0, 300)); }
  }
  await browser.close();

  const secrets = [];
  if (ENV_FILE) for (const line of fs.readFileSync(ENV_FILE, 'utf8').split('\n')) {
    const m = line.match(/^([A-Z0-9_]+)=(.*)$/); if (m && /PASSWORD|SECRET|KEY|TOKEN/.test(m[1]) && m[2].length >= 6) secrets.push([m[1], m[2]]);
  }
  const patterns = [/qaDummy/i, /Traceback/, /\/home\//, /\/app\//, /postgres(ql)?:\/\//i, /bi_stub_login/, /Authorization/i, /Bearer /, /SELECT .* FROM/i, /bi_data\./];
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
