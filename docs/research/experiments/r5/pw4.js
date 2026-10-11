const { chromium } = require('/opt/node22/lib/node_modules/playwright');
const fs = require('fs');
const env = {}; for (const l of fs.readFileSync('/home/user/BI-Wizard/_workspace/qa/g3x.env','utf8').split('\n')) { const m=l.match(/^([A-Z_]+)=(.*)$/); if (m) env[m[1]]=m[2]; }
const ORIGIN='http://127.0.0.1:25173', ROOT='/bi-wizard/superset';
const ids = JSON.parse(fs.readFileSync('ids.json','utf8'));
async function start(user='a27_author1') {
  const browser = await chromium.launch({ executablePath:'/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args:['--no-sandbox'] });
  const ctx = await browser.newContext({ viewport:{width:1600,height:1000} });
  const page = await ctx.newPage();
  await page.goto(`${ORIGIN}${ROOT}/login/`, {waitUntil:'networkidle'});
  await page.fill('#username', user); await page.fill('#password', env.SUPERSET_ADMIN_PASSWORD);
  await Promise.all([page.waitForNavigation({waitUntil:'networkidle', timeout:30000}).catch(()=>{}), page.click('button[data-test="login-button"]')]);
  return {browser, ctx, page};
}
const txt = (page, sel) => page.locator(sel).first().innerText({timeout:3000}).then(t=>t.replace(/\s+/g,' ')).catch(e=>'(n/a '+sel+')');
module.exports = {chromium, fs, env, ORIGIN, ROOT, ids, start, txt};
