#!/bin/bash
# Capacity Block管理スクリプト

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
Capacity Block管理スクリプト

使用方法: $0 [COMMAND] [OPTIONS]

Commands:
    search                               利用可能なCapacity Blockを検索
    purchase                             Capacity Blockを購入
    list                                 購入済みCapacity Blockを一覧表示
    describe                             Capacity Blockの詳細情報を表示
    cancel                               Capacity Blockをキャンセル
    save-params                          パラメータをParameter Storeに保存
    load-params                          Parameter Storeからパラメータを読み込み

Options:
    -r, --region REGION                  AWSリージョン (デフォルト: sa-east-1)
    -t, --instance-type TYPE             インスタンスタイプ (デフォルト: trn2.3xlarge)
    -c, --instance-count COUNT           インスタンス数 (デフォルト: 1)
    -d, --duration HOURS                 期間 (時間、デフォルト: 1)
    --start-time TIME                    開始時刻 (ISO8601形式、例: 2026-01-27T00:00:00Z)
    --offering-id ID                     Capacity Block Offering ID (購入時必須)
    --reservation-id ID                  Capacity Reservation ID (詳細表示・キャンセル時必須)
    --subnet-id ID                       Subnet ID (save-params時に使用)
    -h, --help                           このヘルプを表示

例:
    # 利用可能なCapacity Blockを検索
    $0 search -t trn2.3xlarge -d 1

    # 特定のOfferingを購入
    $0 purchase --offering-id cbr-a1234567890abcdef --start-time 2026-01-27T00:00:00Z

    # 購入済みCapacity Blockを一覧表示
    $0 list

    # Capacity Blockの詳細情報を表示
    $0 describe --reservation-id cr-06670284d2d99ffea

    # Capacity Blockをキャンセル
    $0 cancel --reservation-id cr-06670284d2d99ffea

    # パラメータをParameter Storeに保存
    $0 save-params --reservation-id cr-06670284d2d99ffea --subnet-id subnet-03bc087b5513f8134

    # Parameter Storeからパラメータを読み込み
    $0 load-params
EOF
}

# デフォルト値
COMMAND=""
REGION="sa-east-1"
INSTANCE_TYPE="trn2.3xlarge"
INSTANCE_COUNT="1"
DURATION="1"
START_TIME=""
OFFERING_ID=""
RESERVATION_ID=""
SUBNET_ID=""

# Parameter Store キー名
PARAM_PREFIX="/capacity-block"

# コマンド取得
if [[ $# -gt 0 ]] && [[ ! "$1" =~ ^- ]]; then
    COMMAND="$1"
    shift
fi

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
        -c|--instance-count)
            INSTANCE_COUNT="$2"
            shift 2
            ;;
        -d|--duration)
            DURATION="$2"
            shift 2
            ;;
        --start-time)
            START_TIME="$2"
            shift 2
            ;;
        --offering-id)
            OFFERING_ID="$2"
            shift 2
            ;;
        --reservation-id)
            RESERVATION_ID="$2"
            shift 2
            ;;
        --subnet-id)
            SUBNET_ID="$2"
            shift 2
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

