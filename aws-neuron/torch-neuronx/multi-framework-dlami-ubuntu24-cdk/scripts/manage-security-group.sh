#!/bin/bash

# セキュリティグループ管理スクリプト
# IPアドレスの追加・削除・一覧表示を行う

set -euo pipefail

# カラーコード
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# デフォルト値
REGION="sa-east-1"
STACK_NAME="TorchNeuron-CDK"
PORT=80
PROTOCOL="tcp"
DESCRIPTION=""

# 使用方法
usage() {
    cat <<EOF
セキュリティグループ管理スクリプト

使用方法: $0 <COMMAND> [OPTIONS]

コマンド:
    add         IPアドレスを追加
    remove      IPアドレスを削除
    list        現在のルールを表示
    show-id     セキュリティグループIDを表示

オプション:
    -i, --ip IP              IPアドレス (CIDR形式、例: 106.72.10.225/32)
    -r, --region REGION      AWSリージョン (デフォルト: sa-east-1)
    -s, --stack-name NAME    スタック名 (デフォルト: TorchNeuron-CDK)
    -g, --group-id ID        セキュリティグループID (自動検出される場合は省略可)
    -p, --port PORT          ポート番号 (デフォルト: 80)
    --protocol PROTOCOL      プロトコル (デフォルト: tcp)
    -d, --description DESC   ルールの説明
    -h, --help               このヘルプを表示

例:
    # IPアドレスを追加
    $0 add -i 106.72.10.225/32 -r sa-east-1

    # IPアドレスを削除
    $0 remove -i 106.72.10.225/32 -r sa-east-1

    # 現在のルールを表示
    $0 list -r sa-east-1

    # セキュリティグループIDを表示
    $0 show-id -r sa-east-1

    # 特定のポートに追加
    $0 add -i 203.0.113.10/32 -p 443 --protocol tcp

    # セキュリティグループIDを直接指定
    $0 add -i 106.72.10.225/32 -g sg-xxxxxxxxx
EOF
    exit 1
}

# セキュリティグループIDを取得
get_security_group_id() {
    local region=$1
    local stack_name=$2
    local group_id=""

    echo -e "${BLUE}🔍 セキュリティグループIDを取得中...${NC}" >&2

    # スタックからインスタンスIDを取得
    local instance_id=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$region" \
        --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' \
        --output text 2>/dev/null)

    if [[ -z "$instance_id" || "$instance_id" == "None" ]]; then
        echo -e "${RED}エラー: スタック $stack_name からインスタンスIDを取得できませんでした${NC}" >&2
        exit 1
    fi

    # インスタンスからセキュリティグループIDを取得
    group_id=$(aws ec2 describe-instances \
        --instance-ids "$instance_id" \
        --region "$region" \
        --query 'Reservations[0].Instances[0].SecurityGroups[0].GroupId' \
        --output text 2>/dev/null)

    if [[ -z "$group_id" || "$group_id" == "None" ]]; then
        echo -e "${RED}エラー: セキュリティグループIDを取得できませんでした${NC}" >&2
        exit 1
    fi

    echo -e "${GREEN}  取得成功: $group_id${NC}" >&2
    echo "$group_id"
}

# IPアドレスを追加
add_ip() {
    local group_id=$1
    local ip=$2
    local region=$3
    local port=$4
    local protocol=$5
    local description=$6

    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE}IPアドレス追加${NC}"
    echo -e "${BLUE}=========================================${NC}"
    echo "セキュリティグループID: $group_id"
    echo "IPアドレス: $ip"
    echo "ポート: $port"
    echo "プロトコル: $protocol"
    echo "リージョン: $region"
    if [[ -n "$description" ]]; then
        echo "説明: $description"
    fi
    echo -e "${BLUE}=========================================${NC}"
    echo ""

    echo -e "${BLUE}✚ ルールを追加中...${NC}"

    local result
    if [[ -n "$description" ]]; then
        # 説明がある場合は--ip-permissions形式を使用
        result=$(aws ec2 authorize-security-group-ingress \
            --group-id "$group_id" \
            --ip-permissions "IpProtocol=$protocol,FromPort=$port,ToPort=$port,IpRanges=[{CidrIp=$ip,Description='$description'}]" \
            --region "$region" 2>&1)
    else
        # 説明がない場合はシンプルな形式を使用
        result=$(aws ec2 authorize-security-group-ingress \
            --group-id "$group_id" \
            --protocol "$protocol" \
            --port "$port" \
            --cidr "$ip" \
            --region "$region" 2>&1)
    fi

    echo ""
    if echo "$result" | grep -q "InvalidPermission.Duplicate"; then
        echo -e "${YELLOW}⚠️  ルールは既に存在しています${NC}"
    elif echo "$result" | grep -q "error\|Error"; then
        echo -e "${RED}❌ エラー: $result${NC}"
        exit 1
    else
        echo -e "${GREEN}✅ IPアドレスを追加しました${NC}"
    fi
}

