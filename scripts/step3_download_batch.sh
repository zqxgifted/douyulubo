#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
# Step 3 批量下载：N 并发（默认 2）、断点续跑、磁盘空间守门、失败清单。
#
# 用法：
#   DOUYU_CONFIG=/path/to/config.json bash scripts/step3_download_batch.sh
#
# 依赖：node、bash、step3_download_seg.mjs、step2 生成的 data/download_list.json
set -u

CONFIG="${DOUYU_CONFIG:-./config.json}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

read_cfg() {
  node -e '
    const fs = require("fs");
    const p = process.env.DOUYU_CONFIG || "config.json";
    let c = {};
    try { c = JSON.parse(fs.readFileSync(p, "utf8")); } catch {}
    const k = process.argv[1];
    const v = (c[k] ?? process.env["DOUYU_" + k.toUpperCase()] ?? "");
    if (typeof v === "string") process.stdout.write(v); else process.stdout.write(String(v));
  ' "$1"
}

WORK="$(read_cfg work_dir)"
CONCURRENT="$(read_cfg concurrent)"
if [ -z "$WORK" ] || [ ! -d "$WORK" ]; then
  echo "!! 读不到 work_dir（请检查 DOUYU_CONFIG=$CONFIG）"; exit 1
fi
[ -z "$CONCURRENT" ] && CONCURRENT=2

LIST="$WORK/data/download_list.json"
if [ ! -f "$LIST" ]; then
  echo "!! 缺少 $LIST（先跑 step2_fetch_detail.py）"; exit 1
fi

mkdir -p "$WORK/downloads" "$WORK/tmp"
export TMP="$WORK/tmp" TEMP="$WORK/tmp"   # 临时文件全部落在工作目录，不写系统盘
export DOUYU_CONFIG="$CONFIG"
FAILED="$WORK/downloads/_failed.txt"

TOTAL=$(node -p "require('$LIST').length")
echo "=== 共 $TOTAL 场，${CONCURRENT} 并发，输出到 $WORK/downloads"

dl() {
  local hash="$1" file="$2"
  local out="$WORK/downloads/$file"
  if [ -f "$out" ]; then
    local sz; sz=$(stat -c%s "$out" 2>/dev/null || echo 0)
    if [ "$sz" -gt 104857600 ]; then echo "SKIP(已存在) $file"; return 0; fi
  fi
  echo "--- 开始 $file"
  node "$HERE/step3_download_seg.mjs" "$hash" "$out"
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    printf '%s\t%s\trc=%s\n' "$hash" "$file" "$rc" >> "$FAILED"
    echo "  !! 失败 rc=$rc"
  fi
  rm -rf "${out%.mp4}-ts"
}

QUEUE="$WORK/data/_dl_queue.txt"
node -e '
  const l = require(process.argv[1]);
  for (const x of l) console.log(x.hash + "\t" + x.file);
' "$LIST" > "$QUEUE"

i=0
while IFS=$'\t' read -r hash file; do
  [ -z "${hash:-}" ] && continue
  dl "$hash" "$file" &
  i=$((i + 1))
  if [ $((i % CONCURRENT)) -eq 0 ]; then wait; fi
  # 空间守门：工作盘剩余 <10GB 立刻停
  FREE_KB=$(df -k "$WORK" | tail -1 | awk '{print $4}')
  if [ "${FREE_KB:-0}" -lt 10485760 ]; then echo "!!! 空间不足 10GB，中止"; break; fi
done < "$QUEUE"
wait
echo "=== 全部完成。失败清单: $FAILED（若存在）"
