#!/bin/bash

# SageMaker Studio Domain 作成スクリプト（HyperPod + FSx 統合用）
# awsome-distributed-training の CloudFormation テンプレートを使用

set -euo pipefail

# 設定変数
CLUSTER_NAME="cpu-slurm-cluster"  # 実際のクラスター名に変更してください
STACK_NAME="hyperpod-studio-integration"
REGION="us-east-1"  # 必要に応じて変更してください
HEAD_NODE_NAME="controller"  # または "controller-machine"
SHARED_FSX="True"  # True: 共有FSx, False: ユーザー別パーティション
ADDITIONAL_USERS=""  # 追加ユーザー（カンマ区切り）

echo "=============================================="
echo "SageMaker Studio Domain + FSx 統合作成スクリプト"
echo "awsome-distributed-training CloudFormation 使用"
echo "=============================================="

# 1. 既存 HyperPod クラスター情報の取得
echo "1. HyperPod クラスター情報を取得中..."
echo "クラスター名: $CLUSTER_NAME"

# クラスターが存在するかチェック
if ! aws sagemaker describe-cluster --cluster-name "$CLUSTER_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "エラー: クラスター '$CLUSTER_NAME' が見つかりません"
    echo "利用可能なクラスター一覧:"
    aws sagemaker list-clusters --region "$REGION" --query 'ClusterSummaries[].ClusterName' --output table
    exit 1
fi

# クラスター詳細情報を取得
CLUSTER_INFO=$(aws sagemaker describe-cluster \
    --cluster-name "$CLUSTER_NAME" \
    --region "$REGION" \
    --output json)

# VPC 設定を取得
VPC_CONFIG=$(echo "$CLUSTER_INFO" | jq -r '.VpcConfig')
SUBNET_IDS=$(echo "$VPC_CONFIG" | jq -r '.Subnets[]? // empty' | tr '\n' ',' | sed 's/,$//')
SECURITY_GROUP_IDS=$(echo "$VPC_CONFIG" | jq -r '.SecurityGroupIds[]? // empty' | head -1)

# VPC ID をサブネットから取得
FIRST_SUBNET=$(echo "$VPC_CONFIG" | jq -r '.Subnets[]? // empty' | head -1)
VPC_ID=$(aws ec2 describe-subnets \
    --subnet-ids "$FIRST_SUBNET" \
    --region "$REGION" \
    --query 'Subnets[0].VpcId' \
    --output text)

# FSx for Lustre ID を取得
CLUSTER_CONFIG=$(echo "$CLUSTER_INFO" | jq -r '.InstanceGroups[] | select(.InstanceGroupName == "controller") | .LifeCycleConfig.SourceS3Uri // empty')
if [[ -z "$CLUSTER_CONFIG" ]]; then
    echo "エラー: LifeCycleConfig.SourceS3Uri が見つかりません"
    exit 1
fi

# S3 から provisioning_parameters.json をダウンロードして FSx ID を取得
BUCKET_PATH=$(echo "$CLUSTER_CONFIG" | sed 's|s3://||' | sed 's|/.*||')
aws s3 cp "$CLUSTER_CONFIG/provisioning_parameters.json" /tmp/provisioning_params.json >/dev/null 2>&1
FSX_ID=$(jq -r '.fsx_dns_name // empty' /tmp/provisioning_params.json | cut -d'.' -f1)

if [[ -z "$FSX_ID" ]]; then
    echo "エラー: FSx for Lustre ID が取得できませんでした"
    echo "provisioning_parameters.json の内容:"
    cat /tmp/provisioning_params.json
    exit 1
fi

echo "取得したパラメータ:"
echo "  VPC ID: $VPC_ID"
echo "  Subnet IDs: $SUBNET_IDS"
echo "  Security Group ID: $SECURITY_GROUP_IDS"
echo "  FSx Lustre ID: $FSX_ID"
echo "  Head Node Name: $HEAD_NODE_NAME"

# 2. CloudFormation テンプレートのダウンロード
echo ""
echo "2. CloudFormation テンプレートをダウンロード中..."
TEMPLATE_URL="https://raw.githubusercontent.com/aws-samples/awsome-distributed-training/main/1.architectures/5.sagemaker-hyperpod/slurm-studio/studio-slurm.yaml"
curl -sL "$TEMPLATE_URL" -o /tmp/studio-slurm.yaml

if [[ ! -f "/tmp/studio-slurm.yaml" ]]; then
    echo "エラー: CloudFormation テンプレートのダウンロードに失敗しました"
    exit 1
fi

echo "✅ CloudFormation テンプレートをダウンロードしました"

