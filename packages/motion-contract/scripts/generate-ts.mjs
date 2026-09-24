#!/usr/bin/env node
// Regenerates src/ts/generated/*.ts from schema/*.schema.json. Run: npm run generate.
import { compile } from "json-schema-to-typescript";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

const targets = [
  { schema: "motion-result.schema.json", typeName: "MotionResult", out: "motion-result.ts" },
  { schema: "job-status.schema.json", typeName: "JobStatus", out: "job-status.ts" },
];

const banner = `/**
 * GENERATED FILE — do not edit by hand.
 * Source of truth: packages/motion-contract/schema/*.schema.json
 * Regenerate with: npm run generate
 */\n\n`;

for (const { schema, typeName, out } of targets) {
  const schemaPath = path.join(root, "schema", schema);
  const schemaJson = JSON.parse(readFileSync(schemaPath, "utf-8"));
  const ts = await compile(schemaJson, typeName, {
    additionalProperties: false,
    style: { singleQuote: false },
  });
  writeFileSync(path.join(root, "src", "ts", "generated", out), banner + ts);
  console.log(`wrote src/ts/generated/${out}`);
}
