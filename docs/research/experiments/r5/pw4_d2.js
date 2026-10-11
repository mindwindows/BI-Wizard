const L = require('./pw4.js');
async function step(name, fn) { try { await fn(); } catch(e) { console.log('STEP FAIL', name, String(e).slice(0,250)); } }
(async()=>{
  const {browser, page} = await L.start(); page.setDefaultTimeout(8000);
  await page.goto(`${L.ORIGIN}${L.ROOT}/superset/dashboard/${L.ids.dash}/`, {waitUntil:'networkidle'}); await page.waitForTimeout(4500);
  await step('drill-by', async()=>{
    const bars = page.locator('.dashboard-component-chart-holder').nth(1); const box = await bars.boundingBox();
    await page.mouse.click(box.x+box.width*0.92, box.y+box.height*0.75, {button:'right'}); await page.waitForTimeout(800);
    await page.getByText('Drill by', {exact:true}).first().hover(); await page.waitForTimeout(1200);
    console.log('DRILL BY SUBMENU:', await L.txt(page, '.ant-dropdown-menu-submenu-popup:not(.ant-dropdown-menu-submenu-hidden), .ant-dropdown:not(.ant-dropdown-hidden)'));
    await page.screenshot({path:'shots/d2_drill_by_menu.png'});
    console.log('ALL MENU ITEMS:', await page.locator('[role="menuitem"]').allInnerTexts());
    await page.getByText('Drill by', {exact:true}).first().click().catch(()=>{}); await page.waitForTimeout(1200);
    console.log('DRILL BY AFTER CLICK:', await page.locator('[role="menuitem"], .ant-popover:not(.ant-popover-hidden)').allInnerTexts());
    await page.screenshot({path:'shots/d2_drill_by_menu2.png'});
  });
  await browser.close();
})();
