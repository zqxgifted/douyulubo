#!/usr/bin/env node
// SPDX-License-Identifier: MIT
// Copyright (c) 2026 douyu-vod-toolkit contributors
/**
 * douyu-vod-toolkit 统一命令入口。
 *
 * 用法：
 *   node douyu.mjs <command> [options]
 *   node douyu.mjs --help
 *
 * 设计原则：
 *  - 只做「参数解析 + 调度」，实际逻辑全在 scripts/ 与 src/ 里，便于单独调用
 *  - 所有路径都相对于本文件，不依赖 cwd，也不写死任何本机路径
 *  - 子进程继承环境变量；DOUYU_CONFIG 可用 --config 覆盖
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { loadConfig } from '../src/config.mjs';
import { listAll, historyDir } from '../src/history.mjs';

// 本文件位于 core/ 下，项目根是它的上一层
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const S = (f) => path.join(ROOT, 'scripts', f);

// 自包含 exe 里没有独立的 python.exe：用 --run-py 让打包进去的解释器跑脚本。
// GUI/命令行可通过 DOUYU_PY 指定解释器：
//   · 指向 douyulubo.exe（打包版）→ 需要 --run-py
//   · 指向 python.exe / pythonw.exe → 普通解释器，直接跑脚本
const PY = process.env.DOUYU_PY || 'python';

/** 判断 PY 是不是我们打包的 exe（需要 --run-py 参数）。 */
function isBundledExe(exePath) {
  if (!exePath || exePath === 'python' || exePath === 'python3') return false;
  const base = path.basename(String(exePath)).toLowerCase();
  if (base.startsWith('python')) return false;   // python.exe / pythonw.exe
  if (base === 'py.exe' || base === 'py') return false;
  // 其余情况视为打包的 douyulubo.exe
  return true;
}

const USE_RUN_PY = isBundledExe(PY);

const pyArgs = (f, extra = []) => (USE_RUN_PY
  ? [PY, ['--run-py', f, ...extra]]
  : [PY, [f, ...extra]]);

const COMMANDS = {
  init: {
    desc: '把示例配置复制为 config.json（不覆盖已有文件）',
    run: () => {
      const src = path.join(ROOT, 'examples', 'config.example.json');
      const dst = path.join(ROOT, 'config.json');
      if (fs.existsSync(dst)) { console.log('config.json 已存在，未改动。'); return 0; }
      fs.copyFileSync(src, dst);
      console.log('已创建 config.json —— 请填写 up_id 与 work_dir 后再跑其它命令。');
      return 0;
    },
  },
  run: {
    desc: '一键跑完整流程：fetch → detail → download → danmaku → probe（可加 --skip-* 跳过）',
    args: '[--skip-download] [--skip-danmaku] [--skip-probe]',
    run: (o) => runPipeline(o),
  },
  fetch: { desc: 'Step1 抓全部场次与分段', cmd: () => pyArgs(S('step1_fetch_list.py')) },
  shows: {
    desc: '只抓场次索引（含总数），速度快，供 GUI 搜索结果页使用',
    args: '[--quiet] [--json-out FILE]',
    run: (o) => {
      const [b, a] = pyArgs(S('list_shows.py'));
      return call(b, [...a, ...(o.quiet ? ['--quiet'] : [])], o);
    },
  },
  detail: {
    desc: 'Step2 抓分段详情并生成下载清单',
    args: '[--only <hashes.json>]  只抓指定场次',
    cmd: (o) => {
      const [b, a] = pyArgs(S('step2_fetch_detail.py'));
      return [b, [...a, ...(o.only ? ['--only', String(o.only)] : [])]];
    },
  },
  download: {
    desc: 'Step3 批量下载（默认 2 并发）',
    args: '[--only <hashes.json>] 只下指定分段；[--hash <id> --out <file>] 单场',
    run: (o) => {
      if (o.hash) {
        if (!o.out) { console.error('单场模式需要 --out <输出.mp4>'); return 2; }
        return call('node', [S('step3_download_seg.mjs'), o.hash, o.out], o);
      }
      const extra = o.only ? ['--only', String(o.only)] : [];
      return call('node', [S('step3_download_batch.mjs'), ...extra], o);
    },
  },
  danmaku: {
    desc: 'Step4 抓取弹幕 XML（--limit N 可先试几场）',
    cmd: (o) => pyArgs(S('step4_pull_danmaku.py'), o.limit ? ['--limit', String(o.limit)] : []),
  },
  ass: {
    desc: '工具：XML → ASS（内置纯 Python 实现，默认；--backend 可切外部）',
    cmd: (o) => pyArgs(S('util_convert_danmaku_ass.py'), [
      ...(o.limit ? ['--limit', String(o.limit)] : []),
      ...(o.backend ? ['--backend', String(o.backend)] : []),
    ]),
  },
  'probe-meta': {
    desc: '探测每个分段的最高清晰度与预计大小（只读元数据，不下载）',
    args: '[--limit N]',
    run: (o) => {
      const script = S('probe_segments.mjs');
      const extra = o.limit ? ['--limit', String(o.limit)] : [];
      return call('node', [script, ...extra], o);
    },
  },
  posts: {
    desc: '抓取播主的投稿列表（author-video）',
    args: '[--quiet]',
    run: (o) => {
      const [b, a] = pyArgs(S('list_posts.py'));
      return call(b, [...a, ...(o.quiet ? ['--quiet'] : [])], o);
    },
  },
  history: {
    desc: '下载管理：列出已下载录播历史（--json 输出机器可读）',
    args: '[--json]',
    run: (o) => {
      const cfg = loadConfig();
      const recs = listAll(cfg.workDir);
      console.log(`历史目录: ${historyDir(cfg.workDir)}`);
      console.log(`已下载: ${recs.length} 个，合计 ${(recs.reduce((a, r) => a + Number(r.size || 0), 0) / 1024 ** 3).toFixed(2)} GB`);
      if (o.json) { console.log(JSON.stringify(recs, null, 1)); return 0; }
      for (const r of recs.slice(0, 200)) {
        console.log(`  ${r.hash || ''} | ${(r.size / 1024 ** 2).toFixed(0)}MB | ${r.quality || ''} | ${r.finished_at || ''} | ${r.title || r.file || ''}`);
      }
      if (recs.length > 200) console.log(`  … 还有 ${recs.length - 200} 条`);
      return 0;
    },
  },
  probe: {
    desc: 'Step5 核查画质 / 体积（默认两个都跑）',
    args: '[--quality] [--size]',
    run: (o) => {
      const which = o.quality ? ['quality'] : o.size ? ['size'] : ['quality', 'size'];
      let rc = 0;
      for (const w of which) {
        const f = w === 'quality' ? 'step5_probe_quality_all.js' : 'step5_probe_size_all.js';
        rc = call('node', [S(f)], o) || rc;
      }
      return rc;
    },
  },
  m3u8: {
    desc: '工具：打印某分段最高画质 m3u8 地址',
    args: '<hash_id>',
    run: (o) => {
      if (!o._[0]) { console.error('用法: node douyu.mjs m3u8 <hash_id>'); return 2; }
      return call('node', [S('lib_get_m3u8.js'), o._[0]], o);
    },
  },
  stats: {
    desc: '工具：估算码率（需要 --sizes <file.json>）',
    args: '--sizes <file.json>',
    run: (o) => {
      if (!o.sizes) { console.error('用法: node douyu.mjs stats --sizes <file.json>'); return 2; }
      const [bin, args] = pyArgs(S('util_bitrate_stats.py'), ['--sizes', o.sizes]);
      return call(bin, args, o);
    },
  },
  doctor: {
    desc: '体检：检查 Python / Node / ffmpeg / 配置文件是否就绪',
    run: (o) => doctor(o),
  },
};

