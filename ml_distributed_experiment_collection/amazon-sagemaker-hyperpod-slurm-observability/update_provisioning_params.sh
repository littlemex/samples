#!/bin/bash

# 設定値
BUCKET_NAME="your-hyperpod-bucket-name"  # 実際のS3バケット名に変更
CLUSTER_NAME="cpu-slurm-cluster"
DEFAULT_INSTANCE_TYPE="ml.g5.xlarge"

echo "HyperPod provisioning_parameters.json 自動更新スクリプト"
echo "=============================================="

# S3から現在のファイルをダウンロード
echo "1. S3からprovisioning_parameters.jsonをダウンロード中..."
aws s3 cp s3://${BUCKET_NAME}/provisioning_parameters.json ./provisioning_parameters.json

if [ $? -ne 0 ]; then
    echo "エラー: S3からのダウンロードに失敗しました"
    echo "バケット名を確認してください: ${BUCKET_NAME}"
    exit 1
fi

# 現在の設定内容を表示
echo "2. 現在の設定内容:"
cat provisioning_parameters.json | jq '.'

# worker_groupsに新しいGPUワーカーグループを追加
echo "3. worker_groups に gpu-worker グループを追加中..."
jq --arg instance_type "$DEFAULT_INSTANCE_TYPE" '
  .worker_groups += [{"instance_group_name": "gpu-worker", "partition_name": $instance_type}]
' provisioning_parameters.json > provisioning_parameters_updated.json

# 更新された内容を表示
echo "4. 更新後の設定内容:"
cat provisioning_parameters_updated.json | jq '.'

# S3に更新されたファイルをアップロード
echo "5. 更新されたファイルをS3にアップロード中..."
aws s3 cp provisioning_parameters_updated.json s3://${BUCKET_NAME}/provisioning_parameters.json

if [ $? -eq 0 ]; then
    echo "✅ 正常にアップロードが完了しました"
    echo "クラスター作成を再実行できます"
else
    echo "❌ S3アップロードに失敗しました"
    exit 1
fi

# 一時ファイルのクリーンアップ
rm -f provisioning_parameters.json provisioning_parameters_updated.json

echo "=============================================="
echo "スクリプト実行完了"
