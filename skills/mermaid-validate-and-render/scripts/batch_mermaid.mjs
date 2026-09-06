#!/usr/bin/env node
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const root = fileURLToPath(new URL('../', import.meta.url));
export const hash = value => createHash('sha256').update(value).digest('hex');
const message = error => error instanceof Error ? error.message : String(error);
const failure = (kind, error) => ({ status: 'failed', kind, message: message(error) });
const pending = () => ({ status: 'not_run' });

// Top-level CommonMark fences; other fenced languages are consumed, never re-scanned.
export function extractMarkdown(text) {
  const lines = text.replace(/\r\n?/g, '\n').split('\n');
  const result = [];
  let fence = null;
  let headings = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (fence) {
      const close = line.match(/^ {0,3}(`{3,}|~{3,})\s*$/);
      if (close && close[1][0] === fence.char && close[1].length >= fence.length) {
        if (fence.mermaid) result.push({ source: fence.lines.join('\n'), line: fence.line, heading: fence.heading, block: result.length + 1 });
        fence = null;
      } else fence.lines.push(line.slice(0, fence.indent).trim() === '' ? line.slice(fence.indent) : line);
      continue;
    }
    // Do not silently claim coverage for container-nested Mermaid blocks.
    if (/^\s*(?:>|[-+*]\s|\d+[.)]\s).*?(?:`{3,}|~{3,})\s*mermaid\b/i.test(line) || /^ {4,}(?:`{3,}|~{3,})\s*mermaid\b/i.test(line)) {
      throw new Error(`Unsupported nested Mermaid fence at line ${i + 1}; use top-level fences`);
    }
    const open = line.match(/^( {0,3})(`{3,}|~{3,})(.*)$/);
    if (open && !(open[2][0] === '`' && open[3].includes('`'))) {
      fence = { char: open[2][0], length: open[2].length, indent: open[1].length, mermaid: /^mermaid(?:\s|$)/i.test(open[3].trim()), lines: [], line: i + 2, heading: headings.filter(Boolean).join(' / ') };
      continue;
    }
    const heading = line.match(/^ {0,3}(#{1,6})(?:\s+|$)(.*)$/);
    if (heading) {
      headings = headings.slice(0, heading[1].length);
      headings[heading[1].length - 1] = heading[2].replace(/\s+#+\s*$/, '').trim();
    } else if (/^ {0,3}(?:=+|-+)\s*$/.test(line) && i > 0 && lines[i - 1].trim()) {
      const level = line.trim()[0] === '=' ? 1 : 2;
      headings = headings.slice(0, level);
      headings[level - 1] = lines[i - 1].trim();
    }
  }
  if (fence?.mermaid) throw new Error(`Unclosed Mermaid fence at line ${fence.line - 1}`);
  return result;
}

export function options(args) {
  const { values, positionals } = parseArgs({ args, allowPositionals: true, options: {
    'out-dir': { type: 'string' }, format: { type: 'string', default: 'png' },
    background: { type: 'string', default: 'white' }, width: { type: 'string', default: '1200' },
    config: { type: 'string' }, 'puppeteer-config': { type: 'string' },
    resume: { type: 'string' }, only: { type: 'string', multiple: true },
    'parse-only': { type: 'boolean', default: false }, help: { type: 'boolean' },
  }});
  if (values.help) return { help: true };
  if (!positionals.length) throw new Error('At least one .md, .markdown or .mmd input is required');
  const formats = [...new Set(values.format.split(','))];
  if (!formats.length || formats.some(f => !['png', 'svg'].includes(f))) throw new Error('--format must be png, svg or png,svg');
  const width = Number(values.width);
  if (!Number.isInteger(width) || width < 1 || width > 16384) throw new Error('--width must be an integer from 1 to 16384');
  return { inputs: [...new Set(positionals.map(p => path.resolve(p)))], outDir: values['out-dir'], formats,
    background: values.background, width, config: values.config,
    puppeteerConfig: values['puppeteer-config'] || process.env.PUPPETEER_CONFIG_FILE,
    resume: values.resume, only: values.only, parseOnly: values['parse-only'] };
}

export async function runBatch(opts) {
  const report = { schema: 1, startedAt: new Date().toISOString(), mode: opts.parseOnly ? 'parse-only' : 'parse-render',
    browserLaunchAttempts: 0, browserLaunches: 0, errors: [], diagrams: [] };
  let browser;
  let previous;
  let mermaidConfig;
  let launchConfig;
  let puppeteer;
  try {
    for (const file of opts.inputs) {
      try {
        const source = await fs.readFile(file, 'utf8');
        const ext = path.extname(file).toLowerCase();
        const blocks = ext === '.mmd' ? [{ source, block: 1, line: 1, heading: '' }]
          : ['.md', '.markdown'].includes(ext) ? extractMarkdown(source) : (() => { throw new Error('Unsupported input extension'); })();
        if (!blocks.length) throw new Error('No Mermaid blocks found');
        for (const block of blocks) report.diagrams.push({ ...block, file, id: `${file}#${block.block}`, inputHash: hash(block.source), parse: pending(), render: pending(), artifacts: [] });
      } catch (error) { report.errors.push({ ...failure(error.code ? 'environment' : 'input', error), file }); }
    }
    if (opts.only) for (const id of opts.only) {
      if (!report.diagrams.some(d => d.id === id)) report.errors.push(failure('input', `Unknown --only ID: ${id}`));
    }
    report.outputDirectory = opts.outDir ? path.resolve(opts.outDir) : await fs.mkdtemp(path.join(os.tmpdir(), 'mermaid-'));
    report.retention = 'Output directory is retained; remove it explicitly after visual review. No source copies are created.';
    report.reportPath = path.join(report.outputDirectory, 'report.json');
    if (opts.inputs.includes(report.reportPath)) throw new Error('Report path conflicts with input');
    await fs.mkdir(report.outputDirectory, { recursive: true });
    if (opts.resume) {
      previous = JSON.parse(await fs.readFile(opts.resume, 'utf8'));
      if (previous.schema !== 1 || !Array.isArray(previous.diagrams)) throw new Error('Unsupported resume report');
    }
    mermaidConfig = { startOnLoad: false, securityLevel: 'strict', ...(opts.config ? JSON.parse(await fs.readFile(opts.config, 'utf8')) : {}) };
    launchConfig = { headless: 'shell', ...(opts.puppeteerConfig ? JSON.parse(await fs.readFile(opts.puppeteerConfig, 'utf8')) : {}) };
    const version = async name => JSON.parse(await fs.readFile(path.join(root, 'node_modules', name, 'package.json'), 'utf8')).version;
    report.versions = { node: process.version, mermaid: await version('mermaid'), puppeteer: await version('puppeteer') };
    report.configuration = { mermaid: mermaidConfig, background: opts.background, width: opts.width, formats: opts.formats,
      puppeteerConfigHash: hash(JSON.stringify(launchConfig)) };
    report.engineHash = hash(await fs.readFile(fileURLToPath(import.meta.url)));
    report.parseKey = hash(JSON.stringify([report.versions, report.engineHash, mermaidConfig]));
    report.renderKey = hash(JSON.stringify([report.parseKey, report.configuration]));
    puppeteer = (await import('puppeteer')).default;
    for (const diagram of report.diagrams) {
      const old = previous?.diagrams.find(d => d.id === diagram.id && d.inputHash === diagram.inputHash);
      const sameParse = previous?.parseKey === report.parseKey && old?.parse.status === 'success';
      const selected = !opts.only || opts.only.includes(diagram.id);
      if (sameParse) diagram.parse = { status: 'success', reused: true, from: path.resolve(opts.resume) };
      if (sameParse && previous?.renderKey === report.renderKey && old?.render.status === 'success' &&
          old.artifacts?.length === opts.formats.length &&
          await Promise.all(old.artifacts.map(async a => {
            try { return opts.formats.includes(a.format) && hash(await fs.readFile(a.path)) === a.hash; } catch { return false; }
          })).then(results => results.every(Boolean))) {
        diagram.render = { status: 'success', reused: true, from: path.resolve(opts.resume) };
        diagram.artifacts = old.artifacts;
      }
      if (!selected) { diagram.selected = false; continue; }
      diagram.selected = true;
      if (diagram.parse.status === 'success' && (opts.parseOnly || diagram.render.status === 'success')) continue;
      let page;
      try {
        if (!browser) {
          report.browserLaunchAttempts++;
          try { browser = await puppeteer.launch(launchConfig); report.browserLaunches++; report.versions.browser = await browser.version(); }
          catch (error) {
            report.errors.push(failure('environment', error));
            for (const remaining of report.diagrams.filter(d => !opts.only || opts.only.includes(d.id))) {
              if (remaining.parse.status === 'not_run') remaining.parse = failure('environment', error);
              else if (!opts.parseOnly && remaining.render.status === 'not_run') remaining.render = failure('environment', error);
            }
            break;
          }
        }
        page = await browser.newPage();
        await page.setViewport({ width: opts.width, height: 900, deviceScaleFactor: 1 });
        await page.setContent('<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0"><div id="container"></div></body></html>');
        await page.addScriptTag({ path: path.join(root, 'node_modules/mermaid/dist/mermaid.min.js') });
        await page.evaluate(config => globalThis.mermaid.initialize(config), mermaidConfig);
        if (diagram.parse.status !== 'success') {
          const parsed = await page.evaluate(async source => {
            try { await globalThis.mermaid.parse(source, { suppressErrors: false }); return { status: 'success' }; }
            catch (error) { return { status: 'failed', kind: 'syntax', message: String(error.message || error) }; }
          }, diagram.source);
          diagram.parse = parsed;
        }
        if (diagram.parse.status !== 'success' || opts.parseOnly) continue;
        if (diagram.render.status === 'success') continue;
        const rendered = await page.evaluate(async ({ source, background }) => {
          try {
            if (!CSS.supports('background-color', background)) return { status: 'failed', kind: 'environment', message: 'Invalid background color' };
            // Mermaid otherwise replaces oversized source with a rendered warning diagram.
            if (source.length > globalThis.mermaid.mermaidAPI.getConfig().maxTextSize) return { status: 'failed', kind: 'render', message: 'Source exceeds Mermaid maxTextSize; original diagram was not rendered' };
            const { svg } = await globalThis.mermaid.render('diagram', source);
            document.querySelector('#container').innerHTML = svg;
            const element = document.querySelector('#container svg');
            element.style.backgroundColor = background;
            await document.fonts.ready;
            return { status: 'success', svg: element.outerHTML };
          } catch (error) { return { status: 'failed', kind: 'render', message: String(error.message || error) }; }
        }, { source: diagram.source, background: opts.background });
        if (rendered.status !== 'success') { diagram.render = rendered; continue; }
        for (const format of opts.formats) {
          const output = path.join(report.outputDirectory, `${hash(diagram.id).slice(0, 16)}-${diagram.block}.${format}`);
          const data = format === 'svg' ? Buffer.from(rendered.svg) : await (await page.$('#container svg')).screenshot({ omitBackground: true });
          await fs.writeFile(output, data);
          diagram.artifacts.push({ format, path: output, hash: hash(data) });
        }
        diagram.render = { status: 'success' };
      } catch (error) {
        if (diagram.parse.status !== 'success') diagram.parse = failure('environment', error);
        else diagram.render = failure('environment', error);
      } finally { if (page) await page.close().catch(error => report.errors.push(failure('environment', error))); }
    }
  } catch (error) { report.errors.push(failure('environment', error)); }
  finally { if (browser) await browser.close().catch(error => report.errors.push(failure('environment', error))); }
  report.finishedAt = new Date().toISOString();
  report.success = report.errors.length === 0 && report.diagrams.length > 0 && report.diagrams.every(d => d.parse.status === 'success' && (opts.parseOnly || d.render.status === 'success'));
  for (const d of report.diagrams) delete d.source;
  if (report.reportPath) {
    try { await fs.writeFile(report.reportPath, JSON.stringify(report, null, 2) + '\n'); }
    catch (error) { report.errors.push(failure('environment', error)); report.success = false; }
  }
  return report;
}

export async function cli(args = process.argv.slice(2)) {
  try {
    const opts = options(args);
    if (opts.help) {
      console.log('Usage: node scripts/batch_mermaid.mjs [--out-dir DIR] [--format png|svg|png,svg] [--background white|transparent|COLOR] [--width PIXELS] [--config FILE] [--puppeteer-config FILE] [--resume REPORT] [--only ABSOLUTE_FILE#BLOCK ...] [--parse-only] INPUT...');
      return;
    }
    const report = await runBatch(opts);
    console.log(JSON.stringify(report, null, 2));
    process.exitCode = report.success ? 0 : report.errors.some(e => e.kind === 'environment') || report.diagrams.some(d => [d.parse, d.render].some(s => s.kind === 'environment')) ? 1 : 2;
  } catch (error) { console.error(JSON.stringify(failure('input', error))); process.exitCode = 1; }
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) await cli();
