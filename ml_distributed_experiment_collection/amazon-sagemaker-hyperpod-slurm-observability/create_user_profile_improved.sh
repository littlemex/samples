#!/bin/bash

# SageMaker Studio User Profile 作成スクリプト（FSx権限対応版）
# CustomPosixUserConfig を使用してFSx書き込み権限を確保

set -euo pipefail

# 設定変数
DOMAIN_NAME="hyperpod-studio-integration"  # CloudFormation スタック名と同じ
USER_PROFILE_NAME="ml-researcher2"  # 作成するユーザー名
REGION="us-east-1"  # 必要に応じて変更してください
CLUSTER_NAME="cpu-slurm-cluster"  # HyperPod クラスター名
HEAD_NODE_NAME="controller"

# CustomPosixUserConfig設定（AWS制約に準拠）
STUDIO_UID=10001  # AWS minimum: 10000
STUDIO_GID=1001   # AWS minimum: 1001

echo "=============================================="
echo "SageMaker Studio User Profile 作成スクリプト"
echo "FSx 書き込み権限対応版（CustomPosixUserConfig使用）"
echo "=============================================="

# 1. コマンドライン引数の処理
if [[ $# -ge 1 ]]; then
    USER_PROFILE_NAME="$1"
    echo "ユーザー名を引数から設定: $USER_PROFILE_NAME"
fi

if [[ $# -ge 2 ]]; then
    DOMAIN_NAME="$2"
    echo "Domain 名を引数から設定: $DOMAIN_NAME"
fi

if [[ $# -ge 3 ]]; then
    CLUSTER_NAME="$3"
    echo "クラスター名を引数から設定: $CLUSTER_NAME"
fi

# 2. 既存 Studio Domain の確認
echo "1. Studio Domain を確認中..."

# CloudFormation スタックから Domain ID を取得
DOMAIN_ID=$(aws cloudformation describe-stacks \
    --stack-name "$DOMAIN_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`StudioDomainId`].OutputValue' \
    --output text 2>/dev/null || echo "")

if [[ -z "$DOMAIN_ID" ]]; then
    echo "エラー: CloudFormation スタック '$DOMAIN_NAME' から Domain ID を取得できません"
    echo "利用可能なスタック:"
    aws cloudformation list-stacks --region "$REGION" \
        --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE \
        --query 'StackSummaries[].[StackName]' --output table
    exit 1
fi

echo "取得した情報:"
echo "  Domain ID: $DOMAIN_ID"
echo "  User Profile 名: $USER_PROFILE_NAME"
echo "  Studio UID: $STUDIO_UID"
echo "  Studio GID: $STUDIO_GID"

# 3. 既存 User Profile の確認
echo ""
echo "2. 既存 User Profile を確認中..."

EXISTING_PROFILES=$(aws sagemaker list-user-profiles \
    --domain-id-equals "$DOMAIN_ID" \
    --region "$REGION" \
    --query "UserProfiles[?UserProfileName=='$USER_PROFILE_NAME'].UserProfileName" \
    --output text)

if [[ -n "$EXISTING_PROFILES" ]]; then
    echo "警告: User Profile '$USER_PROFILE_NAME' が既に存在します"
    echo "既存のプロファイル一覧:"
    aws sagemaker list-user-profiles --domain-id-equals "$DOMAIN_ID" --region "$REGION" \
        --query 'UserProfiles[].[UserProfileName,Status,CreationTime]' --output table
    exit 1
fi

# 4. HyperPod クラスターでの対応ユーザー作成
echo ""
echo "3. HyperPod クラスターで対応ユーザーを作成中..."

# HyperPod クラスター情報の取得
CLUSTER_INFO=$(aws sagemaker list-cluster-nodes --cluster-name "$CLUSTER_NAME" --region "$REGION" 2>/dev/null)
if [[ $? -ne 0 ]]; then
    echo "警告: HyperPod クラスター '$CLUSTER_NAME' が見つかりません"
    echo "クラスター作成後に手動でユーザー設定を行ってください"
    SKIP_HYPERPOD_SETUP=true
else
    CONTROLLER_ID=$(echo "$CLUSTER_INFO" | jq -r ".ClusterNodeSummaries[] | select(.InstanceGroupName==\"$HEAD_NODE_NAME\") | .InstanceId" | head -1)
    CLUSTER_ID=$(aws sagemaker describe-cluster --cluster-name "$CLUSTER_NAME" --region "$REGION" --query 'ClusterArn' --output text | cut -d'/' -f2)
    
    if [[ -n "$CONTROLLER_ID" && -n "$CLUSTER_ID" ]]; then
        SSM_TARGET="sagemaker-cluster:${CLUSTER_ID}_${HEAD_NODE_NAME}-${CONTROLLER_ID}"
        echo "  HyperPod SSM Target: $SSM_TARGET"
        
        # HyperPod側での対応ユーザー作成
        echo "  ユーザー作成中: studio-user (UID: $STUDIO_UID, GID: $STUDIO_GID)"
        aws ssm start-session \
            --target "$SSM_TARGET" \
            --region "$REGION" \
            --document-name AWS-StartInteractiveCommand \
            --parameters "{\"command\":[\"sudo groupadd -g $STUDIO_GID studio-group 2>/dev/null || true\"]}" > /dev/null 2>&1
            
        aws ssm start-session \
            --target "$SSM_TARGET" \
            --region "$REGION" \
            --document-name AWS-StartInteractiveCommand \
            --parameters "{\"command\":[\"sudo useradd -u $STUDIO_UID -g $STUDIO_GID -m -s /bin/bash studio-user 2>/dev/null || true\"]}" > /dev/null 2>&1
            
        # FSx ディレクトリの権限設定
        echo "  FSx ディレクトリの権限設定中..."
        aws ssm start-session \
            --target "$SSM_TARGET" \
            --region "$REGION" \
            --document-name AWS-StartInteractiveCommand \
            --parameters "{\"command\":[\"sudo mkdir -p /fsx/studio-workspace\"]}" > /dev/null 2>&1
            
        aws ssm start-session \
            --target "$SSM_TARGET" \
            --region "$REGION" \
            --document-name AWS-StartInteractiveCommand \
            --parameters "{\"command\":[\"sudo chown $STUDIO_UID:$STUDIO_GID /fsx/studio-workspace\"]}" > /dev/null 2>&1
        
        echo "  ✅ HyperPod 側の設定完了"
    else
        echo "  警告: HyperPod クラスター情報の取得に失敗"
        SKIP_HYPERPOD_SETUP=true
    fi
fi

# 5. User Profile の作成（CustomPosixUserConfig付き）
echo ""
echo "4. User Profile を作成中（CustomPosixUserConfig 使用）..."

# 一時ファイルでUser Profile設定を作成
USER_PROFILE_CONFIG=$(mktemp)
cat > "$USER_PROFILE_CONFIG" << EOF
{
    "CustomPosixUserConfig": {
        "Uid": $STUDIO_UID,
        "Gid": $STUDIO_GID
    }
}
EOF

echo "CustomPosixUserConfig:"
cat "$USER_PROFILE_CONFIG" | jq '.'

# User Profile の作成
USER_PROFILE_ARN=$(aws sagemaker create-user-profile \
    --domain-id "$DOMAIN_ID" \
    --user-profile-name "$USER_PROFILE_NAME" \
    --user-settings file://"$USER_PROFILE_CONFIG" \
    --region "$REGION" \
    --query 'UserProfileArn' \
    --output text)

# 一時ファイルのクリーンアップ
rm -f "$USER_PROFILE_CONFIG"

echo "✅ User Profile 作成を開始しました"
echo "User Profile ARN: $USER_PROFILE_ARN"

# 6. 作成状況の監視
echo ""
echo "5. User Profile 作成状況を監視中..."

ATTEMPTS=0
MAX_ATTEMPTS=30  # 15分（30秒間隔）

while [[ $ATTEMPTS -lt $MAX_ATTEMPTS ]]; do
    PROFILE_STATUS=$(aws sagemaker describe-user-profile \
        --domain-id "$DOMAIN_ID" \
        --user-profile-name "$USER_PROFILE_NAME" \
        --region "$REGION" \
        --query 'Status' \
        --output text 2>/dev/null || echo "Creating")
    
    echo "現在のプロファイル状態: $PROFILE_STATUS (試行 $((ATTEMPTS + 1))/$MAX_ATTEMPTS)"
    
    if [[ "$PROFILE_STATUS" == "InService" ]]; then
        echo "✅ User Profile の作成が完了しました！"
        break
    elif [[ "$PROFILE_STATUS" == "Failed" ]]; then
        echo "❌ User Profile の作成に失敗しました"
        echo "詳細エラー情報:"
        aws sagemaker describe-user-profile \
            --domain-id "$DOMAIN_ID" \
            --user-profile-name "$USER_PROFILE_NAME" \
            --region "$REGION"
        exit 1
    fi
    
    sleep 30
    ((ATTEMPTS++))
done

if [[ $ATTEMPTS -eq $MAX_ATTEMPTS ]]; then
    echo "⚠️  作成がタイムアウトしました。コンソールで状況を確認してください"
fi

# 7. FSx権限テストスクリプトの生成
echo ""
echo "6. FSx 権限テストスクリプトを生成中..."

cat > fsx_write_test.sh << 'EOF'
#!/bin/bash

# FSx 書き込み権限テストスクリプト
# Studio Code Editor で実行

echo "=== FSx 権限テスト ==="

FSX_MOUNT=$(df -h | grep fsx_lustre | awk '{print $NF}')
echo "FSx Mount Point: $FSX_MOUNT"

# 基本情報確認
echo "Current User: $(id)"
echo "FSx Root Directory:"
ls -la "$FSX_MOUNT"

# 書き込みテスト
TEST_DIR="$FSX_MOUNT/studio-workspace"
TEST_FILE="$TEST_DIR/test-$(date +%s).txt"

echo ""
echo "書き込みテスト開始..."

if [[ -d "$TEST_DIR" ]]; then
    echo "✅ studio-workspace ディレクトリが存在します"
    
    if touch "$TEST_FILE" 2>/dev/null; then
        echo "✅ ファイル作成成功: $TEST_FILE"
        echo "Hello from Studio $(date)" > "$TEST_FILE"
        
        if cat "$TEST_FILE" >/dev/null 2>&1; then
            echo "✅ ファイル読み込み成功"
            echo "✅ FSx 書き込み権限が正常に機能しています！"
        else
            echo "❌ ファイル読み込み失敗"
        fi
        
        # クリーンアップ
        rm -f "$TEST_FILE"
    else
        echo "❌ ファイル作成失敗: Permission denied"
        echo "UID/GID マッピングの確認が必要です"
    fi
else
    echo "❌ studio-workspace ディレクトリが見つかりません"
    echo "HyperPod側での権限設定が必要です"
fi

echo ""
echo "=== テスト完了 ==="
EOF

chmod +x fsx_write_test.sh

# 8. 完了メッセージ
echo ""
echo "=============================================="
echo "🎉 User Profile 作成完了！"
echo "=============================================="
echo "Domain ID: $DOMAIN_ID"
echo "User Profile: $USER_PROFILE_NAME"
echo "Studio UID/GID: $STUDIO_UID/$STUDIO_GID"
echo ""
echo "次のステップ:"
echo "1. SageMaker コンソールでプロファイルにアクセス"
echo "2. Code Editor Space を作成し、FSx とライフサイクル設定をアタッチ"
echo "3. Code Editor 起動後、./fsx_write_test.sh を実行して権限確認"
echo ""

if [[ "${SKIP_HYPERPOD_SETUP:-false}" == "true" ]]; then
    echo "⚠️  HyperPod設定がスキップされました"
    echo "手動で以下を実行してください:"
    echo "ssh hyperpod-login"
    echo "sudo groupadd -g $STUDIO_GID studio-group"
    echo "sudo useradd -u $STUDIO_UID -g $STUDIO_GID -m studio-user" 
    echo "sudo chown $STUDIO_UID:$STUDIO_GID /fsx/studio-workspace"
    echo ""
fi

echo "アクセス URL:"
echo "https://$REGION.console.aws.amazon.com/sagemaker/home?region=$REGION#/studio"
echo "=============================================="
