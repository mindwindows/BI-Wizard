const L = require('./pw4.js');
const pop = '.ant-popover:not(.ant-popover-hidden)';
const dd = '.ant-select-dropdown:not(.ant-select-dropdown-hidden)';
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  await page.goto(`${L.ORIGIN}${L.ROOT}/explore/?slice_id=${L.ids.chart_table}`, {waitUntil:'networkidle'}); await page.waitForTimeout(3000);
  await step('results', async()=>{
    await page.getByText('Results', {exact:true}).first().click(); await page.waitForTimeout(3000);
    const body = await page.evaluate(()=>document.body.innerText.replace(/\s+/g,' ')); const i = body.lastIndexOf('Results'); console.log('RESULTS PANE:', body.slice(i, i+300));
    await page.screenshot({path:'shots/a4_results_pane.png'});
  });
  await step('viewquery', async()=>{
    await page.locator('button:has([aria-label="ellipsis"])').last().click(); await page.waitForTimeout(800);
    console.log('TOP MENU:', await L.txt(page, '.ant-dropdown:not(.ant-dropdown-hidden)'));
    await page.screenshot({path:'shots/a4_top_menu.png'});
    await page.getByText('View query', {exact:true}).first().click(); await page.waitForTimeout(2500);
    console.log('VIEW QUERY:', (await L.txt(page, '.ant-modal')).slice(0,900));
    await page.screenshot({path:'shots/a4_view_query.png'});
    await page.keyboard.press('Escape'); await page.waitForTimeout(500);
  });
  await step('viewresults', async()=>{
    await page.locator('button:has([aria-label="ellipsis"])').last().click(); await page.waitForTimeout(800);
    await page.getByText('View query results', {exact:false}).first().click(); await page.waitForTimeout(2500);
    console.log('VIEW QUERY RESULTS:', (await L.txt(page, '.ant-modal')).slice(0,400));
    await page.screenshot({path:'shots/a4_view_results.png'});
    await page.keyboard.press('Escape'); await page.waitForTimeout(500);
  });
  await step('filter-gt', async()=>{
    await page.getByText('Drop columns/metrics here or click').first().click(); await page.waitForTimeout(1500);
    await page.locator(`${pop} .ant-select`).first().click(); await page.waitForTimeout(400);
    await page.locator(`${dd} .ant-select-item-option`, {hasText:'매출'}).first().click(); await page.waitForTimeout(500);
    await page.locator(`${pop} .ant-select`).nth(1).click(); await page.waitForTimeout(400);
    await page.locator(`${dd} .ant-select-item-option[title="Greater than (>)"], ${dd} .ant-select-item-option:has-text("Greater than (>)")`).first().click(); await page.waitForTimeout(500);
    await page.screenshot({path:'shots/a4_filter_gt1.png'});
    const inp = page.locator(`${pop} input`); console.log('inputs in popover', await inp.count(), await inp.evaluateAll(els=>els.map(e=>e.type+':'+(e.getAttribute('aria-label')||e.className.slice(0,40)))));
    await page.locator(`${pop} input:not([type="search"])`).last().fill('120'); await page.waitForTimeout(300);
    await page.locator(`${pop} button`, {hasText:'Save'}).first().click(); await page.waitForTimeout(1200);
    console.log('FILTERS CONTROL:', await L.txt(page, '[data-test="adhoc_filters"]'));
    await page.getByText('Update chart').first().click(); await page.waitForTimeout(3000);
    await page.screenshot({path:'shots/a4_filter_gt2.png'});
    // hover chip for tooltip
    await page.locator('[data-test="adhoc_filters"] >> text=c_1').first().hover(); await page.waitForTimeout(1200);
    console.log('CHIP TOOLTIP:', await L.txt(page, '[role="tooltip"]:visible, .ant-tooltip:not(.ant-tooltip-hidden)'));
    await page.screenshot({path:'shots/a4_filter_gt_hover.png'});
  });
  await step('aggregate', async()=>{
    await page.mouse.move(900, 60);
    await page.getByText('Aggregate', {exact:true}).first().click(); await page.waitForTimeout(1500);
    await page.screenshot({path:'shots/a4_aggregate.png'});
    console.log('AGG BODY:', (await page.evaluate(()=>document.body.innerText.replace(/\s+/g,' '))).slice(280, 900));
    // add a metric
    await page.getByText('Drop columns/metrics here or click').first().click().catch(()=>{});
  });
  await browser.close();
})();
