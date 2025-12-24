#!/bin/bash

# SageMaker Studio Code Editor 内での Slurm + MUNGE セットアップスクリプト
# 技術検証用 - 本番環境では SSH 経由を推奨

set -euo pipefail

# 設定変数
DEFAULT_CLUSTER_NAME="cpu-slurm-cluster"
DEFAULT_HEAD_NODE_NAME="controller"

echo "=============================================="
echo "SageMaker Studio Code Editor - Slurm 設定スクリプト"
echo "MUNGE 認証 + Slurm コマンド実行環境構築"
echo "=============================================="
echo "⚠️  本スクリプトは技術検証用です"
echo "   本番環境では SSH 経由のアクセスを推奨します"
echo ""

# Step 1: 既存の env_vars ファイルを確認
echo "=== Step 1: 環境変数ファイルの確認 ==="
if [ -f /tmp/env_vars ]; then
    echo "既存の環境変数ファイルを確認:"
    cat /tmp/env_vars
    source /tmp/env_vars
    echo "✅ 既存設定を読み込みました"
else
    echo "env_vars ファイルが見つかりません。手動で設定します。"
fi

# Step 2: 環境変数の手動設定
echo ""
echo "=== Step 2: 環境変数の設定 ==="
export CLUSTER_NAME="${CLUSTER_NAME:-$DEFAULT_CLUSTER_NAME}"
export HEAD_NODE_NAME="${HEAD_NODE_NAME:-$DEFAULT_HEAD_NODE_NAME}"

echo "設定値:"
echo "  クラスター名: $CLUSTER_NAME"
echo "  ヘッドノード名: $HEAD_NODE_NAME"

# Step 3: クラスター情報の取得と検証
echo ""
echo "=== Step 3: クラスター情報の取得 ==="
CLUSTER_INFO=$(aws sagemaker list-cluster-nodes --cluster-name "$CLUSTER_NAME" 2>/dev/null)
if [ $? -ne 0 ]; then
    echo "❌ エラー: クラスター '$CLUSTER_NAME' が見つかりません"
    echo "利用可能なクラスターを確認:"
    aws sagemaker list-clusters --query 'ClusterSummaries[].ClusterName' --output table
    exit 1
fi

CONTROLLER_ID=$(echo "$CLUSTER_INFO" | jq -r '.ClusterNodeSummaries[] | select(.InstanceGroupName=="'$HEAD_NODE_NAME'") | .InstanceId' | head -1)
CLUSTER_ID=$(aws sagemaker describe-cluster --cluster-name "$CLUSTER_NAME" --query 'ClusterArn' --output text | cut -d'/' -f2)

# Step 4: 取得した情報の検証
echo ""
echo "=== Step 4: 環境変数の検証 ==="
echo "クラスター名: $CLUSTER_NAME"
echo "ヘッドノード名: $HEAD_NODE_NAME"
echo "コントローラー ID: $CONTROLLER_ID"
echo "クラスター ID: $CLUSTER_ID"

if [ -z "$CONTROLLER_ID" ] || [ -z "$CLUSTER_ID" ]; then
    echo "❌ エラー: 必要な情報が取得できませんでした"
    echo "クラスター名とヘッドノード名を確認してください"
    exit 1
fi

# Step 5: SSM ターゲットの動作確認
echo ""
echo "=== Step 5: SSM 接続確認 ==="
SSM_TARGET="sagemaker-cluster:${CLUSTER_ID}_${HEAD_NODE_NAME}-${CONTROLLER_ID}"
echo "SSM Target: $SSM_TARGET"
echo "接続テストを実行中（30秒タイムアウト）..."

# SSM接続テストのステータスチェック
timeout 30s bash -c "
    aws ssm start-session \
        --target '$SSM_TARGET' \
        --document-name AWS-StartInteractiveCommand \
        --parameters '{\"command\":[\"echo SSM connection test successful\"]}' 2>&1 | \
    grep -q 'SSM connection test successful'
"

SSM_EXIT_CODE=$?
if [ $SSM_EXIT_CODE -eq 0 ]; then
    echo "✅ SSM接続確認成功"
elif [ $SSM_EXIT_CODE -eq 124 ]; then
    echo "⚠️  SSM接続がタイムアウトしました（30秒）"
    echo "ネットワークまたはSSM Agentの確認が必要です"
    exit 1
else
    echo "❌ SSM接続に失敗しました。ターゲットを確認してください"
    echo "SSM Target: $SSM_TARGET"
    exit 1
fi

# Step 6: MUNGE ディレクトリの準備
echo ""
echo "=== Step 6: MUNGE ディレクトリの準備 ==="
sudo mkdir -p /etc/munge /run/munge /var/log/munge /var/lib/munge
sudo chmod 755 /run/munge
sudo chown -R munge:munge /etc/munge /run/munge /var/log/munge /var/lib/munge
echo "✅ MUNGE ディレクトリ準備完了"

