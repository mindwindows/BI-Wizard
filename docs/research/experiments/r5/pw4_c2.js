const L = require('./pw4.js');
const dd = '.ant-select-dropdown:not(.ant-select-dropdown-hidden)';
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  await page.goto(`${L.ORIGIN}${L.ROOT}/superset/dashboard/${L.ids.dash}/`, {waitUntil:'networkidle'}); await page.waitForTimeout(4000);
  await step('open-config', async()=>{
    const hdr = page.locator('[data-test="filter-bar"]');
    console.log('gear candidates', await page.evaluate(()=>[...document.querySelectorAll('[data-test="filter-bar"] button, [data-test="filter-bar"] [role="button"], [data-test="filter-bar"] [data-test]')].slice(0,15).map(b=>(b.getAttribute('data-test')||'')+'|'+(b.getAttribute('aria-label')||'')+'|'+b.tagName)));
    await page.locator('[data-test="filterbar-orientation-icon"], [data-test="filter-bar"] [aria-label="setting"]').first().click(); await page.waitForTimeout(800);
    console.log('GEAR MENU:', await L.txt(page, '.ant-dropdown:not(.ant-dropdown-hidden)'));
    await page.screenshot({path:'shots/c2_gear_menu.png'});
    await page.getByText(/Add or edit filters/i).first().click(); await page.waitForTimeout(2500);
    await page.screenshot({path:'shots/c2_filter_modal.png'});
    console.log('MODAL:', (await L.txt(page, '.ant-modal')).slice(0,900));
  });
  await step('column-select', async()=>{
    // existing filter '팀' is selected; find column select
    const sels = page.locator('.ant-modal .ant-select'); console.log('selects in modal', await sels.count());
    console.log('SELECT labels', await page.evaluate(()=>[...document.querySelectorAll('.ant-modal .ant-select')].map(s=>(s.getAttribute('data-test')||s.getAttribute('aria-label')||'')+'='+s.innerText.replace(/\s+/g,' ')).slice(0,12)));
  });
  await browser.close();
})();
