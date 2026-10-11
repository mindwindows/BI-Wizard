const L = require('./pw4.js');
const dd = '.ant-select-dropdown:not(.ant-select-dropdown-hidden)';
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  await page.goto(`${L.ORIGIN}${L.ROOT}/superset/dashboard/${L.ids.dash}/`, {waitUntil:'networkidle'}); await page.waitForTimeout(4500);
  await step('table-cell-drill', async()=>{
    await page.locator('.dashboard-component-chart-holder').first().locator('td, [role="gridcell"]').nth(3).click({button:'right'}); await page.waitForTimeout(900);
    console.log('CELL CONTEXT MENU:', await L.txt(page, '.ant-dropdown:not(.ant-dropdown-hidden), [role="menu"]'));
    await page.screenshot({path:'shots/d1_cell_menu.png'});
    await page.getByText(/Drill to detail/).first().click(); await page.waitForTimeout(3000);
    console.log('DRILL MODAL:', (await L.txt(page, '.ant-modal')).slice(0,500));
    await page.screenshot({path:'shots/d1_drill.png'});
    await page.keyboard.press('Escape');
  });
  await step('bar-drill', async()=>{
    await page.waitForTimeout(500);
    const bars = page.locator('.dashboard-component-chart-holder').nth(1); const box = await bars.boundingBox();
    for (const fx of [0.92,0.85,0.75,0.55]) {
      await page.mouse.click(box.x+box.width*fx, box.y+box.height*0.75, {button:'right'}); await page.waitForTimeout(700);
      const t = await L.txt(page, '.ant-dropdown:not(.ant-dropdown-hidden)'); if (!t.startsWith('(n/a')) { console.log('BAR MENU', fx, t); break; }
    }
    await page.screenshot({path:'shots/d1_bar_menu.png'});
    await page.getByText(/Drill to detail/).first().click({timeout:3000}); await page.waitForTimeout(3000);
    console.log('BAR DRILL MODAL:', (await L.txt(page, '.ant-modal')).slice(0,500));
    await page.screenshot({path:'shots/d1_bar_drill.png'});
  });
  await browser.close();
})();
