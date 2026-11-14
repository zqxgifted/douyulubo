// SPDX-License-Identifier: MIT
// Copyright (c) 2026 douyu-vod-toolkit contributors
/**
 * 下载历史（Node 侧，与 src/history.py 共用同一套文件格式）。
 * 每场一个 JSON：<work_dir>/data/history/<hash>.json，天然支持并发写。
 */
import fs from 'node:fs';
import path from 'node:path';

export function historyDir(workDir) {
  return path.join(workDir, 'data', 'history');
}

function safe(hash) {
  return String(hash).replace(/[^A-Za-z0-9_\-]/g, '_').slice(0, 120);
}

export function recordPath(workDir, hash) {
  return path.join(historyDir(workDir), `${safe(hash)}.json`);
}

export function alreadyDownloaded(workDir, hash, file, minSize = 1) {
  const p = recordPath(workDir, hash);
  if (!fs.existsSync(p)) return false;
  try {
    const rec = JSON.parse(fs.readFileSync(p, 'utf8'));
    const f = rec.file;
    if (!f) return false;
    const fp = path.isAbsolute(f) ? f : path.join(workDir, f);
    return fs.existsSync(fp) && fs.statSync(fp).size >= minSize;
  } catch {
    return false;
  }
}

export function markDownloaded(workDir, rec) {
  const d = historyDir(workDir);
  fs.mkdirSync(d, { recursive: true });
  const out = { ...rec, finished_at: rec.finished_at || new Date().toISOString() };
  fs.writeFileSync(recordPath(workDir, out.hash || 'unknown'), JSON.stringify(out, null, 1));
}

export function listAll(workDir) {
  const d = historyDir(workDir);
  if (!fs.existsSync(d)) return [];
  return fs.readdirSync(d)
    .filter((f) => f.endsWith('.json'))
    .map((f) => {
      try { return JSON.parse(fs.readFileSync(path.join(d, f), 'utf8')); }
      catch { return null; }
    })
    .filter(Boolean)
    .sort((a, b) => String(b.finished_at || '').localeCompare(String(a.finished_at || '')));
}
