#!/usr/bin/env node
// SPDX-License-Identifier: MIT
/**
 * Step 3 — 单场下载核心：实时签名取最高画质 m3u8 → 分片并发/断点续跑 → 拼接 → ffmpeg 转封装。
 *
 * 用法：
 *   DOUYU_CONFIG=/path/to/config.json node scripts/step3_download_seg.mjs <hash_id> <输出.mp4>
 *
 * 退出码：0 成功 / 1 参数或配置错 / 2 取流失败 / 3 master playlist / 4 分片缺失 / 5 输出过小
 *
 * 前置：step2 生成的 data/probe_input.json 里必须有该 hash 的 point_id。
 * 注意：不要拿新下载的文件去替换旧的母版文件 —— 老 VOD 的现行 m3u8 可能比原始短。
 */
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';

import { loadConfig } from '../src/config.mjs';
import { loadSigner, getStreamByQuality, parsePlaylist } from '../src/douyu.mjs';
import { markDownloaded, alreadyDownloaded } from '../src/history.mjs';

const cfg = loadConfig();
cfg.ensureDirs();

const [hash, outAbs] = process.argv.slice(2);
if (!hash || !outAbs) {
  console.error('用法: node scripts/step3_download_seg.mjs <hash_id> <输出.mp4>');
  process.exit(1);
}

const probeFile = path.join(cfg.dataDir, 'probe_input.json');
if (!fs.existsSync(probeFile)) {
  console.error(`缺少 ${probeFile}，请先运行 step2_fetch_detail.py`);
  process.exit(1);
}
const input = JSON.parse(fs.readFileSync(probeFile, 'utf8'));
const it = input.find((x) => x.hash === hash);
if (!it || it.point_id === undefined || it.point_id === null) {
  console.error(`hash ${hash} 不在 probe_input.json 或缺少 point_id`);
  process.exit(1);
}

// 0. 下载历史：同一个录播已下载过就直接提示并跳过
if (alreadyDownloaded(cfg.workDir, hash, outAbs)) {
  console.log(`SKIP(已下载) ${hash} —— 历史记录里已完成，需要重下请删除 data/history/${hash}.json`);
  process.exit(0);
}

// 1. 实时抓签名 → 按 config.quality 选画质（默认最高）
const signFn = await loadSigner(hash, cfg.ua);
const top = await getStreamByQuality({
  hash, pointId: it.point_id, did: cfg.did, ua: cfg.ua, signFn, quality: cfg.quality,
});
console.error(`画质: ${top.name || '-'} bit_rate=${top.bit_rate || '-'} (选择=${cfg.quality})`);

// 2. 解析分片清单
const pl = await (await fetch(top.url, { headers: cfg.headers() })).text();
let { urls: segUrls } = parsePlaylist(pl, top.url);
console.error(`分片数: ${segUrls.length}`);

// 3. 并发下载缺失分片（>10KB 视为已存在，支持断点续跑）
// 临时分片目录放在系统 TEMP（纯 ASCII 路径）：
// 中文路径下 mkdirSync + fs 操作在部分 Windows 环境会直接崩溃（0xC0000409）。
const _tmpRoot = process.env.TEMP || process.env.TMP || os.tmpdir();
const _tag = crypto.createHash('md5').update(outAbs).digest('hex').slice(0, 12);
const segDir = path.join(_tmpRoot, 'douyulubo-seg-' + _tag);
fs.mkdirSync(segDir, { recursive: true });
const segPath = (i) => path.join(segDir, `segment${String(i).padStart(5, '0')}.ts`);

async function fetchSeg(i) {
  const p = segPath(i);
  for (let a = 0; a < 4; a++) {
    try {
      if (fs.existsSync(p) && fs.statSync(p).size > 10240) return true;
      const r = await fetch(segUrls[i], { headers: cfg.headers() });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      // 流式落盘：避免大分片一次性读进内存
      if (!r.body) throw new Error("no body");
      const tmp = p + ".part";
      await new Promise((resolve, reject) => {
        const ws = fs.createWriteStream(tmp);
        const reader = r.body.getReader();
        const pump = () => reader.read().then(({ done, value }) => {
          if (done) { ws.end(); return; }
          if (!ws.write(Buffer.from(value))) ws.once("drain", pump);
          else pump();
        }).catch(reject);
        ws.on("finish", resolve);
        ws.on("error", reject);
        pump();
      });
      const sz = fs.statSync(tmp).size;
      if (sz < 1024) { fs.rmSync(tmp, { force: true }); throw new Error("too small"); }
      fs.renameSync(tmp, p);
      return true;
    } catch (e) {
      if (a === 3) { console.error(`  分片${i} 失败: ${e.message}`); return false; }
      await new Promise((r) => setTimeout(r, 1500 * (a + 1)));
    }
  }
  return false;
}

const missing = [];
for (let i = 0; i < segUrls.length; i++) {
  if (!fs.existsSync(segPath(i)) || fs.statSync(segPath(i)).size <= 10240) missing.push(i);
}
console.error(`已存在 ${segUrls.length - missing.length}，需下载 ${missing.length}`);

