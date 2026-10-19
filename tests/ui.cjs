// DOM interaction checks only. jsdom does not validate rendering or real mobile layout.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM, VirtualConsole } = require('jsdom');
const root = path.resolve(__dirname, '..');
const briefings = JSON.parse(fs.readFileSync(path.join(root, 'data/briefings.json'))).snapshots;
const latest = [...briefings].sort((a,b) => b.publishedAt.localeCompare(a.publishedAt))[0];
const live = JSON.parse(fs.readFileSync(path.join(root, 'data/live-headlines.json')));

async function check(width, remoteFailure = false) {
  const errors = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', error => errors.push(error.message));
  const dom = new JSDOM(fs.readFileSync(path.join(root, 'dist/index.html'), 'utf8'), {
    url: 'https://example.github.io/signal-dashboard/', runScripts: 'dangerously', virtualConsole: vc,
    beforeParse(window) {
      window.innerWidth = width;
      window.scrollTo = () => {};
      window.HTMLElement.prototype.scrollIntoView = () => {};
      window.fetch = async input => {
        if (remoteFailure) throw new Error('Simulated network failure');
        const relative = new URL(input, window.location.href).pathname.replace('/signal-dashboard/', '');
        const local = path.join(root, 'dist', relative);
        return fs.existsSync(local) ? { ok: true, json: async () => JSON.parse(fs.readFileSync(local, 'utf8')) }
          : { ok: false, status: 404 };
      };
    }
  });
  await new Promise(resolve => setTimeout(resolve, 100));
  const window = dom.window, doc = window.document;
  assert.equal(doc.querySelectorAll('[data-tab]').length, 4);
  assert.equal(doc.querySelectorAll('#mobileArchive option').length, briefings.length);
  assert.equal(doc.querySelector('#totalCount').textContent, `${latest.articles.length}개 기사`);
  for (const category of ['stocks', 'economy', 'politics', 'global']) {
    doc.querySelector(`[data-tab="${category}"]`).click();
    assert.equal(doc.querySelector(`[data-tab="${category}"]`).getAttribute('aria-selected'), 'true');
    assert.ok(doc.querySelectorAll('[data-story]').length > 0);
    doc.querySelector('[data-story]').click();
    assert.equal(doc.querySelector('[data-story]').getAttribute('aria-expanded'), 'true');
    assert.equal(doc.querySelectorAll('.story-detail h4').length, 6);
    assert.ok(doc.querySelector('.source-link').href.startsWith('https://'));
    doc.querySelector('[data-story]').click();
    assert.equal(doc.querySelectorAll('.story-detail').length, 0);
  }
  const picker = doc.querySelector('#mobileArchive');
  picker.value = '2026-10-15-08';
  picker.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(doc.querySelector('#totalCount').textContent, '4개 기사');
  assert.equal(doc.querySelector('#dayPicker').value, '2026-10-15');
  assert.ok(doc.querySelector('#metric-note').textContent.includes('복원'));
  doc.querySelector('[data-slot-id="2026-10-15-20"]').click();
  assert.equal(picker.value, '2026-10-15-20');
  const date = doc.querySelector('#dayPicker');
  date.value = '2026-10-19';
  date.dispatchEvent(new window.Event('change', { bubbles: true }));
  assert.equal(doc.querySelector('#totalCount').textContent, '16개 기사');
  if (!remoteFailure) {
    assert.equal(doc.querySelectorAll('.feed-link').length, live.articles.length);
    assert.ok(doc.querySelector('#automationStatus').textContent.includes('심층 분석 자동화'));
  } else {
    assert.ok(doc.querySelector('#automationStatus').textContent.includes('확인할 수 없습니다'));
  }
  assert.deepEqual(errors, []);
  dom.window.close();
  console.log(`DOM interaction checks passed: width=${width}, remoteFailure=${remoteFailure}`);
}

(async () => {
  for (const width of [360, 390, 768, 1280]) await check(width);
  await check(390, true);
})().catch(error => { console.error(error); process.exit(1); });