# コマンド実行
case "$COMMAND" in
    search)
        echo -e "${BLUE}=========================================${NC}"
        echo -e "${BLUE}Capacity Block 検索${NC}"
        echo -e "${BLUE}=========================================${NC}"
        echo "リージョン: $REGION"
        echo "インスタンスタイプ: $INSTANCE_TYPE"
        echo "インスタンス数: $INSTANCE_COUNT"
        echo "期間: ${DURATION}時間"
        if [[ -n "$START_TIME" ]]; then
            echo "開始時刻: $START_TIME"
        fi
        echo -e "${BLUE}=========================================${NC}"
        echo ""

        # 検索パラメータ構築
        SEARCH_PARAMS=(
            --instance-type "$INSTANCE_TYPE"
            --instance-count "$INSTANCE_COUNT"
            --capacity-duration-hours "$DURATION"
            --region "$REGION"
        )

        # 開始時刻が指定されている場合
        if [[ -n "$START_TIME" ]]; then
            # 終了時刻を計算 (開始時刻 + 期間)
            if command -v date &> /dev/null; then
                if date --version &> /dev/null 2>&1; then
                    # GNU date
                    END_TIME=$(date -u -d "$START_TIME + $DURATION hours" +"%Y-%m-%dT%H:%M:%SZ")
                else
                    # BSD date (macOS)
                    END_TIME=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$START_TIME" -v+${DURATION}H +"%Y-%m-%dT%H:%M:%SZ")
                fi
                SEARCH_PARAMS+=(--start-date-range "$START_TIME" --end-date-range "$END_TIME")
            fi
        fi

        echo -e "${BLUE}🔍 利用可能なCapacity Blockを検索中...${NC}"
        echo ""

        # 検索実行
        OFFERINGS=$(aws ec2 describe-capacity-block-offerings "${SEARCH_PARAMS[@]}" --output json)

        # 結果表示
        OFFERING_COUNT=$(echo "$OFFERINGS" | jq '.CapacityBlockOfferings | length')

        if [[ "$OFFERING_COUNT" -eq 0 ]]; then
            echo -e "${YELLOW}⚠️  利用可能なCapacity Blockが見つかりませんでした${NC}"
            exit 0
        fi

        echo -e "${GREEN}✅ ${OFFERING_COUNT}件のCapacity Blockが見つかりました${NC}"
        echo ""

        # 各Offeringを表示
        echo "$OFFERINGS" | jq -r '.CapacityBlockOfferings[] |
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n" +
            "Offering ID: \(.CapacityBlockOfferingId)\n" +
            "開始時刻: \(.StartDate)\n" +
            "終了時刻: \(.EndDate)\n" +
            "期間: \(.CapacityBlockDurationHours)時間\n" +
            "アベイラビリティゾーン: \(.AvailabilityZone)\n" +
            "インスタンスタイプ: \(.InstanceType)\n" +
            "インスタンス数: \(.InstanceCount)\n" +
            "価格: $\(.UpfrontFee) (\(.CurrencyCode))\n" +
            "テナンシー: \(.Tenancy)\n"'

        echo ""
        echo -e "${YELLOW}💡 購入するには:${NC}"
        echo "  $0 purchase --offering-id <OFFERING_ID> --start-time <START_TIME>"
        ;;

    purchase)
        if [[ -z "$OFFERING_ID" ]]; then
            echo -e "${RED}エラー: --offering-id を指定してください${NC}"
            usage
            exit 1
        fi

        if [[ -z "$START_TIME" ]]; then
            echo -e "${RED}エラー: --start-time を指定してください${NC}"
            usage
            exit 1
        fi

        echo -e "${BLUE}=========================================${NC}"
        echo -e "${BLUE}Capacity Block 購入${NC}"
        echo -e "${BLUE}=========================================${NC}"
        echo "Offering ID: $OFFERING_ID"
        echo "開始時刻: $START_TIME"
        echo "リージョン: $REGION"
        echo -e "${BLUE}=========================================${NC}"
        echo ""

        echo -e "${YELLOW}⚠️  Capacity Blockを購入します${NC}"
        read -p "続行しますか？ (yes/no): " -r
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            echo "キャンセルしました"
            exit 0
        fi

        echo ""
        echo -e "${BLUE}💳 購入処理中...${NC}"

        # 購入実行
        RESULT=$(aws ec2 purchase-capacity-block \
            --capacity-block-offering-id "$OFFERING_ID" \
            --instance-platform Linux/UNIX \
            --region "$REGION" \
            --output json)

        CAPACITY_RESERVATION_ID=$(echo "$RESULT" | jq -r '.CapacityReservation.CapacityReservationId')
        AVAILABILITY_ZONE=$(echo "$RESULT" | jq -r '.CapacityReservation.AvailabilityZone')

        echo ""
        echo -e "${GREEN}✅ Capacity Blockの購入が完了しました！${NC}"
        echo ""
        echo -e "${GREEN}📋 購入情報:${NC}"
        echo "  Capacity Reservation ID: $CAPACITY_RESERVATION_ID"
        echo "  Availability Zone: $AVAILABILITY_ZONE"
        echo ""

        # Subnet ID取得（同じAZの最初のサブネット）
        DETECTED_SUBNET_ID=$(aws ec2 describe-subnets \
            --region "$REGION" \
            --filters "Name=availability-zone,Values=$AVAILABILITY_ZONE" \
            --query 'Subnets[0].SubnetId' \
            --output text 2>/dev/null)

        if [[ -n "$DETECTED_SUBNET_ID" ]] && [[ "$DETECTED_SUBNET_ID" != "None" ]]; then
            echo "  Subnet ID (検出): $DETECTED_SUBNET_ID"
            echo ""
        fi

        # Parameter Storeに保存するか確認
        echo -e "${YELLOW}💾 パラメータをParameter Storeに保存しますか？${NC}"
        read -p "(yes/no): " -r
        if [[ $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            # Subnet IDを使用
            SAVE_SUBNET_ID="${DETECTED_SUBNET_ID:-$SUBNET_ID}"

            if [[ -z "$SAVE_SUBNET_ID" ]]; then
                echo ""
                echo -e "${YELLOW}⚠️  Subnet IDが見つかりません。手動で指定してください:${NC}"
                read -p "Subnet ID: " SAVE_SUBNET_ID
            fi

            # Parameter Storeに保存
            $0 save-params \
                --reservation-id "$CAPACITY_RESERVATION_ID" \
                --subnet-id "$SAVE_SUBNET_ID" \
                -r "$REGION"
        fi

        echo ""
        echo -e "${YELLOW}💡 詳細情報を確認するには:${NC}"
        echo "  $0 describe --reservation-id $CAPACITY_RESERVATION_ID"
        echo ""
        echo -e "${YELLOW}💡 デプロイするには:${NC}"
        echo "  cd $(dirname "$(dirname "$(realpath "$0")")")"
        echo "  bash scripts/deploy.sh --use-capacity-block -r $REGION"
        ;;

    list)
        echo -e "${BLUE}=========================================${NC}"
        echo -e "${BLUE}購入済み Capacity Block 一覧${NC}"
        echo -e "${BLUE}=========================================${NC}"
        echo "リージョン: $REGION"
        echo -e "${BLUE}=========================================${NC}"
        echo ""

        # 一覧取得
        RESERVATIONS=$(aws ec2 describe-capacity-reservations \
            --region "$REGION" \
            --filters "Name=instance-type,Values=$INSTANCE_TYPE" \
            --output json)

        RESERVATION_COUNT=$(echo "$RESERVATIONS" | jq '.CapacityReservations | length')

        if [[ "$RESERVATION_COUNT" -eq 0 ]]; then
            echo -e "${YELLOW}⚠️  購入済みのCapacity Blockが見つかりませんでした${NC}"
            exit 0
        fi

        echo -e "${GREEN}✅ ${RESERVATION_COUNT}件のCapacity Blockが見つかりました${NC}"
        echo ""

        # 各Reservationを表示
        echo "$RESERVATIONS" | jq -r '.CapacityReservations[] |
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n" +
            "Reservation ID: \(.CapacityReservationId)\n" +
            "ステータス: \(.State)\n" +
            "インスタンスタイプ: \(.InstanceType)\n" +
            "インスタンス数: \(.TotalInstanceCount)\n" +
            "利用可能数: \(.AvailableInstanceCount)\n" +
            "アベイラビリティゾーン: \(.AvailabilityZone)\n" +
            "開始時刻: \(.StartDate // "N/A")\n" +
            "終了時刻: \(.EndDate // "N/A")\n" +
            "作成日時: \(.CreateDate)\n"'

        echo ""
        echo -e "${YELLOW}💡 詳細情報を確認するには:${NC}"
        echo "  $0 describe --reservation-id <RESERVATION_ID>"
        ;;

    describe)
        if [[ -z "$RESERVATION_ID" ]]; then
            echo -e "${RED}エラー: --reservation-id を指定してください${NC}"
            usage
            exit 1
        fi

        echo -e "${BLUE}=========================================${NC}"
        echo -e "${BLUE}Capacity Block 詳細情報${NC}"
        echo -e "${BLUE}=========================================${NC}"
        echo "Reservation ID: $RESERVATION_ID"
        echo "リージョン: $REGION"
        echo -e "${BLUE}=========================================${NC}"
        echo ""

        # 詳細情報取得
        RESERVATION=$(aws ec2 describe-capacity-reservations \
            --capacity-reservation-ids "$RESERVATION_ID" \
            --region "$REGION" \
            --output json)

        RESERVATION_EXISTS=$(echo "$RESERVATION" | jq '.CapacityReservations | length')

        if [[ "$RESERVATION_EXISTS" -eq 0 ]]; then
            echo -e "${RED}❌ Capacity Reservation ID '$RESERVATION_ID' が見つかりません${NC}"
            exit 1
        fi

        # JSON整形表示
        echo "$RESERVATION" | jq -r '.CapacityReservations[0] |
            "📋 基本情報\n" +
            "  Reservation ID: \(.CapacityReservationId)\n" +
            "  ARN: \(.CapacityReservationArn)\n" +
            "  ステータス: \(.State)\n" +
            "  タイプ: \(.InstanceMatchCriteria)\n" +
            "\n" +
            "🖥️  インスタンス情報\n" +
            "  インスタンスタイプ: \(.InstanceType)\n" +
            "  プラットフォーム: \(.InstancePlatform)\n" +
            "  アベイラビリティゾーン: \(.AvailabilityZone)\n" +
            "  テナンシー: \(.Tenancy)\n" +
            "\n" +
            "📊 キャパシティ情報\n" +
            "  総インスタンス数: \(.TotalInstanceCount)\n" +
            "  利用可能数: \(.AvailableInstanceCount)\n" +
            "\n" +
            "📅 期間情報\n" +
            "  作成日時: \(.CreateDate)\n" +
            "  開始時刻: \(.StartDate // "N/A")\n" +
            "  終了時刻: \(.EndDate // "N/A")\n" +
            "  終了タイプ: \(.EndDateType)\n"'

        # タグ情報
        TAGS=$(echo "$RESERVATION" | jq -r '.CapacityReservations[0].Tags[]? | "  \(.Key): \(.Value)"')
        if [[ -n "$TAGS" ]]; then
            echo ""
            echo "🏷️  タグ"
            echo "$TAGS"
        fi

        echo ""
        ;;

    cancel)
        if [[ -z "$RESERVATION_ID" ]]; then
            echo -e "${RED}エラー: --reservation-id を指定してください${NC}"
            usage
            exit 1
        fi

        echo -e "${BLUE}=========================================${NC}"
        echo -e "${BLUE}Capacity Block キャンセル${NC}"
        echo -e "${BLUE}=========================================${NC}"
        echo "Reservation ID: $RESERVATION_ID"
        echo "リージョン: $REGION"
        echo -e "${BLUE}=========================================${NC}"
        echo ""

        echo -e "${YELLOW}⚠️  Capacity Blockをキャンセルします${NC}"
        echo -e "${YELLOW}    注意: キャンセル料が発生する可能性があります${NC}"
        read -p "本当にキャンセルしますか？ (yes/no): " -r
        if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
            echo "キャンセル処理を中止しました"
            exit 0
        fi

        echo ""
        echo -e "${BLUE}🗑️  キャンセル処理中...${NC}"

        # キャンセル実行
        aws ec2 cancel-capacity-reservation \
            --capacity-reservation-id "$RESERVATION_ID" \
            --region "$REGION" \
            --output json > /dev/null

        echo ""
        echo -e "${GREEN}✅ Capacity Blockのキャンセルが完了しました${NC}"
        ;;

    save-params)
        if [[ -z "$RESERVATION_ID" ]]; then
            echo -e "${RED}エラー: --reservation-id を指定してください${NC}"
            usage
            exit 1
        fi

        if [[ -z "$SUBNET_ID" ]]; then
            echo -e "${RED}エラー: --subnet-id を指定してください${NC}"
            usage
            exit 1
        fi

        echo -e "${BLUE}=========================================${NC}"
        echo -e "${BLUE}Parameter Store 保存${NC}"
        echo -e "${BLUE}=========================================${NC}"
        echo "Reservation ID: $RESERVATION_ID"
        echo "Subnet ID: $SUBNET_ID"
        echo "リージョン: $REGION"
        echo -e "${BLUE}=========================================${NC}"
        echo ""

        # 既存のパラメータをチェック
        EXISTING_RESERVATION=$(aws ssm get-parameter \
            --name "${PARAM_PREFIX}/${REGION}/reservation-id" \
            --region "$REGION" \
            --query 'Parameter.Value' \
            --output text 2>/dev/null)

        EXISTING_SUBNET=$(aws ssm get-parameter \
            --name "${PARAM_PREFIX}/${REGION}/subnet-id" \
            --region "$REGION" \
            --query 'Parameter.Value' \
            --output text 2>/dev/null)

        if [[ -n "$EXISTING_RESERVATION" ]] || [[ -n "$EXISTING_SUBNET" ]]; then
            echo -e "${YELLOW}⚠️  既存のパラメータが見つかりました:${NC}"
            if [[ -n "$EXISTING_RESERVATION" ]]; then
                echo "  Reservation ID: $EXISTING_RESERVATION"
            fi
            if [[ -n "$EXISTING_SUBNET" ]]; then
                echo "  Subnet ID: $EXISTING_SUBNET"
            fi
            echo ""
            echo -e "${YELLOW}上書きしますか？${NC}"
            read -p "(yes/no): " -r
            if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
                echo "キャンセルしました"
                exit 0
            fi
            echo ""
        fi

        echo -e "${BLUE}💾 Parameter Storeに保存中...${NC}"

        # Reservation IDを保存
        aws ssm put-parameter \
            --name "${PARAM_PREFIX}/${REGION}/reservation-id" \
            --value "$RESERVATION_ID" \
            --type String \
            --region "$REGION" \
            --overwrite > /dev/null

        # Subnet IDを保存
        aws ssm put-parameter \
            --name "${PARAM_PREFIX}/${REGION}/subnet-id" \
            --value "$SUBNET_ID" \
            --type String \
            --region "$REGION" \
            --overwrite > /dev/null

        echo ""
        echo -e "${GREEN}✅ Parameter Storeへの保存が完了しました${NC}"
        echo ""
        echo "保存されたパラメータ:"
        echo "  ${PARAM_PREFIX}/${REGION}/reservation-id = $RESERVATION_ID"
        echo "  ${PARAM_PREFIX}/${REGION}/subnet-id = $SUBNET_ID"
        echo ""
        echo -e "${YELLOW}💡 読み込むには:${NC}"
        echo "  $0 load-params -r $REGION"
        ;;

    load-params)
        echo -e "${BLUE}=========================================${NC}"
        echo -e "${BLUE}Parameter Store 読み込み${NC}"
        echo -e "${BLUE}=========================================${NC}"
        echo "リージョン: $REGION"
        echo -e "${BLUE}=========================================${NC}"
        echo ""

        # パラメータを読み込み
        LOADED_RESERVATION=$(aws ssm get-parameter \
            --name "${PARAM_PREFIX}/${REGION}/reservation-id" \
            --region "$REGION" \
            --query 'Parameter.Value' \
            --output text 2>/dev/null)

        LOADED_SUBNET=$(aws ssm get-parameter \
            --name "${PARAM_PREFIX}/${REGION}/subnet-id" \
            --region "$REGION" \
            --query 'Parameter.Value' \
            --output text 2>/dev/null)

        if [[ -z "$LOADED_RESERVATION" ]] && [[ -z "$LOADED_SUBNET" ]]; then
            echo -e "${RED}❌ Parameter Storeにパラメータが見つかりません${NC}"
            echo ""
            echo "パラメータを保存するには:"
            echo "  $0 save-params --reservation-id <ID> --subnet-id <ID> -r $REGION"
            exit 1
        fi

        echo -e "${GREEN}✅ Parameter Storeからパラメータを読み込みました${NC}"
        echo ""
        echo "📋 読み込まれたパラメータ:"
        if [[ -n "$LOADED_RESERVATION" ]]; then
            echo "  Reservation ID: $LOADED_RESERVATION"
        else
            echo -e "  Reservation ID: ${YELLOW}未設定${NC}"
        fi

        if [[ -n "$LOADED_SUBNET" ]]; then
            echo "  Subnet ID: $LOADED_SUBNET"
        else
            echo -e "  Subnet ID: ${YELLOW}未設定${NC}"
        fi

        echo ""
        echo -e "${YELLOW}💡 デプロイコマンド:${NC}"
        if [[ -n "$LOADED_RESERVATION" ]] && [[ -n "$LOADED_SUBNET" ]]; then
            echo "  cd $(dirname "$(dirname "$(realpath "$0")")")"
            echo "  bash scripts/deploy.sh --use-capacity-block \\"
            echo "    --capacity-reservation-id $LOADED_RESERVATION \\"
            echo "    --subnet-id $LOADED_SUBNET \\"
            echo "    -r $REGION"
        fi
        ;;

    "")
        echo -e "${RED}エラー: コマンドを指定してください${NC}"
        echo ""
        usage
        exit 1
        ;;

    *)
        echo -e "${RED}エラー: 不明なコマンド: $COMMAND${NC}"
        echo ""
        usage
        exit 1
        ;;
esac
