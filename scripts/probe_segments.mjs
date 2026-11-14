#!/usr/bin/env node
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 douyulubo contributors
/**
 * 探测每个分段的最高清晰度与预计大小（只读元数据 + HEAD 少量抽样，不下载视频）。
 *
 * 结果写入 data/segment_meta.json：
 *   { "<hash_id>": { quality, bit_rate, est_size, seg_count, duration_sec }, ... }
 *
 * 用法：DOUYU_CONFIG=config.json node scripts/probe_segments.mjs [--limit N]
 */
import fs from 'node:fs';
import path from 'node:path';

import { loadConfig } from '../src/config.mjs';
import { loadSigner, getTopM3u8, parsePlaylist } from '../src/douyu.mjs';

const cfg = loadConfig();
cfg.ensureDirs();

const SEG_FILE = path.join(cfg.dataDir, 'segments_index.json');
const OUT_FILE = path.join(cfg.dataDir, 'segment_meta.json');

if (!fs.existsSync(SEG_FILE)) {
  console.error(`缺少 ${SEG_FILE}，请先运行 list_shows.py`);
  process.exit(1);
}

const segs = JSON.parse(fs.readFileSync(SEG_FILE, 'utf8'));
let meta = {};
try { meta = JSON.parse(fs.readFileSync(OUT_FILE, 'utf8')); } catch { /* 新建 */ }

// 可选：只探测前 N 个（先试跑）
let limit = Infinity;
const li = process.argv.indexOf('--limit');
if (li > 0 && process.argv[li + 1]) limit = parseInt(process.argv[li + 1], 10) || Infinity;

const todo = segs.filter((s) => s.hash_id && !meta[s.hash_id]).slice(0, limit);
console.log(`待探测 ${todo.length} / 共 ${segs.length} 个分段`);

async function segSize(url) {
  try {
    const r = await fetch(url, { method: 'HEAD', headers: cfg.headers() });
    const cl = r.headers.get('content-length');
    if (cl) return parseInt(cl, 10);
  } catch { /* 回退 Range */ }
  try {
    const r = await fetch(url, { headers: { ...cfg.headers(), Range: 'bytes=0-0' } });
    const cr = r.headers.get('content-range');
    if (cr) { const m = cr.match(/\/(\d+)$/); if (m) return parseInt(m[1], 10); }
  } catch { /* 忽略 */ }
  return 0;
}

let signFn = null;
if (todo.length) {
  try { signFn = await loadSigner(todo[0].hash_id, cfg.ua); } catch (e) { console.error(e.message); }
}

const queue = [...todo];
let done = 0, ok = 0, fail = 0;
const t0 = Date.now();

async function worker() {
  while (queue.length) {
    const it = queue.shift();
    try {
      if (!signFn) signFn = await loadSigner(it.hash_id, cfg.ua);
      const top = await getTopM3u8({
        hash: it.hash_id, pointId: it.point_id, did: cfg.did, ua: cfg.ua, signFn,
      }).catch(async (e) => {
        // 签名可能轮换，重载一次
        signFn = await loadSigner(it.hash_id, cfg.ua);
        return getTopM3u8({
          hash: it.hash_id, pointId: it.point_id, did: cfg.did, ua: cfg.ua, signFn,
        });
      });

      const pl = await (await fetch(top.url, { headers: cfg.headers() })).text();
      const { urls, durations } = parsePlaylist(pl, top.url);
      const dur = durations.reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0);


      // 抽样 6 个分片估算平均大小
      const N = Math.min(6, urls.length);
      const sizes = [];
      for (let i = 0; i < N; i++) {
        const idx = Math.floor(i * urls.length / N);
        const s = await segSize(urls[idx]);
        if (s) sizes.push(s);
      }
      const avg = sizes.length ? sizes.reduce((a, b) => a + b, 0) / sizes.length : 0;

      // 斗鱼返回的 fsize 是官方给出的真实字节数（最准），优先用它
      const fsize = parseInt(top.fsize || '0', 10);
      const estFromSegs = Math.round(avg * urls.length);
      const est = fsize > 0 ? fsize : estFromSegs;
      // 真实码率 = 文件大小 ÷ 时长（最可靠）。
      // 斗鱼返回的 bit_rate 字段单位混乱（有时是 B/s，语义不明确），不用它。
      let kbps = 0;
      if (est > 0 && dur > 0) {
        kbps = Math.round(est * 8 / dur / 1000);
      } else if (top.bit_rate) {
        kbps = Math.round(top.bit_rate / 1000);
      }
      meta[it.hash_id] = {
        quality: top.name || '',
        bit_rate: kbps,
        est_size: est,
        est_source: fsize > 0 ? 'official' : 'sampled',
        seg_count: urls.length,
        duration_sec: Math.round(dur),
      };
      ok++;
    } catch (e) {
      meta[it.hash_id] = { error: String(e.message || e).slice(0, 80) };
      fail++;
    }
    done++;
    if (done % 20 === 0) {
      fs.writeFileSync(OUT_FILE, JSON.stringify(meta, null, 1));
      const eta = (Date.now() - t0) / done * (todo.length - done) / 1000;
      console.log(`[${done}/${todo.length}] ok=${ok} fail=${fail} | ETA ${eta.toFixed(0)}s`);
    }
    await new Promise((r) => setTimeout(r, 60));
  }
}

await Promise.all(Array.from({ length: 4 }, worker));
fs.writeFileSync(OUT_FILE, JSON.stringify(meta, null, 1));
console.log(`DONE ok=${ok} fail=${fail} 用时 ${((Date.now() - t0) / 1000).toFixed(0)}s`);
console.log(`已保存 ${OUT_FILE}`);
