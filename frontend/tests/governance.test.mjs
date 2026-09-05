import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { errorMessage } from '../src/api/errorMessage.js';

const server = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, optimizeDeps: { noDiscovery: true, include: [] } });
after(() => server.close());
const load = async (path) => (await server.ssrLoadModule(`/src/${path}.jsx`)).default;
const render = (component, props) => renderToStaticMarkup(createElement(component, props));

test('service block is actionable and never exposes backend details', () => {
  const message = errorMessage({ response: { status: 503, data: { detail: 'private deployment config' } } }, 'Failure');
  assert.match(message, /temporarily unavailable/);
  assert.doesNotMatch(message, /private/);
  assert.equal(typeof errorMessage({ response: { status: 422, data: { detail: [{}] } } }, 'Failure'), 'string');
});

test('retrieved evidence preserves timestamps and treats transcript markup as text', async () => {
  const SourceEvidence = await load('components/workspace/SourceEvidence');
  const html = render(SourceEvidence, { sources: [{ start_time: 65, end_time: 80, text: '<script>private</script>' }] });
  assert.match(html, /01:05/);
  assert.match(html, /01:20/);
  assert.match(html, /&lt;script&gt;/);
  assert.doesNotMatch(html, /<script>/);
});

test('missing historical sources are distinguished from empty retrieval', async () => {
  const SourceEvidence = await load('components/workspace/SourceEvidence');
  assert.match(render(SourceEvidence, { sources: null }), /not saved/);
  assert.match(render(SourceEvidence, { sources: [] }), /No matching transcript/);
});

test('processing disclosure appears before submission and unsupported providers are absent', async () => {
  const InputBox = await load('components/landing/InputBox');
  const html = render(InputBox, { loading: false, onAnalyze() {} });
  assert.ok(html.indexOf('sent to Groq') < html.indexOf('<form'));
  assert.match(html, /retention practices/);
  assert.doesNotMatch(html, /Vimeo|Google Drive/);
});

test('issue reports cannot be mistaken for submitted feedback', async () => {
  const IssueReport = await load('components/governance/IssueReport');
  const html = render(IssueReport, { videoId: 'video-id', answerId: 'answer-id' });
  assert.match(html, /no in-app submission service/);
  assert.match(html, /Download issue report/);
});

test('failed video never offers a question composer or an AI summary', async () => {
  const Workspace = await load('pages/WorkspacePage');
  const html = render(Workspace, { video: { id: 'id', status: 'failed', summary: 'stale summary' } });
  assert.match(html, /Analysis couldn/);
  assert.doesNotMatch(html, /Ask question|stale summary/);
});

test('completed video labels the summary and renders the server expiry', async () => {
  const Workspace = await load('pages/WorkspacePage');
  const html = render(Workspace, { video: { id: 'id', status: 'completed', summary: 'A short summary.', expires_at: '2026-09-06T12:00:00Z' } });
  assert.match(html, /AI-generated summary/);
  assert.match(html, /only the beginning/);
  assert.match(html, /dateTime="2026-09-06T12:00:00.000Z"/i);
});
