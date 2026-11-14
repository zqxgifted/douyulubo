// SPDX-License-Identifier: MIT
// Copyright (c) 2026 douyu-vod-toolkit contributors
/**
 * 斗鱼录播公共接口封装（Node 侧）。
 *
 * 全部端点均为 v.douyu.com 的公开 wgapi，无需登录态；只需正常 User-Agent。
 * 取流签名函数会轮换，必须每次从播放页实时提取，不能硬编码。
 *
 * 归属说明：播放页签名脚本的提取方式（取倒数第二个 <script>）、CryptoJS.MD5
 * 注入、point_id+did+时间戳 的签名拼装，以及 B站弹幕 XML 的颜色映射与 <d p>
 * 字段结构，参考自 renmu123/douyu-video-cli 的 douyu-api（该仓库许可证声明存在
 * GPL-3.0 与子包 MIT 的冲突）。本文件为独立实现，未复制其源码；详见仓库根目录
 * THIRD_PARTY_NOTICES.md。
 */
import crypto from 'node:crypto';

// 斗鱼页面里的签名脚本会用到 CryptoJS.MD5，这里用 node:crypto 提供等价实现
globalThis.CryptoJS = {
  MD5: (s) => crypto.createHash('md5').update(String(s)).digest('hex'),
};

const API_SHOW_LIST = 'https://v.douyu.com/wgapi/vod/center/authorShowVideoList';
const API_REPLAY_LIST = 'https://v.douyu.com/wgapi/vod/center/getShowReplayList';
const API_STREAM = 'https://v.douyu.com/wgapi/vodnc/front/stream/getStreamUrlWeb';
const API_BARRAGE = 'https://v.douyu.com/wgapi/vod/center/getBarrageList';
const SHOW_PAGE = (hash) => `https://v.douyu.com/show/${hash}`;

function extractScripts(html) {
  const out = [];
  const re = /<script\b[^>]*>([\s\S]*?)<\/script>/g;
  let m;
  while ((m = re.exec(html)) !== null) out.push(m[1]);
  return out;
}

function firstFunctionName(js) {
  const names = [...String(js || '').matchAll(/function\s+([a-zA-Z0-9_]+)\(/g)].map((x) => x[1]);
  return names[0] || null;
}

/** 从播放页倒数第二个 <script> 里实时提取并载入签名函数，返回函数名。 */
export async function loadSigner(hash, ua) {
  const html = await (await fetch(SHOW_PAGE(hash), { headers: { 'User-Agent': ua } })).text();
  const scripts = extractScripts(html);
  const ds = scripts.at(-2) || '';
  const fn = firstFunctionName(ds);
  if (!fn) throw new Error('未能从播放页提取签名函数（页面结构可能已变更）');
  // 斗鱼签名脚本为页面内联 JS，需 eval 后调用；如站点结构变化，此处会报错
  globalThis.eval(ds);
  if (typeof globalThis[fn] !== 'function') throw new Error(`签名函数 ${fn} 未定义`);
  return fn;
}

/** 按 bit_rate 降序取最高画质。 */
export function pickTopStream(payload) {
  const tv = payload?.data?.thumb_video;
  const list = tv ? (Array.isArray(tv) ? tv : Object.values(tv)) : [];
  list.sort((a, b) => (b.bit_rate || 0) - (a.bit_rate || 0));
  return list[0] || null;
}

/**
 * 取某分段的最高画质 m3u8 地址。
 * @param {object} o { hash, pointId, did, ua, signFn }
 */
export async function getTopM3u8({ hash, pointId, did, ua, signFn }) {
  const body = `${globalThis[signFn](pointId, did, Math.floor(Date.now() / 1000))}&vid=${hash}`;
  const r = await fetch(API_STREAM, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': ua },
    body,
  });
  const j = JSON.parse(await r.text());
  if (j.error !== 0) throw new Error(`取流失败 error=${j.error} ${j.msg || ''}`);
  const top = pickTopStream(j);
  if (!top) throw new Error('取流成功但没有可用画质档位');
  return top;
}

// 清晰度档位 -> 匹配关键词（按顺序尝试）。与 src/anchor.py 的 QUALITY_ALIASES 保持一致。
const QUALITY_ALIASES = {
  highest: [],
  original: ['原画', '原畫', '1080p60', '1440p'],
  '1080p': ['1080', '原画', '高清 1080'],
  '720p': ['720', 'high', '高清'],
  '540p': ['540'],
  '480p': ['480', 'normal', '标清'],
  '360p': ['360', 'low', '流畅'],
  audio: ['audio', '音频', '纯音频'],
};

function matchQuality(opts, quality) {
  const q = String(quality || 'highest').trim().toLowerCase();
  if (q === '' || q === 'highest' || q === '最高') return { picked: opts[0], exact: true };

  const aliases = QUALITY_ALIASES[q] || [];
  for (const alias of aliases) {
    const hit = opts.find((o) => String(o.name || '').toLowerCase().includes(alias.toLowerCase()));
    if (hit) return { picked: hit, exact: true };
  }
  const num = Number(q);
  if (Number.isFinite(num)) {
    const byRate = opts.find((o) => Number(o.bit_rate) === num);
    if (byRate) return { picked: byRate, exact: true };
  }
  const direct = opts.find((o) => String(o.name || '').toLowerCase().includes(q));
  if (direct) return { picked: direct, exact: true };
  return { picked: opts[0], exact: false };
}

