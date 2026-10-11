const L = require('./pw4.js');
const pop = '.ant-popover:not(.ant-popover-hidden)';
const dd = '.ant-select-dropdown:not(.ant-select-dropdown-hidden)';
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  await page.goto(`${L.ORIGIN}${L.ROOT}/explore/?slice_id=${L.ids.chart_table}`, {waitUntil:'networkidle'}); await page.waitForTimeout(3000);
  await step('aggregate', async()=>{
    await page.getByText('Aggregate', {exact:true}).first().click(); await page.waitForTimeout(1500);
    await page.getByText('Drop columns here or click').first().click(); await page.waitForTimeout(1200);
    await page.locator(`${pop} .ant-select`).first().click(); await page.waitForTimeout(500);
    await page.locator(`${dd} .ant-select-item-option`, {hasText:'팀'}).first().click(); await page.waitForTimeout(500);
    await page.locator(`${pop} button`, {hasText:'Save'}).first().click(); await page.waitForTimeout(800);
    await page.locator('[data-test="metrics"] >> text=Drop columns/metrics here or click').first().click(); await page.waitForTimeout(1200);
    await page.locator(`${pop} [role="tab"]`, {hasText:'Simple'}).first().click(); await page.waitForTimeout(700);
    const pane = `${pop} .ant-tabs-tabpane-active`;
    console.log('selects in active pane', await page.locator(`${pane} .ant-select`).count());
    await page.locator(`${pane} .ant-select`).first().click(); await page.waitForTimeout(500);
    console.log('METRIC COLUMN OPTIONS:', (await page.locator(`${dd} .ant-select-item-option`).allInnerTexts()).join(' | '));
    await page.locator(`${dd} .ant-select-item-option`, {hasText:'매출'}).first().click(); await page.waitForTimeout(500);
    await page.locator(`${pane} .ant-select`).nth(1).click(); await page.waitForTimeout(500);
    await page.locator(`${dd} .ant-select-item-option`, {hasText:/^SUM$/}).first().click(); await page.waitForTimeout(800);
    await page.screenshot({path:'shots/a6_metric_popover2.png'});
    console.log('METRIC POPOVER 2:', await L.txt(page, pop));
    await page.locator(`${pop} button`, {hasText:'Save'}).first().click(); await page.waitForTimeout(1000);
    console.log('METRICS CONTROL:', await L.txt(page, '[data-test="metrics"]'));
    await page.getByText('Update chart').first().click(); await page.waitForTimeout(3500);
    await page.screenshot({path:'shots/a6_aggregate_result.png'});
    console.log('HEADERS:', (await page.locator('[role="columnheader"], th').allInnerTexts()).join(' | '));
    // sort query by
    await page.getByText('Drop a column/metric here or click').first().click().catch(()=>{}); await page.waitForTimeout(800);
    console.log('SORT POPOVER:', (await L.txt(page, pop)).slice(0,300));
    await page.screenshot({path:'shots/a6_sort_popover.png'});
    await page.keyboard.press('Escape');
  });
  await browser.close();
})();
