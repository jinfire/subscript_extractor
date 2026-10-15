import { test } from 'node:test';
import assert from 'node:assert/strict';
import { transcriptText, timestamp, splitText, summaryPrompt } from '../static/text.mjs';

test('timestamps support hour-long videos', () => {
  assert.equal(timestamp(9.9), '0:09');
  assert.equal(timestamp(3661), '1:01:01');
});

test('plain text and timed text preserve actual caption contents', () => {
  const segments = [{text: '안녕하세요', start: 0}, {text: '다음 내용', start: 61}];
  assert.equal(transcriptText(segments), '안녕하세요 다음 내용');
  assert.equal(transcriptText(segments, true), '[0:00] 안녕하세요\n[1:01] 다음 내용');
});

test('split and recombine without losing text or breaking emoji', () => {
  const input = '가😀 '.repeat(6000);
  const chunks = splitText(input);
  assert.ok(chunks.length > 1);
  assert.equal(chunks.join(''), input);
  assert.ok(chunks.every(s => Array.from(s).length <= 8000));
  assert.ok(chunks.every(s => s.isWellFormed()));
});

test('copy prompt includes source, generation type, and complete original text', () => {
  const text = '원문 <script>내용</script>';
  const prompt = summaryPrompt({url: 'https://youtu.be/example', language: 'ko', is_generated: true}, text);
  assert.ok(prompt.includes('https://youtu.be/example'));
  assert.ok(prompt.includes('자동생성'));
  assert.ok(prompt.includes(`[대본 시작]\n${text}\n[대본 끝]`));
});
