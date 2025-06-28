#!/bin/bash

echo "メインプロセス PID: $$"

# サブプロセスを生成して終了させる（ゾンビ化）
while true; do
  # サブシェルでサブプロセスを起動
  (
    echo "新しいサブプロセスを起動 (PID: $$)"
    sleep 2
    exit 0
  ) &
  
  # 少し待ってからプロセス状態を表示
  sleep 3
  echo "現在のプロセス状態:"
  ps aux | grep -v grep | grep -E "PID|defunct|zombie_maker"
  echo "---"
done
