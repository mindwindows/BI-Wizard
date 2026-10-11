const L = require('./pw4.js');
const pop = '.ant-popover:not(.ant-popover-hidden)';
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,200)); } }
(async()=>{
  const {browser, page} = await L.start();
  await page.goto(`${L.ORIGIN}${L.ROOT}/explore/?slice_id=${L.ids.chart_table}`, {waitUntil:'networkidle'}); await page.waitForTimeout(3000);
  // ---- Filters: add filter on 매출
  await step('filter', async()=>{
    await page.getByText('Drop columns/metrics here or click').first().click(); await page.waitForTimeout(1500);
    await page.locator(`${pop} .ant-select`).first().click(); await page.waitForTimeout(500);
    await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option', {hasText:'매출'}).first().click(); await page.waitForTimeout(800);
    await page.screenshot({path:'shots/a3_filter_popover1.png'});
    console.log('FILTER POPOVER:', await L.txt(page, pop));
    // operator select is 2nd select, value input
    const sels = page.locator(`${pop} .ant-select`); console.log('n selects', await sels.count());
    await sels.nth(1).click(); await page.waitForTimeout(500);
    console.log('OPERATORS:', (await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option').allInnerTexts()).join(' | '));
    await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option', {hasText:/^>$/}).first().click().catch(async()=>{ await page.keyboard.press('Escape'); });
    await page.waitForTimeout(500);
    await page.locator(`${pop} input[type="text"], ${pop} .ant-input-number-input, ${pop} input.ant-input`).last().fill('120').catch(e=>console.log('fill fail'));
    await page.screenshot({path:'shots/a3_filter_popover2.png'});
    await page.locator(`${pop} button`, {hasText:'Save'}).first().click(); await page.waitForTimeout(1200);
    console.log('FILTERS CONTROL:', await L.txt(page, '[data-test="adhoc_filters"]'));
    await page.screenshot({path:'shots/a3_filter_chip.png'});
    // hover chip
    await page.locator('[data-test="adhoc_filters"] .ant-tag, [data-test="adhoc_filters"] [data-test="option-label"]').nth(1).hover().catch(()=>{}); await page.waitForTimeout(1000);
    console.log('FILTER CHIP TOOLTIP:', await L.txt(page, '.ant-tooltip:not(.ant-tooltip-hidden)'));
    await page.screenshot({path:'shots/a3_filter_chip_hover.png'});
  });
  // ---- Ordering select
  await step('ordering', async()=>{
    await page.mouse.move(900, 60);
    await page.locator('text=Ordering').first().scrollIntoViewIfNeeded();
    const ord = page.locator('[data-test="timeseries_limit_metric"], [data-test="order_by_cols"]').first();
    await ord.click(); await page.waitForTimeout(800);
    console.log('ORDERING OPTIONS:', (await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option').allInnerTexts()).join(' | '));
    await page.screenshot({path:'shots/a3_ordering.png'});
    await page.keyboard.press('Escape');
  });
  // ---- Update chart & results pane
  await step('update', async()=>{
    await page.getByText('Update chart').first().click(); await page.waitForTimeout(3500);
    await page.getByText('Results', {exact:true}).first().click(); await page.waitForTimeout(2500);
    await page.screenshot({path:'shots/a3_results_pane.png'});
    const body = await page.evaluate(()=>document.body.innerText.replace(/\s+/g,' '));
    const i = body.lastIndexOf('Results'); console.log('RESULTS PANE (tail):', body.slice(i, i+400));
    await page.getByText('Samples', {exact:true}).first().click(); await page.waitForTimeout(2500);
    const body2 = await page.evaluate(()=>document.body.innerText.replace(/\s+/g,' '));
    const j = body2.lastIndexOf('Samples'); console.log('SAMPLES PANE (tail):', body2.slice(j, j+400));
    await page.screenshot({path:'shots/a3_samples_pane.png'});
  });
  // ---- View query
  await step('viewquery', async()=>{
    await page.locator('[data-test="query-save-button"]').count();
    await page.getByRole('button', {name:/ellipsis|more|\.\.\./i}).first().click().catch(async()=>{ await page.locator('button:has(.anticon-ellipsis), [data-test="actions-trigger"], button:has([aria-label="ellipsis"])').first().click(); });
    await page.waitForTimeout(800);
    console.log('MENU:', await L.txt(page, '.ant-dropdown:not(.ant-dropdown-hidden)'));
    await page.screenshot({path:'shots/a3_menu.png'});
    await page.getByText('View query', {exact:true}).first().click(); await page.waitForTimeout(2000);
    console.log('VIEW QUERY MODAL:', (await L.txt(page, '.ant-modal')).slice(0,700));
    await page.screenshot({path:'shots/a3_view_query.png'});
  });
  await browser.close();
})();
