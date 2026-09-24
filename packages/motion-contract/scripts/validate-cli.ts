#!/usr/bin/env -S npx tsx
// Validates every fixtures/*.json against MotionResult. Run: npm run validate
import { readFileSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { validateMotionResult } from "../src/ts/validate.js";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const fixturesDir = path.join(root, "fixtures");

let anyFailed = false;
for (const file of readdirSync(fixturesDir).filter((f) => f.endsWith(".json"))) {
  const doc = JSON.parse(readFileSync(path.join(fixturesDir, file), "utf-8"));
  const result = validateMotionResult(doc);
  if (result.valid) {
    console.log(`OK   ${file}`);
  } else {
    anyFailed = true;
    console.log(`FAIL ${file}`);
    for (const err of result.errors) console.log(`     ${err}`);
  }
}
process.exit(anyFailed ? 1 : 0);