let doneCnt = 0;
const queue = [...missing];
const t0 = Date.now();
async function worker() {
  while (queue.length) {
    const i = queue.shift();
    const ok = await fetchSeg(i);
    doneCnt++;
    if (doneCnt % 50 === 0 || !ok) {
      console.error(`  ${doneCnt}/${missing.length} ${ok ? '' : '(含失败)'} ${((Date.now() - t0) / 1000).toFixed(0)}s`);
    }
  }
}
await Promise.all(Array.from({ length: cfg.workersPerTask }, worker));

const stillMissing = [];
for (let i = 0; i < segUrls.length; i++) {
  if (!fs.existsSync(segPath(i)) || fs.statSync(segPath(i)).size <= 10240) stillMissing.push(i);
}
if (stillMissing.length) {
  console.error(`仍有 ${stillMissing.length} 个分片缺失: ${stillMissing.slice(0, 10).join(',')}`);
  process.exit(4);
}

// 4. 二进制拼接（TS 可顺序拼接；大小不符时重建）
const mergedTs = path.join(segDir, 'output.ts');
const expectTotal = segUrls.reduce((a, _, i) => a + fs.statSync(segPath(i)).size, 0);
const cur = fs.existsSync(mergedTs) ? fs.statSync(mergedTs).size : -1;
if (Math.abs(cur - expectTotal) > 1024) {
  fs.rmSync(mergedTs, { force: true });
  const ws = fs.createWriteStream(mergedTs);
  for (let i = 0; i < segUrls.length; i++) {
    const buf = fs.readFileSync(segPath(i));
    if (!ws.write(buf)) await new Promise((r) => ws.once('drain', r));
  }
  await new Promise((r) => ws.end(r));
}
console.error(`拼接完成: ${(fs.statSync(mergedTs).size / 1048576).toFixed(0)}MB`);

// 5. ffmpeg 转封装
fs.mkdirSync(path.dirname(path.resolve(outAbs)), { recursive: true });
execFileSync(cfg.ffmpeg, ['-y', '-i', mergedTs, '-c', 'copy', '-bsf:a', 'aac_adtstoasc', outAbs],
  { stdio: ['ignore', 'ignore', 'ignore'] });
const sz = fs.statSync(outAbs).size;
console.error(`DONE ${outAbs} ${(sz / 1048576).toFixed(0)}MB 用时${((Date.now() - t0) / 60000).toFixed(1)}min`);

// 6. 输出过小判定：可按配置关闭。超短场次（如 488 秒 / 25MB）是完全正常的，
//    正确做法是 ffprobe 核时长对比 raw_detail.duration_sec，而不是按固定 MB 阈值拒绝。
const minBytes = cfg.minFileMb > 0 ? cfg.minFileMb * 1048576 : 0;
// 时长来源优先级：命令行 --duration > 分段索引
const _ai = process.argv.indexOf('--air-time');
if (_ai > 0) it.time_str = process.argv[_ai + 1] || it.time_str || '';

const _di = process.argv.indexOf('--duration');
const _durArg = _di > 0 ? Number(process.argv[_di + 1] || 0) : 0;
const _dur = _durArg || Number(it.duration_sec || 0);

if (minBytes && sz < minBytes) {
  const knownShort = _dur > 0 && _dur < 900;
  if (!knownShort) {
    console.error(`文件过小 (${(sz / 1048576).toFixed(0)}MB < ${cfg.minFileMb}MB)，视为失败；` +
                  '若为短场次请设 min_file_mb=0 或用 ffprobe 核时长');
    process.exit(5);
  }
}

// 7. 分片目录保留，交给 merge_ts 合并转码后再清理。
//    若配置里没开自动转码，则在这里直接删掉（节省空间）。
if (cfg.transcodeEnabled) {
  console.error(`KEEP_TS ${segDir}`);
  // 把分片目录位置写进历史记录，供转码阶段使用
  try {
    const p = path.join(cfg.dataDir, 'pending_ts.json');
    let m = {};
    try { m = JSON.parse(fs.readFileSync(p, 'utf8')); } catch { /* 新建 */ }
    m[hash] = { dir: segDir, out: outAbs };
    fs.writeFileSync(p, JSON.stringify(m, null, 1));
  } catch (e) {
    console.error(`WARN 记录分片目录失败: ${e.message}`);
  }
} else {
  for (let a = 0; a < 4; a++) {
    try { fs.rmSync(segDir, { recursive: true, force: true }); break; }
    catch { await new Promise((r) => setTimeout(r, 2000)); }
  }
  console.error('CLEANED');
}

// 8. 写入下载历史（供 GUI「下载管理/历史」页与重复检测使用）
markDownloaded(cfg.workDir, {
  hash,
  title: it.title || '',
  folder: it.folder || '',
  // 录播时间（下载管理页「录播时间」列用）
  air_time: String(it.time_str || it.airTime || it.date || ''),
  file: path.resolve(outAbs),
  size: sz,
  duration_sec: _dur,
  quality: top.name || '',
  bit_rate: Number(top.bit_rate || 0),
  danmaku_mode: cfg.danmakuMode,
  source: 'douyu-vod-toolkit',
});
console.log(`HISTORY: 已记录 ${hash}`);

// Windows 下管道未排空就退出会让进程以 0xC0000409 结束（GUI 误判为崩溃）。
// 这里显式设退出码，并给 stdout 一个刷新机会再自然结束。
process.exitCode = 0;
await new Promise((r) => setTimeout(r, 120));
