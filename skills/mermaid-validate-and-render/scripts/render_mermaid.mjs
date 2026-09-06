#!/usr/bin/env node
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { options, runBatch } from './batch_mermaid.mjs';

const [input, output, config, puppeteerConfig, ...extra] = process.argv.slice(2);
let temp;
try {
  if (!input || !output || extra.length || path.extname(input).toLowerCase() !== '.mmd') throw new Error('Usage: render_mermaid.sh <input.mmd> <output.svg|png> [mermaid-config.json] [puppeteer-config.json]');
  if (path.resolve(input) === path.resolve(output)) throw new Error('Input and output must differ');
  const format = path.extname(output).slice(1).toLowerCase();
  const opts = options(['--format', format, ...(config ? ['--config', config] : []), ...(puppeteerConfig ? ['--puppeteer-config', puppeteerConfig] : []), input]);
  temp = await fs.mkdtemp(path.join(os.tmpdir(), 'mermaid-single-'));
  const report = await runBatch({ ...opts, outDir: temp });
  if (!report.success) {
    console.error(JSON.stringify(report, null, 2));
    process.exitCode = report.diagrams.some(d => d.parse.kind === 'syntax' || d.render.kind === 'render') ? 2 : 1;
  } else {
    await fs.copyFile(report.diagrams[0].artifacts[0].path, output);
    console.log(`OK: parse and render succeeded for ${path.resolve(input)} -> ${path.resolve(output)}`);
  }
} catch (error) {
  console.error(JSON.stringify({ status: 'failed', kind: 'environment', message: error.message }));
  process.exitCode = 1;
} finally { if (temp) await fs.rm(temp, { recursive: true, force: true }); }
