#!/usr/bin/env node
// SPDX-License-Identifier: MIT
/** Step 5a — 探测斗鱼当前会给出的文件大小（m3u8 分片 HEAD 抽样估算）。
 *
 * 用法：DOUYU_CONFIG=/path/to/config.json node scripts/step5_probe_size_all.js
 * 输出：data/size_results.json（断点续跑）
 *
 * 注意：est_size 是推算值（标称码率或抽样均值 × 时长），实测误差 ±5~10%，
 * 只能作为「下限参照」，不能当 ±1MB 判据。
 */
import fs from 'node:fs';
import path from 'node:path';

import { loadConfig } from '../src/config.mjs';
import { loadSigner, getTopM3u8, parsePlaylist } from '../src/douyu.mjs';

const cfg = loadConfig();
cfg.ensureDirs();

const IN_FILE = path.join(cfg.dataDir, 'probe_input.json');
const OUT_FILE = path.join(cfg.dataDir, 'size_results.json');
if (!fs.existsSync(IN_FILE)) {
  console.error(`缺少 ${IN_FILE}，请先运行 step2_fetch_detail.py`);
  process.exit(1);
}
const IN = JSON.parse(fs.readFileSync(IN_FILE, 'utf8'));
let res = {};
try { res = JSON.parse(fs.readFileSync(OUT_FILE, 'utf8')); } catch {}

const SAMPLE_N = 8;

async function segSize(url) {
  try {
    const r = await fetch(url, { method: 'HEAD', headers: cfg.headers() });
    const cl = r.headers.get('content-length');
    if (cl) return parseInt(cl, 10);
  } catch {}
  try {
    const r = await fetch(url, { headers: { ...cfg.headers(), Range: 'bytes=0-0' } });
    const cr = r.headers.get('content-range');
    if (cr) { const m = cr.match(/\/(\d+)$/); if (m) return parseInt(m[1], 10); }
  } catch {}
  return 0;
}

async function measure(item, signFn) {
  const top = await getTopM3u8({
    hash: item.hash, pointId: item.point_id, did: cfg.did, ua: cfg.ua, signFn,
  });
  const pl = await (await fetch(top.url, { headers: cfg.headers() })).text();
  const { urls: segs, durations } = parsePlaylist(pl, top.url);
  const totalDur = durations.reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0);
  const N = Math.min(SAMPLE_N, segs.length);
  const sizes = [];
  for (let i = 0; i < N; i++) {
    const idx = Math.floor(i * segs.length / N);
    const s = await segSize(segs[idx]);
    if (s) sizes.push(s);
  }
  const avg = sizes.length ? sizes.reduce((a, b) => a + b, 0) / sizes.length : 0;
  return {
    key: item.key, folder: item.folder, title: item.title,
    official_bit_rate: top.bit_rate || 0,
    seg_count: segs.length, total_dur: Math.round(totalDur),
    sampled: sizes.length, avg_seg: Math.round(avg),
    est_size: Math.round(avg * segs.length),
    netdisk_size: item.netdisk_size || 0,
  };
}

(async () => {
  let signFn = await loadSigner(IN[0].hash, cfg.ua);
  console.log('签名函数:', signFn);
  const todo = IN.filter((x) => !res[x.hash]);
  console.log(`总数 ${IN.length}，已完成 ${IN.length - todo.length}，待测 ${todo.length}`);
  const queue = [...todo];
  let done = 0, ok = 0, fail = 0;
  const errs = [];
  const t0 = Date.now();

  async function worker() {
    while (queue.length) {
      const item = queue.shift();
      try {
        let r;
        try { r = await measure(item, signFn); }
        catch (e) {
          if (/error=7/.test(String(e))) { signFn = await loadSigner(item.hash, cfg.ua); r = await measure(item, signFn); }
          else throw e;
        }
        res[item.hash] = r; ok++;
      } catch (e) {
        fail++;
        errs.push({ hash: item.hash, key: item.key, err: String(e.message || e).slice(0, 100) });
      }
      done++;
      if (done % 25 === 0) {
        fs.writeFileSync(OUT_FILE, JSON.stringify(res, null, 1));
        console.log(`[${done}/${todo.length}] ok=${ok} fail=${fail} | ETA ${((Date.now() - t0) / done * (todo.length - done) / 60000).toFixed(1)}min`);
      }
      await new Promise((r) => setTimeout(r, 80));
    }
  }
  await Promise.all(Array.from({ length: 4 }, worker));
  fs.writeFileSync(OUT_FILE, JSON.stringify(res, null, 1));
  fs.writeFileSync(path.join(cfg.dataDir, 'size_errors.json'), JSON.stringify(errs, null, 1));
  console.log(`DONE ok=${ok} fail=${fail} elapsed=${((Date.now() - t0) / 1000).toFixed(0)}s`);
})();
