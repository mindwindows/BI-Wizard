const L = require('./pw4.js');
const dd = '.ant-select-dropdown:not(.ant-select-dropdown-hidden)';
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  await page.goto(`${L.ORIGIN}${L.ROOT}/superset/dashboard/${L.ids.dash}/`, {waitUntil:'networkidle'}); await page.waitForTimeout(4000);
  await page.locator('[data-test="filterbar-orientation-icon"]').first().click(); await page.waitForTimeout(600);
  await page.getByText(/Add or edit filters/i).first().click(); await page.waitForTimeout(2500);
  await step('prefilter', async()=>{
    await page.locator('.ant-modal label', {hasText:'Pre-filter available values'}).first().click(); await page.waitForTimeout(1200);
    await page.screenshot({path:'shots/c6_prefilter.png'});
    console.log('AFTER CHECK:', (await L.txt(page, '.ant-modal')).slice(100, 700));
  });
  await step('sort', async()=>{
    await page.locator('.ant-modal label', {hasText:'Sort filter values'}).first().click(); await page.waitForTimeout(1200);
    await page.screenshot({path:'shots/c6_sort.png'});
    console.log('AFTER SORT CHECK:', (await L.txt(page, '.ant-modal')).slice(100, 800));
  });
  await browser.close();
})();
