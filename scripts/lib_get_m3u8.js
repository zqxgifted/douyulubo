#!/usr/bin/env node
// SPDX-License-Identifier: MIT
/** 打印某分段最高画质 m3u8 地址（调试 / 交给 ffmpeg 直拉用）。
 *
 * 用法：DOUYU_CONFIG=/path/to/config.json node scripts/lib_get_m3u8.js <hash_id>
 */
import fs from 'node:fs';
import path from 'node:path';

import { loadConfig } from '../src/config.mjs';
import { loadSigner, getTopM3u8 } from '../src/douyu.mjs';

const cfg = loadConfig();
const vid = process.argv[2];
if (!vid) {
  console.error('用法: node scripts/lib_get_m3u8.js <hash_id>');
  process.exit(1);
}
const probeFile = path.join(cfg.dataDir, 'probe_input.json');
if (!fs.existsSync(probeFile)) {
  console.error(`缺少 ${probeFile}，请先运行 step2_fetch_detail.py`);
  process.exit(1);
}
const it = JSON.parse(fs.readFileSync(probeFile, 'utf8')).find((x) => x.hash === vid);
if (!it) { console.error(`hash ${vid} 不在 probe_input.json`); process.exit(1); }

(async () => {
  const signFn = await loadSigner(vid, cfg.ua);
  const top = await getTopM3u8({ hash: vid, pointId: it.point_id, did: cfg.did, ua: cfg.ua, signFn });
  process.stdout.write(top.url);
})().catch((e) => { console.error(e.message); process.exit(2); });
