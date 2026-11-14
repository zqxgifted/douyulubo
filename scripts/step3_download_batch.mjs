#!/usr/bin/env node
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 douyulubo contributors
/**
 * 批量下载：以「分段」为单位（一个分段 = 一个视频文件 = 唯一标识 hash_id）。
 *
 * 数据来源优先级：
 *   1. data/segments_index.json  （推荐，884 段级）
 *   2. data/download_list.json   （旧格式，兼容）
 *
 * 特性：N 并发、断点续传、SPEED 显示、磁盘守门、失败清单、已下载跳过。
 *
 * 用法：
 *   DOUYU_CONFIG=config.json node scripts/step3_download_batch.mjs [--only <hashes.json>]
 */
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

import { loadConfig } from '../src/config.mjs';
import { alreadyDownloaded } from '../src/history.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const SEG_SCRIPT = path.join(HERE, 'step3_download_seg.mjs');
const cfg = loadConfig();
cfg.ensureDirs();

// ---- 读分段清单 ----
const segFile = path.join(cfg.dataDir, 'segments_index.json');
const dlFile = path.join(cfg.dataDir, 'download_list.json');

let items = [];
let source = '';
if (fs.existsSync(segFile)) {
  const segs = JSON.parse(fs.readFileSync(segFile, 'utf8'));
  items = segs.map((s) => ({
    hash: s.hash_id,
    file: `${sanitize(s.title || s.hash_id)}.mp4`,
    folder: s.folder || '',
    title: s.title || '',
    duration_sec: s.duration_sec || 0,
    seg_no: s.seg_no || 1,
    seg_total: s.seg_total || 1,
    time_str: s.time_str || '',
  }));
  source = 'segments_index.json';
} else if (fs.existsSync(dlFile)) {
  items = JSON.parse(fs.readFileSync(dlFile, 'utf8'));
  source = 'download_list.json';
} else {
  console.error(`缺少 ${segFile} 或 ${dlFile}，请先运行 list_shows.py`);
  process.exit(1);
}

function sanitize(name) {
  return String(name || '').replace(/[\\/:*?"<>|]/g, '_').trim().slice(0, 150) || 'unnamed';
}

// --only 只下指定的 hash
const oi = process.argv.indexOf('--only');
if (oi > 0 && process.argv[oi + 1]) {
  try {
    const wanted = new Set(JSON.parse(fs.readFileSync(process.argv[oi + 1], 'utf8')).map(String));
    items = items.filter((x) => wanted.has(String(x.hash)));
  } catch (e) {
    console.error(`读取 --only 失败: ${e.message}`);
    process.exit(2);
  }
}

const FAILED = path.join(cfg.downloadDir, '_failed.txt');
const concurrency = Math.max(1, cfg.concurrent);

console.log(`数据来源: ${source}`);
console.log(`=== 共 ${items.length} 个分段，${concurrency} 个任务并发，`
  + `每个任务 ${cfg.workersPerTask} 个分片并发 ===`);
console.log(`输出目录: ${cfg.downloadDir}`);

const env = { ...process.env, TMP: cfg.tmpDir, TEMP: cfg.tmpDir };

function diskFreeBytes(dir) {
  try {
    const st = fs.statSync ? fs.statfsSync(dir, { bigint: true }) : null;
    const size = st.frsize ?? st.bsize ?? 4096n;
    return Number(st.bavail * size);
  } catch {
    return Number.POSITIVE_INFINITY;
  }
}

const MIN_FREE = 10 * 1024 * 1024 * 1024;

function runOne(it) {
  return new Promise((resolve) => {
    const out = path.join(cfg.downloadDir, it.file);
    const done = (code) => resolve(code);

    // ① 历史记录里已完成
    try {
      if (alreadyDownloaded(cfg.workDir, it.hash, out, 100 * 1024 * 1024)) {
        console.log(`SKIP(已下载) ${it.file}`);
        return done(0);
      }
    } catch { /* 忽略 */ }

    // ② 文件已存在且够大
    try {
      if (fs.existsSync(out) && fs.statSync(out).size > 100 * 1024 * 1024) {
        console.log(`SKIP(已存在) ${it.file}`);
        return done(0);
      }
    } catch { /* 继续 */ }

    const tag = it.seg_total > 1 ? `[${it.seg_no}/${it.seg_total}]` : '';
    console.log(`--- 开始 ${tag} ${it.file}`);
    const t0 = Date.now();

    let child;
    try {
      // 用 pipe 而不是 inherit：GUI 下子进程无控制台，inherit 会写非法句柄
      child = spawn(process.execPath,
        [SEG_SCRIPT, it.hash, out,
         '--duration', String(it.duration_sec || 0),
         '--air-time', String(it.time_str || '')],
        { cwd: cfg.workDir, env, stdio: ['ignore', 'pipe', 'pipe'] });
    } catch (e) {
      console.error(`  !! 启动失败 ${it.file}: ${e.message}`);
      try { fs.appendFileSync(FAILED, `${it.hash}\t${it.file}\trc=spawn-error\n`); } catch { /**/ }
      return done(1);
    }

    const pump = (stream) => (buf) => {
      try { if (stream.writable) stream.write(buf); } catch { /**/ }
    };
    child.stdout.on('data', pump(process.stdout));
    child.stderr.on('data', pump(process.stderr));

    let settled = false;
    child.on('error', (e) => {
      if (settled) return;
      settled = true;
      console.error(`  !! 子进程异常 ${it.file}: ${e.message}`);
      try { fs.appendFileSync(FAILED, `${it.hash}\t${it.file}\trc=spawn-error\n`); } catch { /**/ }
      done(1);
    });

    child.on('close', (rc) => {
      if (settled) return;
      settled = true;
      const sec = ((Date.now() - t0) / 1000).toFixed(0);
      if (rc !== 0) {
        try { fs.appendFileSync(FAILED, `${it.hash}\t${it.file}\trc=${rc}\n`); } catch { /**/ }
        console.log(`  !! 失败 rc=${rc} 用时 ${sec}s`);
      } else {
        try {
          const mb = fs.statSync(out).size / 1048576;
          console.log(`  ✔ 完成 ${mb.toFixed(0)}MB / ${sec}s`);
        } catch { /**/ }
      }
      done(rc ?? 1);
    });
  });
}

(async () => {
  let idx = 0, failed = 0, done = 0;
  const total = items.length;
  const t0 = Date.now();

  async function worker() {
    while (true) {
      const i = idx++;
      if (i >= total) break;
      const free = diskFreeBytes(cfg.workDir);
      if (free < MIN_FREE) {
        console.error(`!!! 工作盘剩余 ${(free / 1024 ** 3).toFixed(1)}GB < 10GB，中止`);
        break;
      }
      failed += (await runOne(items[i])) !== 0 ? 1 : 0;
      done++;
      const el = (Date.now() - t0) / 1000;
      const eta = done ? el / done * (total - done) : 0;
      console.log(`=== 进度 ${done}/${total}  失败 ${failed}  `
        + `用时 ${(el / 60).toFixed(1)}min  ETA ${(eta / 60).toFixed(1)}min ===`);
    }
  }

  await Promise.all(Array.from({ length: concurrency }, worker));
  console.log(`\n全部完成：成功 ${done - failed}，失败 ${failed}`);
  if (failed) console.log(`失败清单：${FAILED}`);

  // Windows 上如果 stdout 管道还有待写数据就退出，进程会以 0xC0000409 结束，
  // GUI 会误判成崩溃。这里先冲刷再设退出码，最后自然结束。
  process.exitCode = failed ? 1 : 0;
  await new Promise((r) => setTimeout(r, 200));
})();
