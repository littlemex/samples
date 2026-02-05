#!/bin/bash

set -e

# 設定
REGION=${AWS_REGION:-us-east-1}
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ROLE_NAME="bedrock-mcp-lambda-role"

echo "=== Bedrock Responses API Lambda デプロイ ==="
echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo ""

# IAMロール作成（存在しない場合）
echo "[1/3] IAMロール確認..."
if ! aws iam get-role --role-name $ROLE_NAME 2>/dev/null; then
    echo "IAMロール作成中..."

    cat > /tmp/trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

    aws iam create-role \
        --role-name $ROLE_NAME \
        --assume-role-policy-document file:///tmp/trust-policy.json

    # 基本実行ロール
    aws iam attach-role-policy \
        --role-name $ROLE_NAME \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

    # VPC実行ロール（VPC Lambda用）
    aws iam attach-role-policy \
        --role-name $ROLE_NAME \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole

    echo "IAMロール作成完了。権限反映のため10秒待機..."
    sleep 10
else
    echo "IAMロール既存"
fi

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${ROLE_NAME}"

# Lambda Standard デプロイ
echo ""
echo "[2/3] Lambda Standard デプロイ..."
cd lambda-standard
zip -q function.zip mcp_handler.py

if aws lambda get-function --function-name bedrock-mcp-standard --region $REGION 2>/dev/null; then
    echo "Lambda更新中..."
    aws lambda update-function-code \
        --function-name bedrock-mcp-standard \
        --zip-file fileb://function.zip \
        --region $REGION > /dev/null
else
    echo "Lambda作成中..."
    aws lambda create-function \
        --function-name bedrock-mcp-standard \
        --runtime python3.12 \
        --role $ROLE_ARN \
        --handler mcp_handler.lambda_handler \
        --zip-file fileb://function.zip \
        --timeout 30 \
        --memory-size 512 \
        --region $REGION \
        --description "MCP Tool - Standard (No VPC)" \
        --tags Project=BedrockResponsesAPITest,Type=Standard,VPC=None > /dev/null
fi

rm function.zip
cd ..

# Lambda VPC デプロイ
echo ""
echo "[3/3] Lambda VPC デプロイ..."

# デフォルトVPC取得
DEFAULT_VPC=$(aws ec2 describe-vpcs \
    --filters Name=isDefault,Values=true \
    --query 'Vpcs[0].VpcId' \
    --output text \
    --region $REGION 2>/dev/null || echo "")

if [ -z "$DEFAULT_VPC" ] || [ "$DEFAULT_VPC" = "None" ]; then
    echo "⚠️  デフォルトVPCが見つかりません"
    echo "VPC Lambdaをスキップします（通常Lambdaのみデプロイ）"
    VPC_LAMBDA_DEPLOYED=false
else
    echo "デフォルトVPC: $DEFAULT_VPC"

    # サブネット取得（最初の2つ）
    SUBNET_IDS=$(aws ec2 describe-subnets \
        --filters Name=vpc-id,Values=$DEFAULT_VPC \
        --query 'Subnets[0:2].SubnetId' \
        --output text \
        --region $REGION | tr '\t' ',')

    # セキュリティグループ取得
    SG_ID=$(aws ec2 describe-security-groups \
        --filters Name=vpc-id,Values=$DEFAULT_VPC Name=group-name,Values=default \
        --query 'SecurityGroups[0].GroupId' \
        --output text \
        --region $REGION)

    echo "サブネット: $SUBNET_IDS"
    echo "セキュリティグループ: $SG_ID"

    cd lambda-vpc
    zip -q function.zip mcp_handler.py

    if aws lambda get-function --function-name bedrock-mcp-vpc --region $REGION 2>/dev/null; then
        echo "Lambda更新中..."
        aws lambda update-function-code \
            --function-name bedrock-mcp-vpc \
            --zip-file fileb://function.zip \
            --region $REGION > /dev/null
    else
        echo "Lambda作成中（VPC設定あり）..."
        aws lambda create-function \
            --function-name bedrock-mcp-vpc \
            --runtime python3.12 \
            --role $ROLE_ARN \
            --handler mcp_handler.lambda_handler \
            --zip-file fileb://function.zip \
            --timeout 30 \
            --memory-size 512 \
            --region $REGION \
            --description "MCP Tool - VPC Enabled" \
            --vpc-config SubnetIds=$SUBNET_IDS,SecurityGroupIds=$SG_ID \
            --tags Project=BedrockResponsesAPITest,Type=VPC,VpcId=$DEFAULT_VPC > /dev/null
    fi

    rm function.zip
    cd ..

    VPC_LAMBDA_DEPLOYED=true
fi

# 出力取得
echo ""
echo "[4/4] デプロイ情報取得..."

LAMBDA_STANDARD_ARN=$(aws lambda get-function \
    --function-name bedrock-mcp-standard \
    --query 'Configuration.FunctionArn' \
    --output text \
    --region $REGION)

if [ "$VPC_LAMBDA_DEPLOYED" = true ]; then
    LAMBDA_VPC_ARN=$(aws lambda get-function \
        --function-name bedrock-mcp-vpc \
        --query 'Configuration.FunctionArn' \
        --output text \
        --region $REGION)
else
    LAMBDA_VPC_ARN="未デプロイ（デフォルトVPCなし）"
fi

echo ""
echo "=== デプロイ完了 ==="
echo ""
echo "Lambda Standard ARN:"
echo "  $LAMBDA_STANDARD_ARN"
echo ""
echo "Lambda VPC ARN:"
echo "  $LAMBDA_VPC_ARN"
echo ""

# テスト用の環境変数ファイル作成
cat > test/.env <<EOF
LAMBDA_STANDARD_ARN=$LAMBDA_STANDARD_ARN
LAMBDA_VPC_ARN=$LAMBDA_VPC_ARN
AWS_REGION=$REGION
VPC_LAMBDA_DEPLOYED=$VPC_LAMBDA_DEPLOYED
EOF

echo "環境変数を test/.env に保存しました"
echo ""
echo "=== 次のステップ ==="
echo "1. Lambda直接テスト: cd test && bash test_lambda_direct.sh"
echo "2. Responses APIテスト: cd test && python test_responses_api.py"
echo ""
echo "⚠️  セキュリティ情報:"
echo "- すべてのLambdaはIAM認証が必要（インターネット露出なし）"
echo "- AWS CLI認証でアクセス可能"
echo "- Function URLは使用していません（セキュア）"