# Step 7: MUNGE キーサイズの確認
echo ""
echo "=== Step 7: MUNGE キーサイズの確認 ==="
MUNGE_KEY_SIZE=$(timeout 30s aws ssm start-session \
    --target "$SSM_TARGET" \
    --document-name AWS-StartInteractiveCommand \
    --parameters '{"command":["sudo stat -c%s /etc/munge/munge.key"]}' 2>/dev/null | \
    grep -v "session" | grep -E '^[0-9]+$' | head -1)

echo "Expected MUNGE key size: ${MUNGE_KEY_SIZE:-未取得} bytes"

if [ -z "$MUNGE_KEY_SIZE" ] || [ "$MUNGE_KEY_SIZE" -eq 0 ]; then
    echo "❌ エラー: MUNGE キーサイズの取得に失敗しました"
    exit 1
fi

# Step 8: MUNGE キーの取得（hexdump方式）
echo ""
echo "=== Step 8: MUNGE キーの取得 ==="
TEMP_FILE=$(mktemp)
echo "一時ファイル: $TEMP_FILE"

timeout 60s aws ssm start-session \
    --target "$SSM_TARGET" \
    --document-name AWS-StartInteractiveCommand \
    --parameters '{"command":["sudo hexdump -C /etc/munge/munge.key"]}' > "$TEMP_FILE" 2>/dev/null

if [ $? -ne 0 ]; then
    echo "❌ MUNGE キーの取得に失敗しました"
    rm -f "$TEMP_FILE"
    exit 1
fi

# Step 9: hexdump からバイナリに変換
echo ""
echo "=== Step 9: hexdump からバイナリ変換 ==="
cat "$TEMP_FILE" | grep "^[0-9a-f].*  |" | sed 's/^[0-9a-f]\{8\}  //' | cut -d'|' -f1 | xxd -r -p | sudo tee /etc/munge/munge.key > /dev/null

# Step 10: 変換結果の検証
CONVERTED_SIZE=$(sudo stat -c%s /etc/munge/munge.key 2>/dev/null || echo "0")
echo "変換後キーサイズ: $CONVERTED_SIZE bytes"

if [ "$CONVERTED_SIZE" -ne "$MUNGE_KEY_SIZE" ]; then
    echo "❌ MUNGE キーの変換に失敗しました"
    echo "期待サイズ: $MUNGE_KEY_SIZE bytes, 実際: $CONVERTED_SIZE bytes"
    rm -f "$TEMP_FILE"
    exit 1
else
    echo "✅ MUNGE キーの変換成功"
fi

# Step 11: 権限設定
echo ""
echo "=== Step 11: 権限設定 ==="
sudo chown munge:munge /etc/munge/munge.key
sudo chmod 400 /etc/munge/munge.key
rm -f "$TEMP_FILE"
echo "✅ 権限設定完了"

# Step 12: MUNGE デーモンの起動（コンテナ対応）
echo ""
echo "=== Step 12: MUNGE デーモンの起動 ==="
# 既存のプロセスを終了
sudo pkill -f munged || true
sleep 2

# コンテナ環境対応の --foreground モードで起動
echo "MUNGE デーモンをバックグラウンドで起動中..."
sudo -u munge /usr/sbin/munged --foreground --socket=/run/munge/munge.socket.2 &
MUNGE_PID=$!
echo "MUNGE PID: $MUNGE_PID"

# 起動確認
sleep 3
if ps -p $MUNGE_PID > /dev/null; then
    echo "✅ MUNGE デーモン起動成功"
else
    echo "❌ MUNGE デーモンの起動に失敗しました"
    exit 1
fi

# Step 13: MUNGE のテスト
echo ""
echo "=== Step 13: MUNGE 認証テスト ==="
sleep 2  # デーモン安定化待機

if timeout 10s bash -c 'echo "test" | munge | unmunge' > /dev/null 2>&1; then
    echo "✅ MUNGE 認証テスト成功"
    echo "test" | munge | unmunge
else
    echo "❌ MUNGE 認証テスト失敗"
    echo "デバッグ情報:"
    ps aux | grep munge || true
    ls -la /run/munge/ || true
    exit 1
fi

# Step 14: Slurm コマンドの実行テスト
echo ""
echo "=== Step 14: Slurm コマンドテスト ==="
echo "sinfo コマンドの実行:"
if timeout 15s sinfo; then
    echo "✅ sinfo 実行成功"
else
    echo "❌ sinfo 実行失敗"
fi

echo ""
echo "squeue コマンドの実行:"
if timeout 15s squeue; then
    echo "✅ squeue 実行成功"
else
    echo "❌ squeue 実行失敗"
fi

# 完了メッセージ
echo ""
echo "=============================================="
echo "🎉 セットアップ完了！"
echo "=============================================="
echo "MUNGE PID: $MUNGE_PID"
echo "SSM Target: $SSM_TARGET"
echo ""
echo "注意事項:"
echo "- MUNGE デーモンはバックグラウンドで動作中です"
echo "- Studio セッション終了時にプロセスも終了します"
echo "- 本番環境では SSH 経由のアクセスを推奨します"
echo ""
echo "確認コマンド:"
echo "  ps aux | grep munge"
echo "  sinfo"
echo "  squeue"
echo "=============================================="
