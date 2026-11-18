// Pull the official print of a finished day's sheet.
//   node pipeline/render.mjs 2026-11-16
// Serves site/ (and the data directory) locally, opens the tray in render mode in headless
// Chromium (software GL, so it runs on GitHub's GPU-less runners), waits for the day to
// finish replaying, and saves site/sheets/<no>/sheet.jpg and og.jpg.
import {chromium} from 'playwright';
import http from 'node:http';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SITE = path.join(ROOT, 'site');
const DATA = process.env.DATA_DIR ? path.resolve(process.env.DATA_DIR) : path.join(SITE, 'data');
const date = process.argv[2];
if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) { console.error('usage: node render.mjs YYYY-MM-DD'); process.exit(1); }
const sheetNo = Math.floor((Date.UTC(...date.split('-').map((v, i) => i === 1 ? v - 1 : +v)) - Date.UTC(1823, 11, 3)) / 864e5) + 1;

const TYPES = {'.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.jpg': 'image/jpeg', '.css': 'text/css'};
const server = http.createServer(async (req, res) => {
  let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (p.endsWith('/')) p += 'index.html';
  const file = p.startsWith('/data/') ? path.join(DATA, p.slice(6)) : path.join(SITE, p);
  try { const b = await readFile(file); res.writeHead(200, {'content-type': TYPES[path.extname(file)] || 'application/octet-stream'}); res.end(b); }
  catch { res.writeHead(404); res.end(); }
}).listen(0);
const port = server.address().port;

const browser = await chromium.launch({executablePath: process.env.CHROME_PATH || undefined, args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist']});
const page = await browser.newPage({viewport: {width: 1800, height: 1200}});
page.on('pageerror', e => console.error('page error:', e.message));
await page.goto(`http://127.0.0.1:${port}/?render=${date}`);
console.log(`rendering sheet ${sheetNo} for ${date} (this takes a few minutes on a CPU)…`);
await page.waitForFunction(() => window.__sheetDone === true, null, {timeout: 40 * 60 * 1000, polling: 2000});
const out = path.join(SITE, 'sheets', String(sheetNo));
await mkdir(out, {recursive: true});
// Take the pictures from inside the page: draw the finished sheet once more and copy the canvas in the
// same task (a WebGL canvas is only readable straight after drawing). This avoids Playwright's
// "wait until the element is stable" check, which never settles on GitHub's software-GL runners.
const shots = await page.evaluate(() => {
  window.__drawSheet();
  const c = document.getElementById('cgl');
  const sheet = c.toDataURL('image/jpeg', 0.88);
  const o = document.createElement('canvas'); o.width = 1200; o.height = 630;
  const g = o.getContext('2d'); const k = Math.max(1200 / c.width, 630 / c.height);
  g.drawImage(c, (1200 - c.width * k) / 2, (630 - c.height * k) / 2, c.width * k, c.height * k);
  return {sheet, og: o.toDataURL('image/jpeg', 0.85)};
});
const save = (name, url) => writeFile(path.join(out, name), Buffer.from(url.split(',')[1], 'base64'));
await save('sheet.jpg', shots.sheet);
await save('og.jpg', shots.og);
console.log('saved', out);
await browser.close(); server.close();
