#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import puppeteer from "puppeteer";
import url from "node:url";

async function main() {
  const inputPath = process.argv[2];
  const puppeteerConfigPath =
    process.argv[3] || process.env.PUPPETEER_CONFIG_FILE || "";

  if (!inputPath) {
    console.error(
      "Usage: node scripts/validate_mermaid.mjs <input.mmd> [puppeteer-config.json]",
    );
    process.exit(1);
  }

  const resolvedPath = path.resolve(inputPath);
  const source = await fs.readFile(resolvedPath, "utf8");
  const pageUrl = url.pathToFileURL(
    path.resolve(
      path.dirname(url.fileURLToPath(import.meta.url)),
      "../node_modules/@mermaid-js/mermaid-cli/dist/index.html",
    ),
  ).href;
  const mermaidScriptPath = path.resolve(
    path.dirname(url.fileURLToPath(import.meta.url)),
    "../node_modules/mermaid/dist/mermaid.min.js",
  );
  const puppeteerConfig = { headless: "shell" };

  if (puppeteerConfigPath) {
    Object.assign(
      puppeteerConfig,
      JSON.parse(await fs.readFile(path.resolve(puppeteerConfigPath), "utf8")),
    );
  }

  const browser = await puppeteer.launch(puppeteerConfig);

  try {
    const page = await browser.newPage();
    await page.goto(pageUrl);
    await page.$eval("body", (body) => {
      body.innerHTML = "<div id=\"container\"></div>";
    });
    await page.addScriptTag({ path: mermaidScriptPath });
    await page.evaluate(
      async ({ definition }) => {
        const mermaid = globalThis.mermaid;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
        });
        await mermaid.parse(definition, { suppressErrors: false });
      },
      { definition: source },
    );
    console.log(`OK: parse succeeded for ${resolvedPath}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`ERROR: parse failed for ${resolvedPath}`);
    console.error(message.trim());
    process.exit(2);
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(message.trim());
  process.exit(1);
});
