const L = require('./pw4.js');
const dd = '.ant-select-dropdown:not(.ant-select-dropdown-hidden)';
const pop = '.ant-popover:not(.ant-popover-hidden)';
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  await page.goto(`${L.ORIGIN}${L.ROOT}/superset/dashboard/${L.ids.dash}/`, {waitUntil:'networkidle'}); await page.waitForTimeout(4000);
  await page.locator('[data-test="filterbar-orientation-icon"]').first().click(); await page.waitForTimeout(600);
  await page.getByText(/Add or edit filters/i).first().click(); await page.waitForTimeout(2500);
  await page.locator('.ant-modal label', {hasText:'Pre-filter available values'}).first().click(); await page.waitForTimeout(1000);
  await step('prefilter add', async()=>{
    await page.locator('.ant-modal').getByText('Add filter', {exact:true}).first().click(); await page.waitForTimeout(1200);
    await page.screenshot({path:'shots/c7_prefilter_add.png'});
    console.log('POPOVER:', await L.txt(page, pop));
    await page.locator(`${pop} .ant-select`).first().click().catch(()=>{}); await page.waitForTimeout(700);
    console.log('PREFILTER COLUMN OPTIONS:', (await page.locator(`${dd} .ant-select-item-option`).allInnerTexts()).join(' | '));
    await page.screenshot({path:'shots/c7_prefilter_options.png'});
    await page.keyboard.press('Escape');
  });
  await step('sort metric', async()=>{
    await page.locator('.ant-modal label', {hasText:'Sort filter values'}).first().click(); await page.waitForTimeout(800);
    const s = page.locator('.ant-modal .ant-select'); const n = await s.count();
    // 'Sort Metric' select is near; click the one with placeholder
    await page.locator('.ant-modal').getByText('Select ...').first().click().catch(()=>{}); await page.waitForTimeout(700);
    console.log('SORT METRIC OPTIONS:', (await page.locator(`${dd} .ant-select-item-option`).allInnerTexts()).join(' | '));
    await page.screenshot({path:'shots/c7_sortmetric.png'});
  });
  await browser.close();
})();
