#!/usr/bin/env node
import { cli } from './batch_mermaid.mjs';
const [input, config, ...extra] = process.argv.slice(2);
if (!input || extra.length) {
  console.error('Usage: node scripts/validate_mermaid.mjs <input.mmd> [puppeteer-config.json]');
  process.exitCode = 1;
} else await cli(['--parse-only', ...(config ? ['--puppeteer-config', config] : []), input]);
