#!/bin/bash
# CDKデプロイ + Code Serverセットアップ統合スクリプト

set -e

# 色の定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ヘルプ表示
usage() {
    cat << EOF
CDKデプロイ + Code Serverセットアップ統合スクリプト

使用方法: $0 [OPTIONS]

Options:
    -r, --region REGION                  AWSリージョン (デフォルト: sa-east-1)
    -t, --instance-type TYPE             インスタンスタイプ (デフォルト: trn2.3xlarge)
    --use-capacity-block                 Capacity Blockを使用
    --capacity-reservation-id ID         Capacity Reservation ID
    --subnet-id ID                       Subnet ID
    --volume-size SIZE                   EBSボリュームサイズ (GB, デフォルト: 500)
    --allowed-ip IP                      許可するIPアドレス (CIDR形式、例: 203.0.113.10/32)
    --skip-setup                         Code Serverセットアップをスキップ
    --show-info                          デプロイ済みスタックの情報を表示
    --destroy                            スタックを削除
    -h, --help                           このヘルプを表示

例:
    # 基本的なデプロイ
    $0

    # Capacity Blockを使用
    $0 --use-capacity-block \\
       --capacity-reservation-id cr-06670284d2d99ffea \\
       --subnet-id subnet-03bc087b5513f8134

    # インスタンスタイプ指定
    $0 -t inf2.8xlarge

    # 特定IPからのアクセスを許可
    $0 --allowed-ip 203.0.113.10/32

    # デプロイ済みスタックの情報を表示
    $0 --show-info

    # スタック削除
    $0 --destroy
EOF
}

# デフォルト値
REGION="sa-east-1"
INSTANCE_TYPE="trn2.3xlarge"
USE_CAPACITY_BLOCK=false
CAPACITY_RESERVATION_ID=""
SUBNET_ID=""
VOLUME_SIZE="500"
ALLOWED_IP=""
SKIP_SETUP=false
SHOW_INFO=false
DESTROY=false
STACK_NAME="TorchNeuron-CDK"

# パラメータ解析
while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -t|--instance-type)
            INSTANCE_TYPE="$2"
            shift 2
            ;;
        --use-capacity-block)
            USE_CAPACITY_BLOCK=true
            shift
            ;;
        --capacity-reservation-id)
            CAPACITY_RESERVATION_ID="$2"
            USE_CAPACITY_BLOCK=true
            shift 2
            ;;
        --subnet-id)
            SUBNET_ID="$2"
            shift 2
            ;;
        --volume-size)
            VOLUME_SIZE="$2"
            shift 2
            ;;
        --allowed-ip)
            ALLOWED_IP="$2"
            shift 2
            ;;
        --skip-setup)
            SKIP_SETUP=true
            shift
            ;;
        --show-info)
            SHOW_INFO=true
            shift
            ;;
        --destroy)
            DESTROY=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}エラー: 不明なオプション: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

# スクリプトのディレクトリ取得
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "${BLUE}=========================================${NC}"
echo -e "${BLUE}CDK デプロイスクリプト${NC}"
echo -e "${BLUE}=========================================${NC}"
echo "プロジェクトディレクトリ: $PROJECT_DIR"
echo "リージョン: $REGION"
echo "インスタンスタイプ: $INSTANCE_TYPE"
echo "Capacity Block: $USE_CAPACITY_BLOCK"
if [[ "$USE_CAPACITY_BLOCK" == true ]]; then
    echo "  Capacity Reservation ID: $CAPACITY_RESERVATION_ID"
    echo "  Subnet ID: $SUBNET_ID"
fi
echo "ボリュームサイズ: ${VOLUME_SIZE}GB"
echo -e "${BLUE}=========================================${NC}"
echo ""