# IPアドレスを削除
remove_ip() {
    local group_id=$1
    local ip=$2
    local region=$3
    local port=$4
    local protocol=$5

    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE}IPアドレス削除${NC}"
    echo -e "${BLUE}=========================================${NC}"
    echo "セキュリティグループID: $group_id"
    echo "IPアドレス: $ip"
    echo "ポート: $port"
    echo "プロトコル: $protocol"
    echo "リージョン: $region"
    echo -e "${BLUE}=========================================${NC}"
    echo ""

    echo -e "${YELLOW}⚠️  ルールを削除します${NC}"
    read -p "続行しますか？ (yes/no): " -r
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo "キャンセルしました"
        exit 0
    fi

    echo ""
    echo -e "${BLUE}✖ ルールを削除中...${NC}"
    if aws ec2 revoke-security-group-ingress \
        --group-id "$group_id" \
        --protocol "$protocol" \
        --port "$port" \
        --cidr "$ip" \
        --region "$region" 2>&1; then
        echo ""
        echo -e "${GREEN}✅ IPアドレスを削除しました${NC}"
    else
        echo ""
        echo -e "${RED}❌ ルールの削除に失敗しました${NC}"
        exit 1
    fi
}

# ルール一覧を表示
list_rules() {
    local group_id=$1
    local region=$2

    echo -e "${BLUE}=========================================${NC}"
    echo -e "${BLUE}セキュリティグループルール一覧${NC}"
    echo -e "${BLUE}=========================================${NC}"
    echo "セキュリティグループID: $group_id"
    echo "リージョン: $region"
    echo -e "${BLUE}=========================================${NC}"
    echo ""

    # インバウンドルールを取得
    local rules=$(aws ec2 describe-security-groups \
        --group-ids "$group_id" \
        --region "$region" \
        --query 'SecurityGroups[0].IpPermissions' \
        --output json)

    echo -e "${GREEN}📋 インバウンドルール:${NC}"
    echo ""

    # jqで整形して表示
    echo "$rules" | jq -r '.[] |
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "プロトコル: \(.IpProtocol)",
        "ポート範囲: \(if .FromPort then "\(.FromPort)-\(.ToPort)" else "All" end)",
        (if .IpRanges then .IpRanges[] | "  CIDR: \(.CidrIp)\(if .Description then " (\(.Description))" else "" end)" else empty end),
        (if .Ipv6Ranges then .Ipv6Ranges[] | "  IPv6: \(.CidrIpv6)\(if .Description then " (\(.Description))" else "" end)" else empty end),
        (if .UserIdGroupPairs then .UserIdGroupPairs[] | "  SG: \(.GroupId)\(if .Description then " (\(.Description))" else "" end)" else empty end)
    '

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# セキュリティグループIDを表示
show_id() {
    local group_id=$1
    local region=$2

    echo -e "${GREEN}セキュリティグループID: $group_id${NC}"
    echo ""
    echo -e "${YELLOW}💡 このIDを使用してルールを管理できます:${NC}"
    echo "  # IPを追加"
    echo "  $0 add -i YOUR_IP/32 -g $group_id -r $region"
    echo ""
    echo "  # IPを削除"
    echo "  $0 remove -i YOUR_IP/32 -g $group_id -r $region"
    echo ""
    echo "  # ルール一覧"
    echo "  $0 list -g $group_id -r $region"
}

# 引数パース
COMMAND=""
IP=""
GROUP_ID=""

if [[ $# -eq 0 ]]; then
    usage
fi

COMMAND=$1
shift

while [[ $# -gt 0 ]]; do
    case $1 in
        -i|--ip)
            IP="$2"
            shift 2
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -s|--stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        -g|--group-id)
            GROUP_ID="$2"
            shift 2
            ;;
        -p|--port)
            PORT="$2"
            shift 2
            ;;
        --protocol)
            PROTOCOL="$2"
            shift 2
            ;;
        -d|--description)
            DESCRIPTION="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}エラー: 不明なオプション: $1${NC}"
            usage
            ;;
    esac
done

# セキュリティグループIDを取得（指定されていない場合）
if [[ -z "$GROUP_ID" ]]; then
    GROUP_ID=$(get_security_group_id "$REGION" "$STACK_NAME")
fi

# コマンド実行
case $COMMAND in
    add)
        if [[ -z "$IP" ]]; then
            echo -e "${RED}エラー: --ip を指定してください${NC}"
            usage
        fi
        # /32が含まれていない場合は追加
        if [[ ! "$IP" =~ /[0-9]+$ ]]; then
            IP="$IP/32"
            echo -e "${YELLOW}⚠️  CIDR表記に変換しました: $IP${NC}"
        fi
        add_ip "$GROUP_ID" "$IP" "$REGION" "$PORT" "$PROTOCOL" "$DESCRIPTION"
        ;;
    remove)
        if [[ -z "$IP" ]]; then
            echo -e "${RED}エラー: --ip を指定してください${NC}"
            usage
        fi
        # /32が含まれていない場合は追加
        if [[ ! "$IP" =~ /[0-9]+$ ]]; then
            IP="$IP/32"
            echo -e "${YELLOW}⚠️  CIDR表記に変換しました: $IP${NC}"
        fi
        remove_ip "$GROUP_ID" "$IP" "$REGION" "$PORT" "$PROTOCOL"
        ;;
    list)
        list_rules "$GROUP_ID" "$REGION"
        ;;
    show-id)
        show_id "$GROUP_ID" "$REGION"
        ;;
    *)
        echo -e "${RED}エラー: 不明なコマンド: $COMMAND${NC}"
        usage
        ;;
esac
