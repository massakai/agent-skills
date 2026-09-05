import test from 'node:test';
import assert from 'node:assert/strict';
import { extractMarkdown, options } from '../scripts/batch_mermaid.mjs';

test('fences, headings, CRLF, ignored examples and block locations', () => {
  const input = ['# 設計', '```text', '## 無視', '~~~mermaid', 'ignored', '~~~', '```', '## 注文', '  ````mermaid', '  flowchart LR', '  A["注文"] --> B["確認"]', '  ````', '結果', '----', '~~~mermaid', 'sequenceDiagram', 'A->>B: 完了', '~~~'].join('\r\n');
  const blocks = extractMarkdown(input);
  assert.equal(blocks.length, 2);
  assert.deepEqual(blocks.map(({ block, line, heading }) => ({ block, line, heading })), [
    { block: 1, line: 10, heading: '設計 / 注文' }, { block: 2, line: 16, heading: '設計 / 結果' },
  ]);
  assert.equal(blocks[0].source, 'flowchart LR\nA["注文"] --> B["確認"]');
});
test('rejects unclosed and container-nested Mermaid instead of ignoring it', () => {
  for (const source of ['```mermaid\nflowchart LR', '> ```mermaid\n> A', '    ```mermaid']) assert.throws(() => extractMarkdown(source));
});
test('CLI options validate formats and width; multiple inputs and selectors', () => {
  const opts = options(['--format', 'png,svg', '--width', '640', '--only', '/a.md#2', 'a.md', 'b.mmd']);
  assert.equal(opts.width, 640);
  assert.equal(opts.inputs.length, 2);
  assert.deepEqual(opts.formats, ['png', 'svg']);
  for (const args of [[], ['--width', 'NaN', 'x.mmd'], ['--format', 'pdf', 'x.mmd'], ['--unknown', 'x.mmd']]) assert.throws(() => options(args));
});