# スタック情報表示モード
if [[ "$SHOW_INFO" == true ]]; then
    echo -e "${BLUE}📊 スタック情報を取得中...${NC}"
    echo ""

    # スタック存在確認
    STACK_STATUS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null)

    if [[ -z "$STACK_STATUS" ]]; then
        echo -e "${RED}❌ スタック '$STACK_NAME' が見つかりません${NC}"
        echo "リージョン: $REGION"
        exit 1
    fi

    echo -e "${GREEN}スタック名: $STACK_NAME${NC}"
    echo "ステータス: $STACK_STATUS"
    echo "リージョン: $REGION"
    echo ""

    # インスタンスID取得
    INSTANCE_ID=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' \
        --output text)

    # Public DNS取得
    PUBLIC_DNS=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`InstancePublicDnsName`].OutputValue' \
        --output text)

    # Public IP取得
    PUBLIC_IP=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`InstancePublicIp`].OutputValue' \
        --output text)

    # Secret ARN取得
    SECRET_ARN=$(aws secretsmanager list-secrets \
        --region "$REGION" \
        --query "SecretList[?contains(Name, 'CodeServerPassword')].ARN | [0]" \
        --output text)

    echo -e "${GREEN}📋 インスタンス情報:${NC}"
    echo "  Instance ID: ${INSTANCE_ID:-'N/A'}"
    echo "  Public DNS: ${PUBLIC_DNS:-'N/A'}"
    echo "  Public IP: ${PUBLIC_IP:-'N/A'}"
    echo ""

    # インスタンスが存在する場合、詳細情報を取得
    if [[ -n "$INSTANCE_ID" ]] && [[ "$INSTANCE_ID" != "None" ]]; then
        echo -e "${BLUE}🔍 インスタンス詳細情報:${NC}"

        # インスタンス詳細を一度に取得
        INSTANCE_INFO=$(aws ec2 describe-instances \
            --instance-ids "$INSTANCE_ID" \
            --region "$REGION" \
            --output json 2>/dev/null)

        # Reservations配列が空でないか確認
        RESERVATIONS_COUNT=$(echo "$INSTANCE_INFO" | jq '.Reservations | length')

        if [[ "$RESERVATIONS_COUNT" -gt 0 ]]; then
            INSTANCE_STATE=$(echo "$INSTANCE_INFO" | jq -r '.Reservations[0].Instances[0].State.Name')
            INSTANCE_TYPE_INFO=$(echo "$INSTANCE_INFO" | jq -r '.Reservations[0].Instances[0].InstanceType')
            AZ=$(echo "$INSTANCE_INFO" | jq -r '.Reservations[0].Instances[0].Placement.AvailabilityZone')
            LAUNCH_TIME=$(echo "$INSTANCE_INFO" | jq -r '.Reservations[0].Instances[0].LaunchTime')

            echo "  State: ${INSTANCE_STATE:-'N/A'}"
            echo "  Instance Type: ${INSTANCE_TYPE_INFO:-'N/A'}"
            echo "  Availability Zone: ${AZ:-'N/A'}"
            echo "  Launch Time: ${LAUNCH_TIME:-'N/A'}"
        else
            echo -e "  ${YELLOW}⚠️  インスタンスが見つかりません（終了済みの可能性）${NC}"
        fi
        echo ""
    fi

    echo -e "${GREEN}🔐 接続情報:${NC}"
    if [[ -n "$PUBLIC_DNS" ]] && [[ "$PUBLIC_DNS" != "None" ]]; then
        echo "  Code Server URL: http://$PUBLIC_DNS"
    fi

    if [[ -n "$SECRET_ARN" ]] && [[ "$SECRET_ARN" != "None" ]]; then
        echo ""
        echo "  パスワード取得コマンド:"
        echo "    aws secretsmanager get-secret-value --secret-id $SECRET_ARN --region $REGION --query 'SecretString' --output text"
    fi

    if [[ -n "$INSTANCE_ID" ]] && [[ "$INSTANCE_ID" != "None" ]]; then
        echo ""
        echo "  SSM接続コマンド:"
        echo "    aws ssm start-session --target $INSTANCE_ID --region $REGION"
    fi

    echo ""
    exit 0
fi

# スタック削除モード
if [[ "$DESTROY" == true ]]; then
    echo -e "${YELLOW}⚠️  スタックを削除します${NC}"
    read -p "本当に削除しますか？ (yes/no): " -r
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo "キャンセルしました"
        exit 0
    fi

    cd "$PROJECT_DIR"
    AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" npm run destroy
    exit 0
fi

# CDKパラメータ構築
CDK_PARAMS=()
if [[ "$USE_CAPACITY_BLOCK" == true ]]; then
    CDK_PARAMS+=("-c" "useCapacityBlock=true")

    # Parameter Storeからパラメータを読み込み（未指定の場合）
    if [[ -z "$CAPACITY_RESERVATION_ID" ]]; then
        echo -e "${BLUE}📥 Parameter Storeから Capacity Reservation ID を読み込み中...${NC}"
        CAPACITY_RESERVATION_ID=$(aws ssm get-parameter \
            --name "/capacity-block/${REGION}/reservation-id" \
            --region "$REGION" \
            --query 'Parameter.Value' \
            --output text 2>/dev/null)

        if [[ -n "$CAPACITY_RESERVATION_ID" ]] && [[ "$CAPACITY_RESERVATION_ID" != "None" ]]; then
            echo "  読み込み成功: $CAPACITY_RESERVATION_ID"
        else
            echo -e "${YELLOW}  ⚠️  Parameter Storeに見つかりません${NC}"
        fi
    fi

    if [[ -z "$SUBNET_ID" ]]; then
        echo -e "${BLUE}📥 Parameter Storeから Subnet ID を読み込み中...${NC}"
        SUBNET_ID=$(aws ssm get-parameter \
            --name "/capacity-block/${REGION}/subnet-id" \
            --region "$REGION" \
            --query 'Parameter.Value' \
            --output text 2>/dev/null)

        if [[ -n "$SUBNET_ID" ]] && [[ "$SUBNET_ID" != "None" ]]; then
            echo "  読み込み成功: $SUBNET_ID"
        else
            echo -e "${YELLOW}  ⚠️  Parameter Storeに見つかりません${NC}"
        fi
    fi

    if [[ -n "$CAPACITY_RESERVATION_ID" ]]; then
        CDK_PARAMS+=("-c" "capacityReservationId=$CAPACITY_RESERVATION_ID")
    fi
    if [[ -n "$SUBNET_ID" ]]; then
        CDK_PARAMS+=("-c" "subnetId=$SUBNET_ID")
    fi
