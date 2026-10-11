const L = require('./pw4.js');
(async()=>{
  const {browser, page} = await L.start();
  await page.goto(`${L.ORIGIN}${L.ROOT}/explore/?slice_id=${L.ids.chart_table}`, {waitUntil:'networkidle'}); await page.waitForTimeout(3000);
  // 1) hover on left panel column "매출"
  const col = page.locator('text=매출').first();
  const left = page.locator('div').filter({hasText:/^매출$/}).first();
  await page.locator('[data-test="datasource-panel"] >> text=매출').first().hover().catch(async()=>{ await page.getByText('매출', {exact:true}).nth(0).hover(); });
  await page.waitForTimeout(1200);
  console.log('TOOLTIP1:', await L.txt(page, '.ant-tooltip:not(.ant-tooltip-hidden), [role="tooltip"]'));
  await page.screenshot({path:'shots/a2_hover_left_col.png'});
  await page.mouse.move(800, 100); await page.waitForTimeout(500);
  // 2) click "Drop columns here or click" (Columns control)
  await page.getByText('Drop columns here or click').first().click(); await page.waitForTimeout(1500);
  await page.screenshot({path:'shots/a2_columns_popover.png'});
  console.log('POPOVER:', await L.txt(page, '.ant-popover:not(.ant-popover-hidden)'));
  // open the column select inside the popover
  const sel = page.locator('.ant-popover:not(.ant-popover-hidden) .ant-select').first();
  await sel.click(); await page.waitForTimeout(1000);
  await page.screenshot({path:'shots/a2_columns_select_open.png'});
  console.log('SELECT OPTIONS:', await page.locator('.ant-select-dropdown:not(.ant-select-dropdown-hidden) .ant-select-item-option').allInnerTexts());
  await browser.close();
})();
