#!/usr/bin/env node
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 douyulubo contributors
/**
 * 探测指定场次（一页）下的所有分段：清晰度 + 预计大小。
 *
 * 只处理传入的 show_id，不碰其它场次，所以一页（20 场约 40-80 段）几秒就能完成。
 * 会自动补 point_id（缺失时），不需要事先跑 --with-pid。
 *
 * 用法：
 *   DOYULU_CONFIG=config.json node scripts/probe_page.mjs --shows 252629647,251456789
 */
import fs from 'node:fs';
import path from 'node:path';

import { loadConfig } from '../src/config.mjs';
import { loadSigner, getTopM3u8 } from '../src/douyu.mjs';

const cfg = loadConfig();
cfg.ensureDirs();

const SEG_FILE = path.join(cfg.dataDir, 'segments_index.json');
const META_FILE = path.join(cfg.dataDir, 'segment_meta.json');

if (!fs.existsSync(SEG_FILE)) {
  console.error(`缺少 ${SEG_FILE}，请先搜索`);
  process.exit(1);
}

// 解析 --shows a,b,c
let showIds = null;
const si = process.argv.indexOf('--shows');
if (si > 0 && process.argv[si + 1]) {
  showIds = new Set(String(process.argv[si + 1]).split(',').filter(Boolean));
}

const allSegs = JSON.parse(fs.readFileSync(SEG_FILE, 'utf8'));
let meta = {};
try { meta = JSON.parse(fs.readFileSync(META_FILE, 'utf8')); } catch { /* 新建 */ }

const FORCE_TIME = process.argv.includes('--force-time');

const targets = allSegs.filter((s) => {
  if (!s.hash_id) return false;
  if (showIds && !showIds.has(String(s.show_id))) return false;
  if (FORCE_TIME) return !s.exact_time;   // 只补时间
  const m = meta[s.hash_id];
  return !m || m.error;     // 没探测过，或上次失败
});

console.log(`本页待探测 ${targets.length} 段（共 ${allSegs.length} 段）`);
if (!targets.length) {
  console.log('本页已全部探测过');
  process.exit(0);
}

// ---- 取 point_id ----
async function fetchPointId(hash) {
  const html = await (await fetch(`https://v.douyu.com/show/${hash}`,
    { headers: cfg.headers() })).text();
  const m = html.match(new RegExp(`\\{"vid":"${hash}","point_id":(\\d+)`));
  // 顺便抓精确开始时间（播放页给了秒级 start_time）
  const st = html.match(/"start_time"\s*:\s*(\d{10})/);
  return {
    pointId: m ? parseInt(m[1], 10) : null,
    startTime: st ? parseInt(st[1], 10) : 0,
  };
}

// ---- 取最高画质 + 大小 ----
async function probeOne(seg, pointId) {
  const signFn = await loadSigner(seg.hash_id, cfg.ua);
  const top = await getTopM3u8({
    hash: seg.hash_id, pointId, did: cfg.did, ua: cfg.ua, signFn,
  });

  const fsize = parseInt(top.fsize || '0', 10);
  const dur = Number(seg.duration_sec || 0);
  let est = fsize;
  if (!est && top.bit_rate && dur) {
    est = Math.round(top.bit_rate * dur);   // bit_rate 单位约等于 B/s
  }
  let kbps = 0;
  if (est > 0 && dur > 0) kbps = Math.round(est * 8 / dur / 1000);

  return {
    quality: top.name || '',
    bit_rate: kbps,
    est_size: est,
    est_source: fsize > 0 ? 'official' : 'derived',
    duration_sec: Math.round(dur),
  };
}

// ---- 并发处理 ----
const queue = [...targets];
let done = 0, ok = 0, fail = 0;
const t0 = Date.now();

async function worker() {
  while (queue.length) {
    const seg = queue.shift();
    const hid = seg.hash_id;
    try {
      let pid = seg.point_id;
      if (!pid || !seg.exact_time) {
        const info = await fetchPointId(hid);
        if (info.pointId) {
          pid = info.pointId;
          seg.point_id = pid;   // 回写，后续下载直接用
        }
        if (info.startTime) {
          seg.exact_time = info.startTime;
          const d = new Date(info.startTime * 1000);
          const p2 = (n) => String(n).padStart(2, '0');
          seg.time_str = `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} `
            + `${p2(d.getHours())}:${p2(d.getMinutes())}`;
        }
      }
      if (!pid) throw new Error('无法获取 point_id');

      meta[hid] = await probeOne(seg, pid);
      ok++;
    } catch (e) {
      meta[hid] = { error: String(e.message || e).slice(0, 80) };
      fail++;
    }
    done++;
    // 每完成一个就吐一行 JSON，GUI 可逐条更新（流式）
    const entry = meta[hid];
    console.log('META ' + JSON.stringify({
      hash: hid,
      show_id: String(seg.show_id || ''),
      quality: entry.quality || '',
      bit_rate: entry.bit_rate || 0,
      est_size: entry.est_size || 0,
      error: entry.error || '',
      done,
      total: targets.length,
    }));
    // 每 10 个落一次盘，避免频繁 IO
    if (done % 10 === 0 || done === targets.length) {
      fs.writeFileSync(META_FILE, JSON.stringify(meta, null, 1));
    }
    await new Promise((r) => setTimeout(r, 40));
  }
}

await Promise.all(Array.from({ length: 6 }, worker));

fs.writeFileSync(META_FILE, JSON.stringify(meta, null, 1));
// point_id 回写
fs.writeFileSync(SEG_FILE, JSON.stringify(allSegs, null, 1));

console.log(`DONE ok=${ok} fail=${fail} 用时 ${((Date.now() - t0) / 1000).toFixed(0)}s`);