fi

if [[ -n "$INSTANCE_TYPE" ]]; then
    CDK_PARAMS+=("-c" "instanceType=$INSTANCE_TYPE")
fi

if [[ -n "$VOLUME_SIZE" ]]; then
    CDK_PARAMS+=("-c" "volumeSize=$VOLUME_SIZE")
fi

# ビルド
echo -e "${BLUE}🔨 プロジェクトをビルド中...${NC}"
cd "$PROJECT_DIR"
npm run build

# デプロイ
echo ""
echo -e "${BLUE}🚀 CDKスタックをデプロイ中...${NC}"
AWS_REGION="$REGION" AWS_DEFAULT_REGION="$REGION" npm run deploy -- "${CDK_PARAMS[@]}" --require-approval never

# デプロイ成功確認
if [[ $? -ne 0 ]]; then
    echo -e "${RED}❌ CDKデプロイに失敗しました${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ CDKデプロイが完了しました${NC}"

# スタック情報取得
echo ""
echo -e "${BLUE}📊 スタック情報を取得中...${NC}"

INSTANCE_ID=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' \
    --output text)

PUBLIC_DNS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK_NAME" \
    --region "$REGION" \
    --query 'Stacks[0].Outputs[?OutputKey==`InstancePublicDnsName`].OutputValue' \
    --output text)

SECRET_ARN=$(aws secretsmanager list-secrets \
    --region "$REGION" \
    --query "SecretList[?contains(Name, 'CodeServerPassword')].ARN | [0]" \
    --output text)

echo "インスタンスID: $INSTANCE_ID"
echo "Public DNS: $PUBLIC_DNS"
echo "Secret ARN: $SECRET_ARN"

# セキュリティグループルール追加
if [[ -n "$ALLOWED_IP" ]]; then
    echo ""
    echo -e "${BLUE}🔒 セキュリティグループルールを追加中...${NC}"

    # セキュリティグループID取得
    SECURITY_GROUP_ID=$(aws ec2 describe-instances \
        --instance-ids "$INSTANCE_ID" \
        --region "$REGION" \
        --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' \
        --output text)

    if [[ -n "$SECURITY_GROUP_ID" ]]; then
        echo "Security Group ID: $SECURITY_GROUP_ID"
        echo "許可IP: $ALLOWED_IP"

        # ルール追加（既に存在する場合はエラーを無視）
        aws ec2 authorize-security-group-ingress \
            --group-id "$SECURITY_GROUP_ID" \
            --region "$REGION" \
            --ip-permissions IpProtocol=tcp,FromPort=80,ToPort=80,IpRanges="[{CidrIp=$ALLOWED_IP,Description='User access'}]" \
            2>/dev/null && echo -e "${GREEN}✅ セキュリティグループルール追加成功${NC}" || echo -e "${YELLOW}⚠️  ルールは既に存在するか、追加できませんでした${NC}"
    else
        echo -e "${YELLOW}⚠️  セキュリティグループIDが取得できませんでした${NC}"
    fi
fi

# Code Serverセットアップ
if [[ "$SKIP_SETUP" == false ]]; then
    echo ""
    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE}Code Server セットアップ${NC}"
    echo -e "${BLUE}=========================================${NC}"
    echo ""

    # セットアップスクリプト実行
    bash "$SCRIPT_DIR/setup-code-server.sh" \
        -i "$INSTANCE_ID" \
        -r "$REGION" \
        -s "$SECRET_ARN"

    if [[ $? -ne 0 ]]; then
        echo -e "${RED}❌ Code Serverセットアップに失敗しました${NC}"
        echo -e "${YELLOW}手動でセットアップするには:${NC}"
        echo "  bash $SCRIPT_DIR/setup-code-server.sh -i $INSTANCE_ID -r $REGION -s $SECRET_ARN --wait"
        exit 1
    fi
else
    echo ""
    echo -e "${YELLOW}ℹ️  Code Serverセットアップをスキップしました${NC}"
    echo "手動でセットアップするには:"
    echo "  bash $SCRIPT_DIR/setup-code-server.sh -i $INSTANCE_ID -r $REGION -s $SECRET_ARN --wait"
fi

# 完了メッセージ
echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}🎉 全ての処理が完了しました！${NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo "📋 接続情報:"
echo "  Instance ID: $INSTANCE_ID"
echo "  Public DNS: $PUBLIC_DNS"
echo ""
echo "🌐 Code Server URL:"
echo "  http://$PUBLIC_DNS"
echo ""
echo "🔐 パスワード取得:"
echo "  aws secretsmanager get-secret-value --secret-id $SECRET_ARN --region $REGION --query 'SecretString' --output text"
echo ""
echo "🔌 SSM接続:"
echo "  aws ssm start-session --target $INSTANCE_ID --region $REGION"
echo ""
echo -e "${GREEN}=========================================${NC}"
