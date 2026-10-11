const L = require('./pw4.js');
const dd = '.ant-select-dropdown:not(.ant-select-dropdown-hidden)';
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  await page.goto(`${L.ORIGIN}${L.ROOT}/superset/dashboard/${L.ids.dash}/`, {waitUntil:'networkidle'}); await page.waitForTimeout(4000);
  await step('prefilter', async()=>{
    await page.locator('[data-test="filterbar-orientation-icon"]').first().click(); await page.waitForTimeout(600);
    await page.getByText(/Add or edit filters/i).first().click(); await page.waitForTimeout(2500);
    await page.locator('.ant-modal label', {hasText:'Pre-filter available values'}).first().click(); await page.waitForTimeout(800);
    await page.locator('.ant-modal').getByText(/Add pre-filter/i).first().click(); await page.waitForTimeout(1500);
    await page.screenshot({path:'shots/c5_prefilter.png'});
    console.log('PREFILTER TEXT:', (await L.txt(page, '.ant-modal')).slice(150, 700));
    const n = await page.locator('.ant-modal .ant-select').count();
    await page.locator('.ant-modal .ant-select').last().click().catch(()=>{}); await page.waitForTimeout(700);
    console.log('PREFILTER COLUMN OPTIONS:', (await page.locator(`${dd} .ant-select-item-option`).allInnerTexts()).join(' | '));
    await page.screenshot({path:'shots/c5_prefilter_open.png'});
    await page.keyboard.press('Escape');
    // sort filter values
    await page.locator('.ant-modal label', {hasText:'Sort filter values'}).first().click(); await page.waitForTimeout(800);
    await page.screenshot({path:'shots/c5_sortfilter.png'});
    console.log('SORT TEXT:', (await L.txt(page, '.ant-modal')).slice(150, 700));
    await page.locator('.ant-modal button', {hasText:'Cancel'}).first().click(); await page.waitForTimeout(800);
    await page.locator('.ant-modal button', {hasText:/Yes|Discard|Cancel/}).first().click().catch(()=>{}); await page.waitForTimeout(600);
  });
  await step('view as table', async()=>{
    await page.reload({waitUntil:'networkidle'}); await page.waitForTimeout(4000);
    const chart = page.locator('.dashboard-component-chart-holder').first(); await chart.hover(); await page.waitForTimeout(400);
    await chart.locator('[data-test="more-vert-trigger"], [aria-label="more-vert"], .ant-dropdown-trigger').first().click(); await page.waitForTimeout(700);
    await page.getByText('View as table', {exact:true}).first().click(); await page.waitForTimeout(2500);
    console.log('VIEW AS TABLE:', (await L.txt(page, '.ant-modal')).slice(0,300));
    await page.screenshot({path:'shots/c5_view_as_table.png'});
    await page.keyboard.press('Escape'); await page.waitForTimeout(500);
  });
  await step('drill', async()=>{
    // drill to detail on bar chart: right click on bar
    const bars = page.locator('.dashboard-component-chart-holder').nth(1);
    const box = await bars.boundingBox(); console.log('bar chart box', JSON.stringify(box));
    await page.mouse.click(box.x+box.width*0.6, box.y+box.height*0.7, {button:'right'}); await page.waitForTimeout(1000);
    console.log('CONTEXT MENU:', await L.txt(page, '.ant-dropdown:not(.ant-dropdown-hidden), [role="menu"]'));
    await page.screenshot({path:'shots/c5_drill_menu.png'});
    await page.getByText(/Drill to detail/).first().click(); await page.waitForTimeout(3000);
    console.log('DRILL MODAL:', (await L.txt(page, '.ant-modal')).slice(0,500));
    await page.screenshot({path:'shots/c5_drill.png'});
    await page.keyboard.press('Escape');
  });
  await browser.close();
})();
