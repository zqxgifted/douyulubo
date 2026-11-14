#!/usr/bin/env node
// SPDX-License-Identifier: MIT
/** Step 5b — 批量探测各分段可选画质档位（只查元数据，不下载视频）。
 *
 * 用法：DOUYU_CONFIG=/path/to/config.json node scripts/step5_probe_quality_all.js
 * 输出：data/quality_results.json（断点续跑）
 */
import fs from 'node:fs';
import path from 'node:path';

import { loadConfig } from '../src/config.mjs';
import { loadSigner, getQualityOptions } from '../src/douyu.mjs';

const cfg = loadConfig();
cfg.ensureDirs();

const IN_FILE = path.join(cfg.dataDir, 'probe_input.json');
const OUT_FILE = path.join(cfg.dataDir, 'quality_results.json');
if (!fs.existsSync(IN_FILE)) {
  console.error(`缺少 ${IN_FILE}，请先运行 step2_fetch_detail.py`);
  process.exit(1);
}
const IN = JSON.parse(fs.readFileSync(IN_FILE, 'utf8'));
let existing = {};
try { existing = JSON.parse(fs.readFileSync(OUT_FILE, 'utf8')); } catch {}

(async () => {
  let signFn = await loadSigner(IN[0].hash, cfg.ua);
  console.log('签名函数:', signFn);
  const todo = IN.filter((x) => !existing[x.hash]);
  console.log(`总数 ${IN.length}，已完成 ${IN.length - todo.length}，待探测 ${todo.length}`);
  const queue = [...todo];
  let done = 0, ok = 0, fail = 0;
  const errs = [];
  const t0 = Date.now();

  async function worker() {
    while (queue.length) {
      const item = queue.shift();
      try {
        let opts;
        try {
          opts = await getQualityOptions({ hash: item.hash, pointId: item.point_id, did: cfg.did, ua: cfg.ua, signFn });
        } catch (e) {
          signFn = await loadSigner(item.hash, cfg.ua);  // 签名脚本可能被轮换，重载一次
          opts = await getQualityOptions({ hash: item.hash, pointId: item.point_id, did: cfg.did, ua: cfg.ua, signFn });
        }
        existing[item.hash] = {
          key: item.key, title: item.title, folder: item.folder, options: opts,
        };
        ok++;
      } catch (e) {
        fail++;
        errs.push({ hash: item.hash, title: item.title, err: String(e.message || e).slice(0, 120) });
      }
      done++;
      if (done % 20 === 0) {
        fs.writeFileSync(OUT_FILE, JSON.stringify(existing, null, 1));
        console.log(`[${done}/${todo.length}] ok=${ok} fail=${fail} | ETA ${((Date.now() - t0) / done * (todo.length - done) / 60000).toFixed(1)}min`);
      }
      await new Promise((r) => setTimeout(r, 120));
    }
  }
  await Promise.all(Array.from({ length: 3 }, worker));
  fs.writeFileSync(OUT_FILE, JSON.stringify(existing, null, 1));
  fs.writeFileSync(path.join(cfg.dataDir, 'quality_errors.json'), JSON.stringify(errs, null, 1));
  console.log(`DONE ok=${ok} fail=${fail} elapsed=${((Date.now() - t0) / 1000).toFixed(0)}s`);
})();