/**
 * 取指定画质档位。quality 取值见 QUALITY_ALIASES：
 *   highest（默认）/ original / 1080p / 720p / 540p / 480p / 360p / audio
 *   也接受具体 bit_rate 数字或画质名片段
 * 找不到时回落到最高档并明确提示，绝不静默下错清晰度。
 */
export async function getStreamByQuality({ hash, pointId, did, ua, signFn, quality = 'highest' }) {
  const opts = await getQualityOptions({ hash, pointId, did, ua, signFn });
  if (opts.length === 0) throw new Error('没有可用画质档位');
  const { picked, exact } = matchQuality(opts, quality);
  if (!exact) {
    const avail = opts.map((o) => `${o.name}(${o.bit_rate})`).join(', ');
    console.error(`[quality] 未找到档位 "${quality}"，回落到最高画质 ${opts[0].name}。可用档位: ${avail}`);
  }
  return picked;
}

/** 返回全部画质档位（{name, bit_rate, url} 数组，已按码率降序）。 */
export async function getQualityOptions({ hash, pointId, did, ua, signFn }) {
  const body = `${globalThis[signFn](pointId, did, Math.floor(Date.now() / 1000))}&vid=${hash}`;
  const r = await fetch(API_STREAM, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': ua },
    body,
  });
  const j = JSON.parse(await r.text());
  if (j.error !== 0) throw new Error(`取流失败 error=${j.error} ${j.msg || ''}`);
  const tv = j?.data?.thumb_video;
  const list = tv ? (Array.isArray(tv) ? tv : Object.values(tv)) : [];
  list.sort((a, b) => (b.bit_rate || 0) - (a.bit_rate || 0));
  return list.map((s) => ({
    name: s.name || s.stream_name || '',
    bit_rate: s.bit_rate || 0,
    stream_type: s.stream_type ?? null,
    url: s.url || '',
  }));
}

/** 解析 media playlist，返回分片 URL 与时长数组。master playlist 会抛错。 */
export function parsePlaylist(text, baseUrl) {
  if (text.includes('#EXT-X-STREAM-INF')) throw new Error('master playlist（需再取下一层）');
  const lines = text.split('\n').map((s) => s.trim()).filter(Boolean);
  const base = new URL(baseUrl);
  const urls = lines.filter((l) => !l.startsWith('#')).map((s) => new URL(s, base).href);
  const durations = lines
    .filter((l) => l.startsWith('#EXTINF'))
    .map((l) => parseFloat(l.split(':')[1]));
  return { urls, durations };
}

/** 分页拉取某分段的全部弹幕并去重。 */
export async function fetchDanmaku(hash, durationSec, ua, { maxWindows = 60, pauseMs = 120 } = {}) {
  const items = [];
  let start = 0;
  const end = Math.max(1, Math.floor(durationSec * 1000));
  for (let w = 0; w < maxWindows; w++) {
    const u = `${API_BARRAGE}?` + new URLSearchParams({
      vid: hash, start_time: String(start), end_time: String(end),
    });
    const r = await fetch(u, { headers: { 'User-Agent': ua } });
    const d = JSON.parse(await r.text());
    const lst = d?.data?.list || [];
    items.push(...lst);
    if (lst.length < 500) break;
    const tls = lst.map((x) => parseInt(x.tl || 0, 10));
    const next = Math.max(...tls) + 1;
    if (!Number.isFinite(next) || next <= start) break;
    start = next;
    if (pauseMs) await new Promise((r2) => setTimeout(r2, pauseMs));
  }
  const seen = new Set();
  const uniq = [];
  for (const x of items) {
    const k = `${x.uid}|${x.sts}|${x.ctt}`;
    if (seen.has(k)) continue;
    seen.add(k);
    uniq.push(x);
  }
  return uniq;
}

/** 生成 B 站格式 XML 弹幕。 */
export function toBilibiliXml(items, meta = {}) {
  const COLOR = {
    0: 0xFFFFFF, 7: 0xFF5654, 8: 0xFF7523, 9: 0xFE69B3,
    10: 0xFFBC00, 11: 0x78C946, 12: 0x9E7FFF, 13: 0x3D9BFF,
  };
  const esc = (t) => String(t ?? '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  const lines = ['<?xml version="1.0" encoding="utf-8"?>', '<i>', '  <metadata>'];
  for (const [k, v] of Object.entries(meta)) {
    if (v !== undefined && v !== null && v !== '') lines.push(`    <${k}>${esc(v)}</${k}>`);
  }
  lines.push('  </metadata>');
  for (const x of items) {
    const tl = Math.floor(parseInt(x.tl || 0, 10) / 1000);
    const color = COLOR[x.col] ?? 0xFFFFFF;
    const p = [tl, 1, 25, color, parseInt(x.sts || 0, 10), 0, x.mid || '', x.uid || '', 0].join(',');
    lines.push(`  <d p="${p}">${esc(x.ctt)}</d>`);
  }
  lines.push('</i>');
  return lines.join('\n');
}

export { API_SHOW_LIST, API_REPLAY_LIST, SHOW_PAGE };
