// FU-1 1e(Superset 연동) 화면 스크린샷 촬영(Playwright, headless Chromium, 1920x1080, deviceScaleFactor 1).
//
// 사용:
//   node capture1e.cjs --origin http://127.0.0.1:36180 --base /bi-wizard --ids ids1e.json --out ../ \
//        --env 임시-env-파일 --only 이름,이름 [--dump 페이지텍스트덤프.txt]
// 사전 조건: 스택(스텁 켬, Superset 포함) + seed-stub-users + seed1e.py portal/superset으로 합성 데이터를 넣은 새 DB.
// 비밀값은 환경변수로만 받는다: Superset 관리자 로그인이 필요한 'superset-calc' 단계만 SUPERSET_ADMIN_USER, SUPERSET_ADMIN_PASSWORD를 읽는다.
// 단계는 사이사이에 컨테이너 조작(docker pause/stop/start)이 필요해 --only로 나눠 실행한다. README의 1e 재촬영 방법을 따른다.
// playwright는 저장소 의존성이 아니다(PLAYWRIGHT_MODULE, CHROMIUM_PATH 환경변수).
const fs = require('fs');
const path = require('path');

const arg = (name, def) => { const i = process.argv.indexOf('--' + name); return i >= 0 ? process.argv[i + 1] : def; };
const ORIGIN = arg('origin'), BASE = arg('base', ''), OUT = path.resolve(arg('out', '.'));
const IDS = JSON.parse(fs.readFileSync(arg('ids'), 'utf8'));
const ENV_FILE = arg('env'), ONLY = (arg('only', '') || '').split(',').filter(Boolean), DUMP = arg('dump');
const pw = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const { chromium } = pw;
const CHROMIUM = process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const D1 = IDS.d1, D2 = IDS.d2, D3 = IDS.d3;

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
    return [r.status(), j, r.headers()];
  };
  const newPage = async () => {
    const page = await ctx.newPage();
    page.on('pageerror', (e) => notes.push('pageerror: ' + String(e).slice(0, 200)));
    return page;
  };
  const frameOf = (page) => page.frames().find((f) => /\/embedded\//.test(f.url()));
  const settle = async (page, ms = 400) => {
    await page.waitForLoadState('networkidle').catch(() => undefined);
    for (let i = 0; i < 40; i++) {
      if (!(await page.locator('.state-loading').count())) break;
      await sleep(150);
    }
    await sleep(ms);
  };
  // 포털 페이지 + (있으면) iframe 안 글자도 비밀 검사 대상으로 모은다.
  const shot = async (page, name, opts = {}) => {
    await page.mouse.move(1910, 1070);
    if (!opts.noSettle) await settle(page, opts.wait ?? 400);
    else await sleep(opts.wait ?? 100);
    let text = await page.evaluate(() => document.body.innerText);
    if (/불러오는 중/.test(text) && !opts.allowLoading) throw new Error(name + ': 아직 불러오는 중이다');
    let html = await page.evaluate(() => document.documentElement.outerHTML);
    const f = frameOf(page);
    if (f) { try { text += '\n[iframe]\n' + (await f.evaluate(() => document.body.innerText)); html += await f.evaluate(() => document.documentElement.outerHTML); } catch (e) { /* 다른 문서 */ } }
    await page.screenshot({ path: path.join(OUT, name + '.png'), animations: 'disabled', caret: 'hide' });
    dumps.push({ name, text, html });
    made.push(name + '.png');
    console.log('촬영', name);
  };
  const open = async (page, route) => { await page.goto(`${ORIGIN}${BASE}${route}`, { waitUntil: 'networkidle' }); await settle(page, 300); };
  // 임베드 안의 차트 6개가 모두 그려질 때까지 기다린다(그림 요소와 로딩 표시 없음).
  const chartsReady = async (page, count = 6) => {
    for (let i = 0; i < 120; i++) {
      const f = frameOf(page);
      if (f) {
        const info = await f.evaluate(() => [...document.querySelectorAll('[data-test-chart-id]')].map((e) => ({
          drawn: e.querySelectorAll('canvas').length + e.querySelectorAll('svg').length + e.querySelectorAll('table').length,
          loading: !!e.querySelector('.loading, [data-test="loading-indicator"]'),
        }))).catch(() => []);
        if (info.length >= count && info.every((c) => c.drawn > 0 && !c.loading)) { await sleep(1500); return; }
      }
      await sleep(500);
    }
    throw new Error('차트가 모두 그려지지 않았다');
  };
  const dashUrl = (d) => `/dashboards?d=${d.portal_id}`;

  const scenarios = {
    // ---------------------------------------------------------------- S7 (정상 단계)
    async 's7-select'() {
      const page = await newPage();
      await loginAs('stub-viewer'); await open(page, '/dashboards');
      await page.waitForSelector('[data-testid=pick-dashboard]');
      await shot(page, 'fu1e-s7-dashboard-select-prompt');
      await page.close();
    },
    async 's7-loading'() {
      // 입장권 응답을 6초 늦춰 "불러오는 중" 상태를 만든다(브라우저 쪽 지연 주입. 서버·화면 코드는 그대로).
      const page = await newPage();
      await page.route('**/guest-token', async (route) => { await sleep(6000); await route.continue(); });
      await loginAs('stub-viewer');
      await page.goto(`${ORIGIN}${BASE}${dashUrl(D1)}`, { waitUntil: 'domcontentloaded' });
      await page.waitForSelector('.dashboard-view .state-loading', { timeout: 10000 });
      await sleep(600);
      await shot(page, 'fu1e-s7-dashboard-loading', { noSettle: true, allowLoading: true });
      await page.unroute('**/guest-token');
      await page.close();
    },
    async 's7-six'() {
      const page = await newPage();
      await loginAs('stub-viewer'); await open(page, dashUrl(D1));
      await chartsReady(page);
      await shot(page, 'fu1e-s7-dashboard-six-charts-viewer');
      // 임베드 화면(iframe) 안을 맨 아래로 스크롤해 둘째 줄(큰 숫자·원형·혼합)이 온전히 보이게 한다.
      await page.mouse.move(1200, 700);
      await page.mouse.wheel(0, 3000);
      await sleep(2500);
      await shot(page, 'fu1e-s7-dashboard-six-charts-viewer-scrolled-down');
      await page.close();
    },
    async 's7-guide'() {
      const page = await newPage();
      await loginAs('stub-viewer'); await open(page, '/dashboards');
      await page.locator('details.author-guide summary').click();
      await sleep(300);
      await shot(page, 'fu1e-s7-author-guide-open');
      await page.close();
    },
    async 's7-blank'() {
      // 허용 도메인이 포털 주소와 다른 대시보드: 입장권은 발급되지만 Superset이 403 JSON을 돌려줘 iframe 안이 비어 있다.
      const page = await newPage();
      await loginAs('stub-viewer'); await open(page, dashUrl(D3));
      await page.waitForSelector('[data-testid=embed-blank-hint]', { timeout: 40000 });
      await shot(page, 'fu1e-s7-dashboard-blank-allowed-domains');
      await page.close();
    },
    async 's7-429'() {
      // 같은 사용자가 60초에 30회를 넘게 입장권을 요청한다(실제 한도). 응답 본문(입장권)은 읽지 않고 상태 번호만 센다.
      const user = 'stub-entry';
      let last = 0; const codes = {};
      for (let i = 0; i < 33; i++) {
        const r = await ctx.request.post(apiUrl(`/dashboards/${D1.portal_id}/guest-token`), { headers: { cookie: 'bi_stub_login=' + user } });
        last = r.status(); codes[last] = (codes[last] || 0) + 1;
      }
      notes.push('입장권 요청 상태 분포 ' + JSON.stringify(codes));
      const page = await newPage();
      await loginAs(user); await open(page, dashUrl(D1));
      await page.waitForSelector('[data-testid=embed-failed]', { timeout: 20000 });
      await shot(page, 'fu1e-s7-dashboard-error-429-rate-limited');
      await page.close();
    },
    async 's7-nodash'() {
      // 연결된 대시보드가 하나도 없는 상태: 관리자가 모두 해제했다가 되돌린다.
      const rows = (await api('stub-admin', '/dashboards?include_inactive=true&limit=100'))[1].items;
      const active = rows.filter((r) => r.is_active);
      try {
        for (const r of active) await api('stub-admin', `/dashboards/${r.id}`, 'PATCH', { is_active: false });
        const page = await newPage();
        await loginAs('stub-viewer'); await open(page, '/dashboards');
        await page.waitForSelector('[data-testid=no-dashboards]');
        await shot(page, 'fu1e-s7-dashboard-none-linked');
        await page.close();
      } finally {
        for (const r of active) await api('stub-admin', `/dashboards/${r.id}`, 'PATCH', { is_active: true });
      }
    },
    async 's7-502'() {
      // 1e-f 추가: 관리자가 Superset에서 대시보드의 임베드를 껐다(D3). 포털 연결은 그대로 남아 입장권 발급이 Superset에 거부된다(502).
      // 비밀번호는 환경변수로만 받는다(SUPERSET_ADMIN_USER, SUPERSET_ADMIN_PASSWORD). 화면에는 나오지 않는다.
      const user = process.env.SUPERSET_ADMIN_USER, pass = process.env.SUPERSET_ADMIN_PASSWORD;
      if (!user || !pass) throw new Error('SUPERSET_ADMIN_USER/PASSWORD 환경변수가 필요하다');
      const root = `${ORIGIN}${BASE}/superset`;
      const sctx = await pw.request.newContext();
      const login = await sctx.post(`${root}/api/v1/security/login`, { data: { username: user, password: pass, provider: 'db', refresh: true } });
      if (login.status() !== 200) throw new Error('Superset 로그인 ' + login.status());
      const bearer = { Authorization: 'Bearer ' + (await login.json()).access_token };
      const csrf = (await (await sctx.get(`${root}/api/v1/security/csrf_token/`, { headers: bearer })).json()).result;
      const del = await sctx.delete(`${root}/api/v1/dashboard/${D3.superset_id}/embedded`, { headers: { ...bearer, 'X-CSRFToken': csrf, Referer: root + '/' } });
      notes.push('임베드 해제 응답 ' + del.status());
      await sctx.dispose();
      const page = await newPage();
      await loginAs('stub-viewer'); await open(page, dashUrl(D3));
      await page.waitForSelector('[data-testid=embed-failed]', { timeout: 30000 });
      await shot(page, 'fu1e-s7-dashboard-error-502-embed-disabled');
      await page.close();
    },
    async 's7-503'() {
      // 사전: 셸에서 `docker compose stop superset`
      const page = await newPage();
      await loginAs('stub-viewer'); await open(page, dashUrl(D1));
      await page.waitForSelector('[data-testid=embed-failed]', { timeout: 30000 });
      await shot(page, 'fu1e-s7-dashboard-error-503-superset-down');
      await page.close();
    },
    // ---------------------------------------------------------------- S8
    async 's8'() {
      const page = await newPage();
      await loginAs('stub-admin'); await open(page, '/admin/dashboards');
      await page.waitForSelector('table[aria-label="대시보드 연결 목록"]');
      await shot(page, 'fu1e-s8-connections-list-admin');
      // 형식 오류
      await page.getByLabel('이름 (사용자에게 보이는 이름)').fill('영업 현황');
      await page.getByLabel('임베드 번호 (Superset에서 받은 번호)').fill('1234-not-a-uuid');
      await page.waitForSelector('[data-testid=uuid-format-error]');
      await shot(page, 'fu1e-s8-form-error-uuid-format');
      // 중복 409(이미 연결된 번호)
      await page.getByLabel('임베드 번호 (Superset에서 받은 번호)').fill(D1.uuid.toUpperCase());
      await page.waitForSelector('[data-testid=uuid-normalized]');
      await shot(page, 'fu1e-s8-form-uuid-uppercase-normalized-notice');
      await page.getByRole('button', { name: '연결 등록' }).click();
      await page.waitForSelector('form[aria-label="대시보드 연결 등록"] [role=alert]:not([data-testid])', { timeout: 8000 });
      await sleep(400);
      await shot(page, 'fu1e-s8-form-error-duplicate-409');
      // 이름 비움(공백만): 앞 오류가 남지 않도록 새로 연다
      await open(page, '/admin/dashboards');
      await page.waitForSelector('table[aria-label="대시보드 연결 목록"]');
      await page.getByLabel('이름 (사용자에게 보이는 이름)').fill('   ');
      await sleep(200);
      await shot(page, 'fu1e-s8-form-error-empty-name');
      await page.close();
    },
    async 's8-toggle'() {
      const page = await newPage();
      await loginAs('stub-admin'); await open(page, '/admin/dashboards');
      await page.waitForSelector('table[aria-label="대시보드 연결 목록"]');
      const row = page.locator('table[aria-label="대시보드 연결 목록"] tbody tr', { hasText: D2.title });
      await row.getByRole('button', { name: '이름 변경' }).click();
      await sleep(300);
      await shot(page, 'fu1e-s8-rename-inline');
      await page.getByRole('button', { name: '취소', exact: true }).click();
      await row.getByRole('button', { name: '연결 해제' }).click();
      await page.waitForSelector('table[aria-label="대시보드 연결 목록"] tbody tr.inactive');
      await sleep(400);
      await shot(page, 'fu1e-s8-connections-list-inactive-row');
      await row.getByRole('button', { name: '다시 연결' }).click();
      await page.waitForFunction(() => !document.querySelector('table[aria-label="대시보드 연결 목록"] tbody tr.inactive'));
      await sleep(400);
      await shot(page, 'fu1e-s8-connections-list-reactivated');
      await page.close();
    },
    async 's8-denied'() {
      const page = await newPage();
      await loginAs('stub-entry'); await open(page, '/admin/dashboards');
      await page.waitForSelector('[data-testid=screen-S8]');
      await shot(page, 'fu1e-s8-access-denied-non-admin');
      await page.close();
    },
    // ---------------------------------------------------------------- S9 / S2
    async 'sync-registered'() {
      const page = await newPage();
      await loginAs('stub-admin'); await open(page, '/admin/status');
      await page.waitForSelector('[data-testid=sync-summary]');
      await page.evaluate(() => document.querySelector('[data-testid=sync-section]')?.scrollIntoView({ block: 'start' }));
      await shot(page, 'fu1e-s9-sync-all-registered');
      await page.close();
      const p2 = await newPage();
      await loginAs('stub-definer'); await open(p2, '/datasets');
      await p2.waitForSelector('table');
      await shot(p2, 'fu1e-s2-dataset-list-sync-registered');
      await p2.close();
    },
    // 사전: 셸에서 Superset을 멈추고 데이터셋을 만들어 둔다(README). 실패는 `docker compose stop superset` 상태에서 만든 데이터셋이다.
    async 'sync-failed'() {
      const toSync = async (page) => {
        await page.waitForSelector('[data-testid=sync-summary]');
        await page.evaluate(() => document.querySelector('[data-testid=sync-section]')?.scrollIntoView({ block: 'start' }));
      };
      const page = await newPage();
      await loginAs('stub-admin'); await open(page, '/admin/status');
      await toSync(page);
      await shot(page, 'fu1e-s9-sync-failed-with-error-code-admin');
      notes.push('S9 요약(실패 단계): ' + (await page.locator('[data-testid=sync-summary]').innerText()).replace(/\s+/g, ' '));
      await page.locator('section[aria-label="Superset 동기"] select').selectOption('failed');
      await sleep(400);
      await shot(page, 'fu1e-s9-sync-filter-failed-admin');
      await page.close();
      for (const [user, tag] of [['stub-definer', 'definer'], ['stub-viewer', 'viewer']]) {
        const p2 = await newPage();
        await loginAs(user); await open(p2, '/datasets');
        await p2.waitForSelector('table');
        await shot(p2, `fu1e-s2-dataset-list-sync-failed-${tag}`);
        await p2.close();
      }
      // 비관리자: E1의 last_error는 null이고(API 값만 기록), S9(관리자 현황)는 들어갈 수 없다.
      const resp = (await api('stub-definer', '/superset/datasets'))[1];
      notes.push('definer가 받은 last_error 목록(모두 null이어야 함): ' + JSON.stringify((resp.items || resp).map((i) => i.last_error)));
      const p3 = await newPage();
      await loginAs('stub-definer'); await open(p3, '/admin/status');
      await shot(p3, 'fu1e-s9-access-denied-non-admin');
      await p3.close();
    },
    // 사전: 셸에서 Superset 컨테이너를 `docker compose pause superset`으로 멈춘 채(응답 없음) 데이터셋 여러 개를 만들어 둔다.
    // 요청은 읽기 시간 초과(15초)까지 처리 중이므로 대기 항목이 잠시 남는다. 이 단계는 만든 직후 바로 실행해야 한다.
    async 'sync-pending'() {
      const page = await newPage();
      await loginAs('stub-admin'); await open(page, '/admin/status');
      await page.waitForSelector('[data-testid=sync-summary]');
      await page.evaluate(() => document.querySelector('[data-testid=sync-section]')?.scrollIntoView({ block: 'start' }));
      notes.push('S9 요약(대기 단계): ' + (await page.locator('[data-testid=sync-summary]').innerText()).replace(/\s+/g, ' '));
      await shot(page, 'fu1e-s9-sync-pending-admin');
      await page.locator('section[aria-label="Superset 동기"] select').selectOption('pending');
      await sleep(300);
      await shot(page, 'fu1e-s9-sync-filter-pending-admin');
      await page.close();
      const p2 = await newPage();
      await loginAs('stub-definer'); await open(p2, '/datasets');
      await p2.waitForSelector('table');
      await shot(p2, 'fu1e-s2-dataset-list-sync-pending-definer');
      await p2.close();
    },
    async 'sync-retry'() {
      // 접수 메시지: "대기·실패 전부 다시 동기" 버튼을 누른다(Superset 상태에 따라 결과가 달라진다).
      const page = await newPage();
      await loginAs('stub-admin'); await open(page, '/admin/status');
      await page.waitForSelector('[data-testid=sync-summary]');
      await page.getByRole('button', { name: /대기·실패 전부 다시 동기/ }).click();
      await page.waitForSelector('[data-testid=sync-accepted]');
      await sleep(600);
      await page.evaluate(() => document.querySelector('[data-testid=sync-section]')?.scrollIntoView({ block: 'start' }));
      await shot(page, 'fu1e-s9-sync-retry-accepted', { wait: 100 });
      await page.close();
    },
    async 'sync-recovered'() {
      const page = await newPage();
      await loginAs('stub-admin'); await open(page, '/admin/status');
      await page.waitForSelector('[data-testid=sync-summary]');
      await page.evaluate(() => document.querySelector('[data-testid=sync-section]')?.scrollIntoView({ block: 'start' }));
      await shot(page, 'fu1e-s9-sync-recovered-all-registered');
      await page.close();
    },
    // ---------------------------------------------------------------- Superset 안(선택)
    async 'superset-calc'() {
      // Superset 화면에 관리자로 로그인해 계산 열 숫자가 보이는 대시보드를 연다. 비밀번호는 환경변수로만 받고 화면에 찍히지 않는다(로그인 후 촬영).
      const user = process.env.SUPERSET_ADMIN_USER, pass = process.env.SUPERSET_ADMIN_PASSWORD;
      if (!user || !pass) throw new Error('SUPERSET_ADMIN_USER/PASSWORD 환경변수가 필요하다');
      const page = await newPage();
      const root = `${ORIGIN}${BASE}/superset`;
      await page.goto(`${root}/login/`, { waitUntil: 'networkidle' });
      await page.fill('[data-test=username-input]', user);
      await page.fill('[data-test=password-input]', pass);
      await page.click('[data-test=login-button]');
      await page.waitForLoadState('networkidle');
      await page.goto(`${root}/superset/dashboard/${D2.superset_id}/?standalone=0`, { waitUntil: 'networkidle' });
      await page.waitForSelector('[data-test-chart-id]', { timeout: 60000 });
      for (let i = 0; i < 60; i++) {
        const ready = await page.evaluate(() => { const c = [...document.querySelectorAll('[data-test-chart-id]')]; return c.length >= 3 && c.every((e) => e.querySelectorAll('canvas,svg,table').length > 0); });
        if (ready) break;
        await sleep(500);
      }
      await sleep(1500);
      await shot(page, 'fu1e-superset-계산열숫자', { noSettle: true, wait: 300 });
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
  const patterns = [/Traceback/, /\/home\//, /\/app\//, /postgres(ql)?:\/\//i, /bi_stub_login/, /Authorization/i, /Bearer /, /SELECT .* FROM/i, /bi_data\./, /eyJ[A-Za-z0-9_-]{10,}/];
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
