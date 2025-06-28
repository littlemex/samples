#!/bin/bash

# 既存のコンテナをクリーンアップ
echo "既存のコンテナをクリーンアップしています..."
docker rm -f no-init with-init 2>/dev/null || true

echo "Docker イメージをビルド中..."
docker build -t init-experiment .

echo "===================================================="
echo "実験 1: --init なしでコンテナを実行"
echo "===================================================="
echo "コンテナを起動します..."
docker run -d --name no-init init-experiment
sleep 5

echo "コンテナのログを表示します (ゾンビプロセスの状態が表示されます)..."
echo "Ctrl+C で次のステップに進みます"
docker logs -f no-init

echo "コンテナを停止します (SIGTERM を送信)..."
echo "停止にかかる時間を計測します (--init なしの場合は約10秒かかります)"
time docker stop no-init
echo ""

echo "===================================================="
echo "実験 2: --init ありでコンテナを実行"
echo "===================================================="
echo "コンテナを起動します..."
docker run -d --init --name with-init init-experiment
sleep 5

echo "コンテナのログを表示します (ゾンビプロセスの状態が表示されます)..."
echo "Ctrl+C で次のステップに進みます"
docker logs -f with-init

echo "コンテナを停止します (SIGTERM を送信)..."
echo "停止にかかる時間を計測します (--init ありの場合はすぐに終了します)"
time docker stop with-init
echo ""

echo "実験完了"
