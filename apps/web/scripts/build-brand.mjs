/**
 * Writes every brand image from lib/brand.ts, so the mark lives in one place:
 *
 *   app/icon.svg                 favicon (any size; browsers draw it at 16 and 32)
 *   app/icon.png                 32 px fallback
 *   app/apple-icon.png           180 px, full bleed (iOS rounds it)
 *   public/icons/icon-{192,512}.png, icon-maskable-512.png   the manifest's
 *   app/opengraph-image.png      1200 x 630 share image, the wave pose
 *
 * Run after changing the mark: `node --import tsx scripts/build-brand.mjs`.
 * PNGs are rasterised by headless Chrome (CHROME=/path/to/chrome, default the
 * macOS install); the outputs are committed, so a build never needs Chrome.
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { ACCENT, INK, PAPER, WAVE_POSE, markBox, markShapes, markTile } from "../lib/brand.ts";
import { PRODUCT_NAME, marketing } from "../lib/copy.ts";

const WEB = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
const CHROME = process.env.CHROME ?? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const tmp = mkdtempSync(path.join(tmpdir(), "brand-"));

function png(out, w, h, body, head = "") {
  const html = path.join(tmp, `${path.basename(out)}.html`);
  writeFileSync(html, `<!doctype html><html><head><meta charset="utf-8">${head}<style>html,body{margin:0;background:transparent}svg{display:block}</style></head><body>${body}</body></html>`);
  execFileSync(CHROME, [
    "--headless", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
    "--default-background-color=00000000", "--virtual-time-budget=4000",
    `--window-size=${w},${h}`, `--screenshot=${path.join(WEB, out)}`, `file://${html}`,
  ], { stdio: "ignore" });
  console.log("wrote", out);
}

// The favicon: marigold rounded tile, the figure nearly filling it.
const favicon = markTile({ size: 32, fit: 0.88, bg: ACCENT, rx: 7 });
writeFileSync(path.join(WEB, "app/icon.svg"), favicon);
console.log("wrote app/icon.svg");
png("app/icon.png", 32, 32, favicon);

// Home-screen tiles: full bleed, the figure on its floor line, inside the safe zone.
png("app/apple-icon.png", 180, 180, markTile({ size: 180, fit: 0.66, bg: ACCENT, floor: true }));
png("public/icons/icon-192.png", 192, 192, markTile({ size: 192, fit: 0.66, bg: ACCENT, floor: true }));
png("public/icons/icon-512.png", 512, 512, markTile({ size: 512, fit: 0.66, bg: ACCENT, floor: true }));
// Maskable: everything inside the central 80% circle.
png("public/icons/icon-maskable-512.png", 512, 512, markTile({ size: 512, fit: 0.5, bg: ACCENT, floor: true }));

// The share image: wordmark and the hero line on paper, the wave on a marigold tile.
const [x0, y0, x1, y1] = markBox(WAVE_POSE);
const wave = `<svg viewBox="${x0} ${y0} ${x1 - x0} ${y1 - y0}" style="height:400px;width:auto">${markShapes({ pose: WAVE_POSE, ink: INK, head: INK })}</svg>`;
const fonts = `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wdth,wght@12..96,75..100,400..800&display=block">`;
png("app/opengraph-image.png", 1200, 630,
  `<div style="width:1200px;height:630px;display:flex;background:${PAPER};color:${INK};font-family:'Bricolage Grotesque',sans-serif">
    <div style="flex:1;display:flex;flex-direction:column;justify-content:center;padding:0 72px">
      <div style="font-weight:800;font-size:112px;letter-spacing:-0.03em;font-variation-settings:'wdth' 85,'opsz' 96;line-height:1">${PRODUCT_NAME}</div>
      <div style="font-weight:700;font-size:44px;letter-spacing:-0.02em;font-variation-settings:'wdth' 85,'opsz' 48;margin-top:28px;line-height:1.1">${marketing.hero.headlineLead}<br>${marketing.hero.headlineAccent}</div>
    </div>
    <div style="width:480px;background:${ACCENT};display:flex;align-items:center;justify-content:center">${wave}</div>
  </div>`,
  fonts);