# 3. パラメータファイルの作成
echo ""
echo "3. CloudFormation パラメータファイルを作成中..."
cat > /tmp/studio-parameters.json << EOF
[
    {
        "ParameterKey": "ExistingVpcId",
        "ParameterValue": "$VPC_ID"
    },
    {
        "ParameterKey": "ExistingSubnetIds",
        "ParameterValue": "$SUBNET_IDS"
    },
    {
        "ParameterKey": "ExistingFSxLustreId",
        "ParameterValue": "$FSX_ID"
    },
    {
        "ParameterKey": "SecurityGroupId",
        "ParameterValue": "$SECURITY_GROUP_IDS"
    },
    {
        "ParameterKey": "HyperPodClusterName",
        "ParameterValue": "$CLUSTER_NAME"
    },
    {
        "ParameterKey": "HeadNodeName",
        "ParameterValue": "$HEAD_NODE_NAME"
    },
    {
        "ParameterKey": "SharedFSx",
        "ParameterValue": "$SHARED_FSX"
    },
    {
        "ParameterKey": "AdditionalUsers",
        "ParameterValue": "$ADDITIONAL_USERS"
    }
]
EOF

echo "パラメータファイル作成完了:"
cat /tmp/studio-parameters.json

# 4. 既存スタックの確認
echo ""
echo "4. 既存 CloudFormation スタックを確認中..."
if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "警告: スタック '$STACK_NAME' が既に存在します"
    echo "既存スタックを削除するか、異なる名前を使用してください"
    echo ""
    echo "既存スタックの状態:"
    aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$REGION" \
        --query 'Stacks[0].{Name:StackName,Status:StackStatus,Created:CreationTime}' --output table
    exit 1
fi

# 5. CloudFormation スタックのデプロイ
echo ""
echo "5. CloudFormation スタックをデプロイ中..."
echo "スタック名: $STACK_NAME"
echo "作成には約 15-20 分かかります（Lambda + FSx 統合のため）"

aws cloudformation create-stack \
    --stack-name "$STACK_NAME" \
    --template-body file:///tmp/studio-slurm.yaml \
    --parameters file:///tmp/studio-parameters.json \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "$REGION"

echo "✅ CloudFormation スタック作成を開始しました"

# 6. デプロイ状況の監視
echo ""
echo "6. デプロイ状況を監視中..."

ATTEMPTS=0
MAX_ATTEMPTS=80  # 40分（30秒間隔）

while [[ $ATTEMPTS -lt $MAX_ATTEMPTS ]]; do
    STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "CREATE_IN_PROGRESS")
    
    echo "現在のスタック状態: $STACK_STATUS"
    
    if [[ "$STACK_STATUS" == "CREATE_COMPLETE" ]]; then
        echo "✅ Studio Domain + FSx 統合の作成が完了しました！"
        break
    elif [[ "$STACK_STATUS" == "CREATE_FAILED" ]] || [[ "$STACK_STATUS" == "ROLLBACK_COMPLETE" ]]; then
        echo "❌ CloudFormation スタックの作成に失敗しました"
        echo ""
        echo "エラー詳細:"
        aws cloudformation describe-stack-events --stack-name "$STACK_NAME" --region "$REGION" \
            --query 'StackEvents[?ResourceStatus==`CREATE_FAILED`].[LogicalResourceId,ResourceStatusReason]' \
            --output table
        exit 1
    fi
    
    sleep 30
    ((ATTEMPTS++))
done

if [[ $ATTEMPTS -eq $MAX_ATTEMPTS ]]; then
    echo "⚠️  作成がタイムアウトしました。コンソールで状況を確認してください"
    exit 1
fi

# 7. 作成結果の表示
echo ""
echo "7. 作成結果を取得中..."

# CloudFormation 出力値を取得
OUTPUTS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs')

STUDIO_DOMAIN_ID=$(echo "$OUTPUTS" | jq -r '.[] | select(.OutputKey=="StudioDomainId") | .OutputValue')
SECURITY_GROUP_NFS=$(echo "$OUTPUTS" | jq -r '.[] | select(.OutputKey=="SecurityGroupForNFS") | .OutputValue')

echo ""
echo "=============================================="
echo "作成完了！"
echo "=============================================="
echo "Stack 名: $STACK_NAME"
echo "Studio Domain ID: $STUDIO_DOMAIN_ID"
echo "FSx 統合: 自動設定完了"
echo "Slurm クライアント: ライフサイクル設定により自動インストール"
echo ""
echo "次のステップ:"
echo "1. SageMaker コンソールでドメインにアクセス"
echo "2. User Profile を作成（自動で FSx パーティション作成）"
echo "3. JupyterLab または Code Editor を起動"
echo "4. /shared または /fsx/<user-name>/ で FSx アクセス確認"
echo "5. Studio 内ターミナルで Slurm コマンド（srun, sbatch）テスト"
echo ""
echo "アクセス URL:"
echo "https://$REGION.console.aws.amazon.com/sagemaker/home?region=$REGION#/studio"

# 一時ファイルのクリーンアップ  
rm -f /tmp/studio-slurm.yaml /tmp/studio-parameters.json /tmp/provisioning_params.json

echo "=============================================="
