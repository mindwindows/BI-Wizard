const L = require('./pw4.js');
const pop = '.ant-popover:not(.ant-popover-hidden)';
const dd = '.ant-select-dropdown:not(.ant-select-dropdown-hidden)';
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  await page.goto(`${L.ORIGIN}${L.ROOT}/explore/?slice_id=${L.ids.chart_table}`, {waitUntil:'networkidle'}); await page.waitForTimeout(3000);
  await step('menu', async()=>{
    await page.locator('[data-test="actions-trigger"]').click(); await page.waitForTimeout(800);
    console.log('TOP MENU:', await L.txt(page, '.ant-dropdown:not(.ant-dropdown-hidden)'));
    await page.screenshot({path:'shots/a5_top_menu.png'});
    await page.getByText('View query', {exact:true}).first().click(); await page.waitForTimeout(2500);
    console.log('VIEW QUERY:', (await L.txt(page, '.ant-modal')).slice(0,900));
    await page.screenshot({path:'shots/a5_view_query.png'});
    await page.keyboard.press('Escape'); await page.waitForTimeout(500);
    await page.locator('[data-test="actions-trigger"]').click(); await page.waitForTimeout(800);
    await page.getByText(/View query results|Run in SQL Lab|Download/).first().hover().catch(()=>{});
  });
  await step('aggregate', async()=>{
    await page.keyboard.press('Escape');
    await page.getByText('Aggregate', {exact:true}).first().click(); await page.waitForTimeout(1500);
    // add dimension: Dimensions control
    await page.locator('text=Dimensions >> xpath=../.. >> text=Drop columns here or click').first().click().catch(async()=>{ await page.getByText('Drop columns here or click').first().click(); });
    await page.waitForTimeout(1200);
    console.log('DIM POPOVER:', await L.txt(page, pop));
    await page.locator(`${pop} .ant-select`).first().click(); await page.waitForTimeout(500);
    console.log('DIM OPTIONS:', (await page.locator(`${dd} .ant-select-item-option`).allInnerTexts()).join(' | '));
    await page.locator(`${dd} .ant-select-item-option`, {hasText:'팀'}).first().click(); await page.waitForTimeout(500);
    await page.locator(`${pop} button`, {hasText:'Save'}).first().click(); await page.waitForTimeout(800);
    // add metric
    await page.locator('[data-test="metrics"] >> text=Drop columns/metrics here or click').first().click(); await page.waitForTimeout(1200);
    await page.screenshot({path:'shots/a5_metric_popover.png'});
    console.log('METRIC POPOVER:', await L.txt(page, pop));
    await page.locator(`${pop} [role="tab"]`, {hasText:'Simple'}).first().click(); await page.waitForTimeout(500);
    const sels = page.locator(`${pop} .ant-select`); console.log('selects in metric popover', await sels.count());
    await sels.first().click(); await page.waitForTimeout(500);
    console.log('METRIC COLUMN OPTIONS:', (await page.locator(`${dd} .ant-select-item-option`).allInnerTexts()).join(' | '));
    await page.locator(`${dd} .ant-select-item-option`, {hasText:'매출'}).first().click(); await page.waitForTimeout(500);
    await sels.nth(1).click(); await page.waitForTimeout(500);
    await page.locator(`${dd} .ant-select-item-option`, {hasText:/^SUM$/}).first().click(); await page.waitForTimeout(800);
    await page.screenshot({path:'shots/a5_metric_popover2.png'});
    console.log('METRIC POPOVER 2:', await L.txt(page, pop));
    await page.locator(`${pop} button`, {hasText:'Save'}).first().click(); await page.waitForTimeout(1000);
    console.log('METRICS CONTROL:', await L.txt(page, '[data-test="metrics"]'));
    await page.screenshot({path:'shots/a5_metric_chip.png'});
    // metric chip tooltip
    await page.locator('[data-test="metrics"] >> text=SUM').first().hover().catch(()=>{}); await page.waitForTimeout(1200);
    console.log('METRIC CHIP TOOLTIP:', await L.txt(page, '.ant-tooltip:not(.ant-tooltip-hidden)'));
    // sort query by
    await page.getByText('Update chart').first().click(); await page.waitForTimeout(3000);
    await page.screenshot({path:'shots/a5_aggregate_result.png'});
    console.log('AGG TABLE HEADERS:', await page.locator('table thead th, [role="columnheader"]').allInnerTexts().catch(()=>[]));
    await page.locator('[data-test="timeseries_limit_metric"], [data-test="order_by_cols"]').first().click().catch(()=>{}); 
    await page.getByText('Drop a column/metric here or click').first().click().catch(()=>{}); await page.waitForTimeout(800);
    console.log('SORT POPOVER:', (await L.txt(page, pop)).slice(0,300));
    await page.screenshot({path:'shots/a5_sort_popover.png'});
  });
  await browser.close();
})();
