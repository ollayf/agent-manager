import asyncio
import json
from pathlib import Path
from urllib.parse import urlsplit, unquote
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parent/'handbook'
OUT=Path('/tmp/archive-general-handbook-20261025')
OUT.mkdir(exist_ok=True)
CHECK_COUNT=len(json.loads((ROOT/'checks-reference.json').read_text())['checks'])
PAGES=['index.html','workflow.html','storage.html','security.html','checks.html','recovery.html','evidence.html']

async def main():
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',headless=True)
  page=await browser.new_page(viewport={'width':1440,'height':1050},device_scale_factor=1)
  await page.emulate_media(reduced_motion='reduce')
  errors=[];requests=[];results=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.on('request',lambda r:requests.append(r.url))
  for name in PAGES:
   await page.goto((ROOT/name).as_uri())
   await page.wait_for_load_state('load')
   assert await page.locator('h1').count()==1
   assert await page.locator('nav[aria-label="Chapters"] a').count()==7
   assert await page.locator('nav[aria-label="Chapters"] a[aria-current="page"]').count()==1
   assert not await page.evaluate('document.documentElement.scrollWidth > window.innerWidth'),name+' overflows desktop'
   for href in await page.locator('a[href]').evaluate_all('(els)=>els.map(el=>el.getAttribute("href"))'):
    if href.startswith('#'):
     assert await page.locator(href).count(),(name,href)
    elif not urlsplit(href).scheme:
     target=ROOT/unquote(urlsplit(href).path)
     assert target.is_file(),(name,href)
   await page.screenshot(path=str(OUT/(Path(name).stem+'-desktop.png')),full_page=True)
   results.append({'page':name,'desktop':'pass'})
  await page.goto((ROOT/'workflow.html').as_uri())
  assert await page.locator('[data-sim-count]').inner_text()=='STEP 1 / 5'
  for _ in range(4):await page.get_by_role('button',name='Next step →',exact=True).click()
  assert 'No upload or eviction' in await page.locator('[data-sim-note]').inner_text()
  assert await page.locator('[data-next]').is_disabled()
  await page.get_by_label('Storage target',exact=True).select_option('google-drive')
  for _ in range(4):await page.get_by_role('button',name='Next step →',exact=True).click()
  assert 'Remote upload is unknown' in await page.locator('[data-sim-note]').inner_text()
  assert await page.locator('[data-state="cloud"] b').inner_text()=='Unknown'
  await page.get_by_label('Storage target',exact=True).select_option('google-drive-api')
  await page.get_by_role('button',name='Show archive step 3',exact=True).click()
  assert await page.locator('[data-state="repo"] b').inner_text()=='Present'
  assert await page.locator('[data-state="cloud"] b').inner_text()=='Verified'
  await page.get_by_role('button',name='Show archive step 5',exact=True).click()
  assert await page.locator('[data-state="repo"] b').inner_text()=='Removed'
  assert 'No desktop archive cache' in await page.locator('[data-sim-note]').inner_text()
  await page.get_by_label('Storage target',exact=True).select_option('icloud')
  assert await page.locator('[data-sim-count]').inner_text()=='STEP 1 / 7'
  for _ in range(6):await page.get_by_role('button',name='Next step →',exact=True).click()
  assert await page.locator('[data-sim-title]').inner_text()=='Evict the local cached bytes'
  assert await page.locator('[data-state="repo"] b').inner_text()=='Removed'
  assert await page.locator('[data-state="cache"] b').inner_text()=='Placeholder only'
  assert await page.locator('[data-state="record"] b').inner_text()=='Recorded'
  assert await page.locator('[data-next]').is_disabled()
  await page.get_by_role('button',name='Show archive step 5',exact=True).click()
  assert 'only on this Mac' in await page.locator('[data-sim-note]').inner_text()
  await page.get_by_role('tab',name='Read',exact=True).click()
  assert await page.locator('#read').is_visible() and not await page.locator('#archive').is_visible()
  await page.get_by_role('tab',name='Read',exact=True).press('ArrowRight')
  assert await page.get_by_role('tab',name='Restore',exact=True).get_attribute('aria-selected')=='true'
  assert await page.locator('#restore').is_visible()
  await page.goto((ROOT/'workflow.html').as_uri()+'#restore')
  assert await page.locator('#restore').is_visible()
  await page.goto((ROOT/'checks.html').as_uri())
  assert await page.locator('[data-check]:visible').count()==CHECK_COUNT
  assert await page.locator('.pill.skip').first.evaluate('(el)=>getComputedStyle(el).position') != 'fixed'
  await page.get_by_label('Search the checks',exact=True).fill('symlink')
  matches=await page.locator('[data-check]:visible').count();assert 0<matches<CHECK_COUNT
  await page.get_by_label('Operation',exact=True).select_option('folders')
  for phases in await page.locator('[data-check]:visible').evaluate_all('(els)=>els.map(el=>el.dataset.phase)'):assert 'folders' in phases.split()
  await page.get_by_label('Response',exact=True).select_option('keep')
  for response in await page.locator('[data-check]:visible').evaluate_all('(els)=>els.map(el=>el.dataset.response)'):assert response=='keep'
  await page.get_by_label('Search the checks',exact=True).fill('zzzz-no-such-check')
  assert await page.locator('#check-empty').is_visible()
  assert await page.locator('#check-count').inner_text()==f'0 of {CHECK_COUNT} checks'
  await page.get_by_role('button',name='Reset filters',exact=True).click()
  assert await page.locator('[data-check]:visible').count()==CHECK_COUNT
  await page.locator('#check-19 summary').click()
  assert await page.locator('#check-19').get_attribute('open') is not None
  await page.goto((ROOT/'checks.html').as_uri()+'?phase=scope')
  assert await page.locator('#check-phase').input_value()=='scope'
  assert await page.locator('[data-check]:visible').count()<CHECK_COUNT
  for width in (390,768):
   await page.set_viewport_size({'width':width,'height':844})
   for name in PAGES:
    await page.goto((ROOT/name).as_uri())
    assert not await page.evaluate('document.documentElement.scrollWidth > window.innerWidth'),(name,width,'overflows')
    if width==390 and name in ['index.html','checks.html','workflow.html','security.html']:
     await page.screenshot(path=str(OUT/(Path(name).stem+'-mobile.png')),full_page=True)
   if width==390:
    await page.get_by_role('button',name='Contents',exact=True).click()
    assert await page.locator('#chapter-nav').is_visible()
    await page.locator('#chapter-nav a[href="security.html"]').click()
    assert 'security.html' in page.url
    await page.get_by_role('button',name='Contents',exact=True).click()
    await page.get_by_role('button',name='Close',exact=True).click()
    assert not await page.locator('#chapter-nav').is_visible()
  nojs=await browser.new_page(java_script_enabled=False,viewport={'width':1280,'height':900})
  await nojs.goto((ROOT/'checks.html').as_uri())
  assert await nojs.locator('[data-check]:visible').count()==CHECK_COUNT
  await nojs.goto((ROOT/'workflow.html').as_uri())
  for ident in ('archive','read','restore'):assert await nojs.locator('#'+ident).is_visible()
  assert not errors,errors
  external=[url for url in requests if not url.startswith(('file:','data:'))]
  assert not external,external
  (OUT/'browser-results.json').write_text(json.dumps({'pages':results,'checks':CHECK_COUNT,'interaction_tests':'passed','mobile_widths':[390,768],'javascript_errors':errors,'external_requests':external,'no_javascript':'passed'},indent=2))
  await browser.close()
  print(f'PASS: 7 pages, links, {CHECK_COUNT} checks, filters, four provider walkthroughs, operation tabs, keyboard navigation, mobile menu, desktop/mobile overflow, no-JS content, and no external requests.')

asyncio.run(main())
