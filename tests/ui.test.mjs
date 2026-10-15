import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { transcriptText, splitText, summaryPrompt } from '../static/text.mjs';

// Optional local dependency directory allows offline testing with an existing jsdom install.
const require = createRequire(process.env.TEST_MODULE_ROOT ? resolve(process.env.TEST_MODULE_ROOT, 'package.json') : import.meta.url);
const { JSDOM } = require('jsdom');
const html = await readFile(new URL('../static/index.html', import.meta.url), 'utf8');
const source = (await readFile(new URL('../static/app.js', import.meta.url), 'utf8')).replace(/^import[^\n]+\n/, '');
const sample = {video_id: 'dQw4w9WgXcQ', url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', language: 'ko', is_generated: true, languages: [{code: 'ko', name: '한국어'}, {code: 'en', name: '영어'}], segments: [{text: '안녕하세요 <script>alert(1)</script>', start: 0}, {text: '다음 문장', start: 61}]};

function setup(fetcher, clipboard = true) {
  const dom = new JSDOM(html, {url: 'https://example.test/', runScripts: 'outside-only'});
  const window = dom.window;
  const copies = [];
  Object.assign(window, {transcriptText, splitText, summaryPrompt, fetch: fetcher});
  if (clipboard) Object.defineProperty(window.navigator, 'clipboard', {value: {writeText: async text => copies.push(text)}});
  window.eval(source);
  const $ = id => window.document.getElementById(id);
  const submit = async () => {
    $('url').value = sample.url;
    $('form').dispatchEvent(new window.Event('submit', {bubbles: true, cancelable: true}));
    await settle();
  };
  return {dom, window, $, copies, submit};
}
async function settle() { for (let i = 0; i < 4; i++) await new Promise(resolve => setImmediate(resolve)); }
const ok = async () => ({ok: true, json: async () => structuredClone(sample)});

test('submission renders captions as text, timestamps toggle, and both copy actions work', async () => {
  const {dom, $, window, copies, submit} = setup(ok);
  try {
    await submit();
    assert.equal($('result').hidden, false);
    assert.equal($('empty').hidden, true);
    assert.equal($('submit').disabled, false);
    assert.equal($('kind').textContent, '자동생성 자막');
    assert.equal($('transcript').value, transcriptText(sample.segments));
    assert.equal(window.document.querySelectorAll('#result script').length, 0);
    $('copy').click(); await settle();
    assert.equal(copies[0], transcriptText(sample.segments));
    $('timestamps').checked = true;
    $('timestamps').dispatchEvent(new window.Event('change'));
    assert.ok($('transcript').value.includes('[1:01] 다음 문장'));
    $('copy-prompt').click(); await settle();
    assert.equal(copies[1], summaryPrompt(sample, transcriptText(sample.segments, true)));
  } finally { dom.window.close(); }
});

test('clipboard denial provides the full requested text without replacing the original transcript', async () => {
  const {dom, $, submit} = setup(ok, false);
  try {
    await submit();
    const original = $('transcript').value;
    $('copy-prompt').click(); await settle();
    assert.equal($('manual-copy').hidden, false);
    assert.ok($('manual-text').value.includes('[대본 시작]'));
    assert.equal($('transcript').value, original);
    assert.equal($('manual-text').selectionEnd, $('manual-text').value.length);
  } finally { dom.window.close(); }
});

test('language change uses loaded video even when URL input was edited', async () => {
  const requests = [];
  const {dom, $, window, submit} = setup(async (_, options) => { requests.push(JSON.parse(options.body)); return ok(); });
  try {
    await submit();
    $('url').value = 'https://youtu.be/otherVideo1';
    $('language').value = 'en';
    $('language').dispatchEvent(new window.Event('change'));
    await settle();
    assert.equal(requests[1].url, sample.url);
    assert.equal(requests[1].language, 'en');
  } finally { dom.window.close(); }
});

test('upstream blocking gives a visible error and permits another submission', async () => {
  let calls = 0;
  const {dom, $, submit} = setup(async () => {
    if (++calls === 1) return {ok: false, json: async () => ({message: '유튜브가 서버 요청을 차단했습니다.'})};
    return ok();
  });
  try {
    await submit();
    assert.equal($('result').hidden, true);
    assert.equal($('status').classList.contains('error'), true);
    assert.ok($('status').textContent.includes('차단'));
    assert.equal($('submit').disabled, false);
    await submit();
    assert.equal($('result').hidden, false);
    assert.equal($('status').classList.contains('error'), false);
  } finally { dom.window.close(); }
});

test('long transcript shows chunk selector and copies the selected portion', async () => {
  const long = {...sample, segments: [{text: '안녕😀'.repeat(4000), start: 0}]};
  const {dom, $, copies, submit} = setup(async () => ({ok: true, json: async () => long}));
  try {
    await submit();
    assert.equal($('chunks').hidden, false);
    $('chunk').value = '1';
    $('copy-chunk').click(); await settle();
    assert.ok(copies[0].includes('대본 2/2'));
    assert.ok(copies[0].endsWith(splitText(long.segments[0].text)[1]));
  } finally { dom.window.close(); }
});
