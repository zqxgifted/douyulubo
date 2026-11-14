// SPDX-License-Identifier: MIT
// Copyright (c) 2026 douyu-vod-toolkit contributors
/**
 * 统一配置加载（Node 侧）。不含任何真实账号、设备号或本机路径。
 *
 * 优先级：DOUYU_CONFIG 指定的 JSON > 当前目录 config.json > DOUYU_* 环境变量 > 默认值
 * up_id / work_dir 为必填，缺失时直接退出，不回落到任何真实主播。
 * did 缺省时随机生成 32 位 hex。
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import crypto from 'node:crypto';

const DEFAULT_UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36';

const PLACEHOLDERS = new Set(['', '<UP_ID>', 'REPLACE_WITH_UP_ID', 'YOUR_UP_ID', 'xxx']);

const DEFAULTS = {
  concurrent: 2,
  ffmpeg: 'ffmpeg',
  danmaku_factory: '',
  ua: DEFAULT_UA,
  did: '',
  workers_per_task: 8,
  min_file_mb: 100,
  anchor_name: '',
  quality: 'highest',
  danmaku_mode: 'ass',
};

const ENV_KEYS = {
  up_id: 'DOUYU_UP_ID',
  work_dir: 'DOUYU_WORK_DIR',
  ffmpeg: 'DOUYU_FFMPEG',
  danmaku_factory: 'DOUYU_DANMAKU_FACTORY',
  ua: 'DOUYU_UA',
  did: 'DOUYU_DID',
  concurrent: 'DOUYU_CONCURRENT',
  workers_per_task: 'DOUYU_WORKERS_PER_TASK',
  min_file_mb: 'DOUYU_MIN_FILE_MB',
  anchor_name: 'DOUYU_ANCHOR_NAME',
  quality: 'DOUYU_QUALITY',
  danmaku_mode: 'DOUYU_DANMAKU_MODE',
};

const INT_KEYS = new Set(['concurrent', 'workers_per_task', 'min_file_mb']);

function die(msg) {
  console.error(`[config] ${msg}`);
  process.exit(2);
}

// 项目根目录：本文件在 src/ 下，上一级是根
const PROJECT_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function readOne(p) {
  try {
    if (!fs.existsSync(p)) return {};
    let text = fs.readFileSync(p, 'utf8');
    if (text.charCodeAt(0) === 0xFEFF) text = text.slice(1); // 兼容 BOM
    const data = JSON.parse(text);
    if (!data || typeof data !== 'object' || Array.isArray(data)) return {};
    // 下划线开头的键是注释，忽略
    const out = {};
    for (const [k, v] of Object.entries(data)) {
      if (!k.startsWith('_')) out[k] = v;
    }
    return out;
  } catch (e) {
    console.error(`[config] 无法读取 ${p}: ${e.message}`);
    return {};
  }
}

function readFileCfg() {
  // 后者覆盖前者
  const merged = {};
  Object.assign(merged, readOne(path.join(PROJECT_ROOT, 'config', 'defaults.json')));
  Object.assign(merged, readOne(path.join(PROJECT_ROOT, 'config', 'user.json')));
  if (process.env.DOUYU_CONFIG) {
    Object.assign(merged, readOne(process.env.DOUYU_CONFIG));
  }
  // 兼容旧位置（优先级最高）
  Object.assign(merged, readOne(path.join(PROJECT_ROOT, 'config.json')));
  return merged;
}

export function loadConfig() {
  const merged = { ...DEFAULTS };
  const fileCfg = readFileCfg();
  for (const [k, v] of Object.entries(fileCfg)) {
    if (v !== null && v !== undefined) merged[k] = v;
  }
  for (const [k, env] of Object.entries(ENV_KEYS)) {
    const v = process.env[env];
    if (v !== undefined && v !== '') merged[k] = v;
  }
  for (const k of INT_KEYS) {
    const n = parseInt(merged[k], 10);
    merged[k] = Number.isFinite(n) ? n : DEFAULTS[k];
  }

  const upId = String(merged.up_id ?? '').trim();
  const workDir = String(merged.work_dir ?? '').trim();
  if (PLACEHOLDERS.has(upId)) {
    die('缺少 up_id：请在 config/user.json 填写，或设置 DOUYU_UP_ID。\n' +
        'up_id 是主播录播页 https://v.douyu.com/author/<up_id> 里那段 ID。');
  }
  let finalWorkDir = workDir;
  if (PLACEHOLDERS.has(workDir) || workDir === '.' || workDir === '..') {
    // 留空时用默认目录：项目根（src/ 的上一级）下的 downloads
    const here = path.dirname(fileURLToPath(import.meta.url));
    finalWorkDir = path.join(path.dirname(here), 'downloads');
  }

  let did = String(merged.did ?? '').trim();
  if (!did) did = crypto.randomBytes(16).toString('hex');

  const root = path.resolve(finalWorkDir);
  const cfg = {
    upId,
    workDir: root,
    dataDir: path.join(root, 'data'),
    downloadDir: path.join(root, 'downloads'),
    danmakuDir: path.join(root, 'danmaku'),
    danmakuAssDir: path.join(root, 'danmaku_ass'),
    tmpDir: path.join(root, 'tmp'),
    concurrent: merged.concurrent,
    ffmpeg: String(merged.ffmpeg),
    danmakuFactory: String(merged.danmaku_factory),
    ua: String(merged.ua),
    did,
    workersPerTask: merged.workers_per_task,
    minFileMb: merged.min_file_mb,
    // 开启自动转码时，下载脚本保留 ts 分片交给转码阶段合并
    transcodeEnabled: merged.transcode_enabled === true
      || String(merged.transcode_enabled).toLowerCase() === 'true',
    transcodeCodec: String(merged.transcode_codec || 'h265'),
    transcodeSuffix: String(merged.transcode_suffix || ''),
    anchorName: String(merged.anchor_name),
    quality: String(merged.quality),
    danmakuMode: String(merged.danmaku_mode),
  };
  cfg.headers = () => ({ 'User-Agent': cfg.ua });
  cfg.ensureDirs = () => {
    for (const d of [cfg.dataDir, cfg.downloadDir, cfg.danmakuDir, cfg.danmakuAssDir, cfg.tmpDir]) {
      fs.mkdirSync(d, { recursive: true });
    }
  };
  return cfg;
}
