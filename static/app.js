import { transcriptText, splitText, summaryPrompt } from './text.mjs';

const $ = id => document.getElementById(id);
let data = null;
let chunks = [];
let busy = false;
let loadedUrl = '';
let toastTimeout;
function toast(message) {
  clearTimeout(toastTimeout);
  $('toast').textContent = message;
  $('toast').hidden = false;
  toastTimeout = setTimeout(() => { $('toast').hidden = true; }, 3000);
}
function status(message, error = false) {
  $('status').textContent = message;
  $('status').classList.toggle('error', error);
}
function render() {
  if (!data) return;
  const text = transcriptText(data.segments, $('timestamps').checked);
  $('transcript').value = text;
  $('count').textContent = `${Array.from(text).length.toLocaleString()}자`;
  chunks = splitText(text);
  $('chunks').hidden = chunks.length <= 1;
  $('chunk').replaceChildren(...chunks.map((_, index) => new Option(`${index + 1} / ${chunks.length} 부분`, index)));
}
async function load(language = null) {
  if (busy) return;
  const url = language ? loadedUrl : $('url').value.trim();
  if (!url) return;
  busy = true;
  $('submit').disabled = true;
  $('submit').textContent = '가져오는 중…';
  $('language').disabled = true;
  $('result').hidden = true;
  $('empty').hidden = true;
  $('manual-copy').hidden = true;
  $('spinner').hidden = false;
  $('form').setAttribute('aria-busy', 'true');
  status('자막을 가져오고 있어요. 잠시 기다려 주세요.');
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 90000);
  try {
    const response = await fetch('/api/transcript', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url, language}), signal: controller.signal
    });
    let body;
    try { body = await response.json(); }
    catch { throw new Error('서버 응답을 읽지 못했습니다. 잠시 후 다시 시도해 주세요.'); }
    if (!response.ok) throw new Error(body.message || '대본을 가져오지 못했습니다.');
    data = body;
    loadedUrl = body.url;
    $('source').href = body.url;
    $('language').replaceChildren(...body.languages.map(l => new Option(l.name, l.code)));
    $('language').value = body.language;
    $('kind').textContent = body.is_generated ? '자동생성 자막' : '수동 자막';
    $('result').hidden = false;
    render();
    status('대본을 가져왔어요. 아래에서 바로 복사하세요.');
  } catch (error) {
    $('empty').hidden = false;
    status(error.name === 'AbortError' ? '응답이 늦어지고 있습니다. 잠시 후 다시 시도해 주세요.' : error instanceof TypeError ? '서버에 연결하지 못했습니다. 인터넷 연결을 확인해 주세요.' : error.message, true);
  } finally {
    clearTimeout(timeout);
    busy = false;
    $('submit').disabled = false;
    $('submit').textContent = '대본 가져오기 ↗';
    $('language').disabled = false;
    $('spinner').hidden = true;
    $('form').setAttribute('aria-busy', 'false');
  }
}
async function copy(text) {
  try {
    if (!navigator.clipboard) throw new Error('Clipboard unavailable');
    await navigator.clipboard.writeText(text);
    $('manual-copy').hidden = true;
    status('복사했어요. ChatGPT에 붙여넣어 주세요.');
    toast('복사했어요. ChatGPT에 붙여넣어 주세요.');
  } catch {
    $('manual-copy').hidden = false;
    $('manual-text').value = text;
    $('manual-text').focus();
    $('manual-text').select();
    $('manual-text').setSelectionRange(0, text.length);
    status('자동 복사를 사용할 수 없어 직접 복사할 텍스트를 선택했어요.');
  }
}
$('form').addEventListener('submit', event => { event.preventDefault(); load(); });
$('language').addEventListener('change', () => load($('language').value));
$('timestamps').addEventListener('change', render);
$('copy').addEventListener('click', () => copy(transcriptText(data.segments, $('timestamps').checked)));
$('copy-prompt').addEventListener('click', () => copy(summaryPrompt(data, transcriptText(data.segments, $('timestamps').checked))));
$('copy-chunk').addEventListener('click', () => {
  const index = Number($('chunk').value);
  const instruction = index === chunks.length - 1 ? '마지막 부분입니다. 이전에 전달한 대본과 합쳐 핵심 내용, 주요 주장과 근거, 사실 확인이 필요한 부분을 한국어로 요약·분석해 주세요.' : '모든 부분을 전달할 때까지 분석하지 말고 기다려 주세요.';
  copy(`영상 URL: ${data.url}\n대본 ${index + 1}/${chunks.length}\n${instruction}\n\n${chunks[index]}`);
});
$('close-manual').addEventListener('click', () => { $('manual-copy').hidden = true; });