function parseArgs(argv) {
  const o = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a.startsWith('--')) {
      const key = a.slice(2);
      const next = argv[i + 1];
      if (next !== undefined && !next.startsWith('--')) { o[key] = next; i++; }
      else o[key] = true;
    } else o._.push(a);
  }
  return o;
}

function call(bin, args, o) {
  const env = { ...process.env };
  if (o.config) env.DOUYU_CONFIG = path.resolve(o.config);
  if (o['work-dir']) env.DOUYU_WORK_DIR = path.resolve(o['work-dir']);
  console.log(`\n$ ${bin} ${args.map((x) => (x.includes(' ') ? `"${x}"` : x)).join(' ')}\n`);
  const r = spawnSync(bin, args, { stdio: 'inherit', cwd: ROOT, env, shell: false });
  if (r.error) { console.error(`无法启动 ${bin}: ${r.error.message}`); return 127; }
  return r.status ?? 1;
}

function runPipeline(o) {
  const cfg = loadConfig();  // 读取 danmaku_mode / quality（GUI 下拉框写进 config）
  const [pb, pa] = pyArgs(S('step4_pull_danmaku.py'));
  const [ab, aa] = pyArgs(S('util_convert_danmaku_ass.py'));
  const mode = String(cfg.danmakuMode || 'ass');
  console.log(`弹幕模式: ${mode}  清晰度: ${cfg.quality}`);

  const danmakuSteps = mode === 'none' ? [] :
    mode === 'xml' ? [['danmaku', () => call(pb, pa, o)]] :
    [['danmaku', () => call(pb, pa, o)], ['ass', () => call(ab, aa, o)]];

  const steps = [
    ['fetch', () => { const [b, a] = pyArgs(S('step1_fetch_list.py')); return call(b, a, o); }],
    ['detail', () => { const [b, a] = pyArgs(S('step2_fetch_detail.py')); return call(b, a, o); }],
    ['download', () => call('node', [S('step3_download_batch.mjs')], o)],
    ...danmakuSteps,
    ['probe', () => {
      let rc = call('node', [S('step5_probe_quality_all.js')], o);
      return call('node', [S('step5_probe_size_all.js')], o) || rc;
    }],
  ];
  const skip = new Set(['skip-download', 'skip-danmaku', 'skip-probe'].filter((k) => o[k]));
  const skipMap = { 'skip-download': 'download', 'skip-danmaku': 'danmaku', 'skip-probe': 'probe' };
  const skipDm = new Set(['danmaku', 'ass']);
  for (const [name, fn] of steps) {
    if (skip.has('skip-danmaku') && skipDm.has(name)) { console.log(`\n[跳过] ${name}`); continue; }
    if ([...skip].some((k) => skipMap[k] === name)) { console.log(`\n[跳过] ${name}`); continue; }
    console.log(`\n===== ${name} =====`);
    const rc = fn();
    if (rc !== 0) { console.error(`\n${name} 失败 (rc=${rc})，流程中止。`); return rc; }
  }
  console.log('\n===== 全部完成 =====');
  return 0;
}

function doctor(o) {
  const env = { ...process.env };
  if (o.config) env.DOUYU_CONFIG = path.resolve(o.config);
  let problems = 0;
  const chk = (name, ok, hint) => {
    console.log(`  ${ok ? '[OK]  ' : '[MISS]'} ${name}${ok ? '' : '  <- ' + hint}`);
    if (!ok) problems++;
  };
  console.log('== 运行环境 ==');
  const usingBundledPy = USE_RUN_PY;
  if (usingBundledPy) {
    const r = spawnSync(PY, ['--run-py', '--version'], { stdio: 'ignore', env });
    chk('内置 Python（随 exe 打包）', !r.error && r.status === 0,
        'exe 不完整，请重新解压发布包');
    const rq = spawnSync(PY, ['--run-py', '-c', 'import requests'], { stdio: 'ignore', env });
    chk('内置 requests', !rq.error && rq.status === 0, 'exe 内缺少 requests');
  } else {
    const r = spawnSync('python', ['--version'], { stdio: 'ignore', env });
    chk('python', !r.error && r.status === 0, '需要 Python 3.9+（step1/2/4 依赖）');
    const py = spawnSync('python', ['-c', 'import requests'], { stdio: 'ignore', env });
    chk('python requests', py.status === 0, 'pip install -r requirements.txt');
  }
  for (const [bin, args, hint] of [
    ['node', ['--version'], '需要 Node 18+（下载/取流/探测依赖）'],
    ['ffmpeg', ['-version'], '需要 ffmpeg（或配置 ffmpeg 路径）'],
  ]) {
    const r = spawnSync(bin, args, { stdio: 'ignore', env });
    chk(bin, !r.error && r.status === 0, hint);
  }

  console.log('== 配置 ==');
  const cfgPath = env.DOUYU_CONFIG || path.join(ROOT, 'config.json');
  const exists = fs.existsSync(cfgPath);
  chk(`config.json (${cfgPath})`, exists, '先跑 node douyu.mjs init');
  if (exists) {
    try {
      const c = JSON.parse(fs.readFileSync(cfgPath, 'utf8').replace(/^\uFEFF/, ''));
      const up = String(c.up_id || '').trim();
      chk('up_id 已填写', up && up !== 'REPLACE_WITH_UP_ID' && up !== '<UP_ID>', '填主播录播页 /author/ 后的 ID');
      chk('work_dir 已填写', !!String(c.work_dir || '').trim(), '填工作目录');
    } catch (e) { chk('config.json 可解析', false, e.message); }
  }
  console.log(`\n${problems === 0 ? '全部就绪。' : `${problems} 项待处理。`}`);
  return problems === 0 ? 0 : 1;
}

function help() {
  console.log(`douyu-vod-toolkit —— 斗鱼录播批量归档工具箱

用法: node douyu.mjs <command> [options]

命令:`);
  for (const [k, v] of Object.entries(COMMANDS)) {
    console.log(`  ${k.padEnd(10)} ${v.desc}${v.args ? '\n' + ' '.repeat(14) + v.args : ''}`);
  }
  console.log(`
通用选项:
  --config <file>     指定配置文件（等价于 DOUYU_CONFIG）
  --work-dir <dir>    覆盖工作目录（等价于 DOUYU_WORK_DIR）
  --limit <n>         danmaku / ass 只处理前 n 个（先试跑）
  -h, --help          显示本帮助

示例:
  node douyu.mjs init
  node douyu.mjs doctor
  node douyu.mjs run --skip-download          # 只抓数据不下载
  node douyu.mjs download --hash <hash_id> --out out.mp4
  node douyu.mjs m3u8 <hash_id>
  node douyu.mjs stats --sizes sizes.json

也可以直接调用 scripts/ 下的单个脚本，详见 README.md。`);
}

const argv = process.argv.slice(2);
if (argv.length === 0 || argv[0] === '-h' || argv[0] === '--help' || argv[0] === 'help') {
  help();
  process.exit(0);
}
const name = argv[0];
const cmd = COMMANDS[name];
if (!cmd) { console.error(`未知命令: ${name}\n`); help(); process.exit(2); }
const o = parseArgs(argv.slice(1));
let rc;
if (cmd.run) rc = cmd.run(o);
else if (cmd.cmd) { const [bin, args] = cmd.cmd(o); rc = call(bin, args, o); }
else { console.error(`命令 ${name} 未实现`); rc = 2; }
process.exit(rc);
