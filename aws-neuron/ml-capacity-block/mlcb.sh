#!/bin/bash
set -euo pipefail

# ============================================================================
# ML Capacity Block Manager
# ============================================================================
# Version: 1.0.0
# All-in-one script for managing AWS ML Capacity Blocks
# Repository: https://github.com/littlemex/samples
# ============================================================================

SCRIPT_VERSION="1.0.0"

# デフォルト値
DEFAULT_REGION="sa-east-1"
DEFAULT_INSTANCE_TYPE="trn2.3xlarge"
DEFAULT_DURATION_HOURS=24
DEFAULT_INSTANCE_COUNT=1

# ============================================================================
# ヘルプ表示
# ============================================================================
show_help() {
    cat << EOF
ML Capacity Block Manager v${SCRIPT_VERSION}

Usage: $0 <command> [options]

Commands:
  check [REGION] [INSTANCE_TYPE] [DURATION_HOURS]
      Check available ML Capacity Block offerings
      Default: check $DEFAULT_REGION $DEFAULT_INSTANCE_TYPE $DEFAULT_DURATION_HOURS

  reserve <OFFERING_ID> [REGION] [INSTANCE_COUNT]
      Reserve ML Capacity Block with offering ID
      Example: reserve cbr-a1b2c3d4e5f6g7h8 sa-east-1 2

  list [REGION] [INSTANCE_TYPE]
      List active ML Capacity Block reservations
      Default: list $DEFAULT_REGION

  cancel <RESERVATION_ID> [REGION]
      Cancel ML Capacity Block reservation
      Example: cancel cr-0abcd1234efgh5678 sa-east-1

  help
      Show this help message

Examples:
  # Check available capacity
  $0 check
  $0 check us-west-2 trn1.32xlarge 72

  # Reserve capacity
  $0 reserve cbr-01be24b6d4ffbbe25 sa-east-1 2

  # List reservations
  $0 list
  $0 list sa-east-1 trn2.3xlarge

  # Cancel reservation
  $0 cancel cr-0d2dc154a2679c429 sa-east-1

EOF
}

# ============================================================================
# コマンド: check - 利用可能な容量を確認
# ============================================================================
cmd_check() {
    local REGION="${1:-$DEFAULT_REGION}"
    local INSTANCE_TYPE="${2:-$DEFAULT_INSTANCE_TYPE}"
    local DURATION_HOURS="${3:-$DEFAULT_DURATION_HOURS}"

    echo "[INFO] Checking ML Capacity Block availability for $INSTANCE_TYPE in $REGION"
    echo "[INFO] Duration: $DURATION_HOURS hours"
    echo ""

    # 開始日（今日から）
    local START_DATE=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")

    # 終了日（7日後）
    local END_DATE
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        END_DATE=$(date -u -v+7d +"%Y-%m-%dT%H:%M:%S.000Z")
    else
        # Linux
        END_DATE=$(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%S.000Z")
    fi

    echo "[INFO] Search period: $START_DATE to $END_DATE"
    echo "[INFO] Searching for available capacity block offerings..."
    echo ""

    # 利用可能なオファリングを取得
    local OFFERINGS
    OFFERINGS=$(aws ec2 describe-capacity-block-offerings \
        --region "$REGION" \
        --instance-type "$INSTANCE_TYPE" \
        --instance-count 1 \
        --start-date-range "$START_DATE" \
        --end-date-range "$END_DATE" \
        --capacity-duration-hours "$DURATION_HOURS" \
        --output json 2>&1)

    if echo "$OFFERINGS" | grep -q "InvalidParameterValue\|An error occurred"; then
        echo "[WARNING] ML Capacity Block is not available for $INSTANCE_TYPE in $REGION"
        echo "[INFO] Note: ML Capacity Block may not be supported for all instance types and regions"
        echo ""
        echo "[INFO] Checking if $INSTANCE_TYPE is available as On-Demand or Spot..."

        # インスタンスタイプの提供状況を確認
        aws ec2 describe-instance-type-offerings \
            --location-type availability-zone \
            --filters "Name=instance-type,Values=$INSTANCE_TYPE" \
            --region "$REGION" \
            --query 'InstanceTypeOfferings[*].[Location,InstanceType]' \
            --output table

        echo ""
        echo "[INFO] $INSTANCE_TYPE is available in the above Availability Zones"
        echo "[INFO] You can use On-Demand or Spot instances instead"
        return 0
    fi

    # JSON から配列の長さを取得
    local OFFERING_COUNT=$(echo "$OFFERINGS" | jq -r '.CapacityBlockOfferings | length' 2>/dev/null || echo "0")

    if [ "$OFFERING_COUNT" == "0" ]; then
        echo "[WARNING] No ML Capacity Block offerings found for the specified period"
        echo "[INFO] Try adjusting the date range or check again later"
        return 0
    fi

    echo "[SUCCESS] Available ML Capacity Block offerings:"
    echo ""

    # JSON を解析して表示
    echo "$OFFERINGS" | jq -r '.CapacityBlockOfferings[] |
"Offering ID: \(.CapacityBlockOfferingId)
  AZ: \(.AvailabilityZone)
  Start: \(.StartDate)
  End: \(.EndDate)
  Duration: \(.CapacityBlockDurationHours) hours
  Upfront Fee: $\(.UpfrontFee) \(.CurrencyCode)
"'

    echo "[INFO] To reserve capacity, run:"
    echo "  $0 reserve <OFFERING_ID> $REGION"
}

# ============================================================================
# コマンド: reserve - 容量を予約
# ============================================================================
cmd_reserve() {
    local OFFERING_ID="${1:-}"
    local REGION="${2:-$DEFAULT_REGION}"
    local INSTANCE_COUNT="${3:-$DEFAULT_INSTANCE_COUNT}"

    if [ -z "$OFFERING_ID" ]; then
        echo "[ERROR] Offering ID is required"
        echo ""
        echo "Usage: $0 reserve <OFFERING_ID> [REGION] [INSTANCE_COUNT]"
        echo ""
        echo "Example:"
        echo "  $0 reserve cbr-a1b2c3d4e5f6g7h8 sa-east-1 1"
        echo ""
        echo "To find available offerings, run:"
        echo "  $0 check"
        return 1
    fi

    echo "[INFO] Reserving ML Capacity Block..."
    echo "  Offering ID: $OFFERING_ID"
    echo "  Region: $REGION"
    echo "  Instance Count: $INSTANCE_COUNT"
    echo ""

    # 予約を作成
    echo "[INFO] Creating capacity reservation..."

    local RESERVATION_OUTPUT
    RESERVATION_OUTPUT=$(aws ec2 purchase-capacity-block \
        --region "$REGION" \
        --capacity-block-offering-id "$OFFERING_ID" \
        --instance-platform "Linux/UNIX" \
        --tag-specifications "ResourceType=capacity-reservation,Tags=[{Key=Project,Value=parallelcluster-workshop},{Key=ManagedBy,Value=mlcb-script}]" \
        --output json)

    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create capacity reservation"
        return 1
    fi

    # 予約 ID を取得
    local RESERVATION_ID=$(echo "$RESERVATION_OUTPUT" | jq -r '.CapacityReservation.CapacityReservationId')
    local STATE=$(echo "$RESERVATION_OUTPUT" | jq -r '.CapacityReservation.State')
    local INSTANCE_TYPE=$(echo "$RESERVATION_OUTPUT" | jq -r '.CapacityReservation.InstanceType')
    local AZ=$(echo "$RESERVATION_OUTPUT" | jq -r '.CapacityReservation.AvailabilityZone')
    local START_DATE=$(echo "$RESERVATION_OUTPUT" | jq -r '.CapacityReservation.StartDate')
    local END_DATE=$(echo "$RESERVATION_OUTPUT" | jq -r '.CapacityReservation.EndDate')

    echo ""
    echo "[SUCCESS] Capacity reservation created!"
    echo ""
    echo "Reservation Details:"
    echo "  Reservation ID: $RESERVATION_ID"
    echo "  State: $STATE"
    echo "  Instance Type: $INSTANCE_TYPE"
    echo "  Availability Zone: $AZ"
    echo "  Start Date: $START_DATE"
    echo "  End Date: $END_DATE"
    echo ""

    if [ "$STATE" == "payment-pending" ]; then
        echo "[INFO] State is 'payment-pending'. Waiting for payment confirmation..."
        echo "[INFO] This may take a few minutes."
        echo ""
        echo "[INFO] To check the current state, run:"
        echo "  $0 list $REGION"
        echo ""
        echo "[INFO] Once the state becomes 'active', you can use it in ParallelCluster:"
        echo "  CapacityReservationTarget:"
        echo "    CapacityReservationId: $RESERVATION_ID"
    fi

    if [ "$STATE" == "active" ]; then
        echo "[INFO] Reservation is active! You can use it in ParallelCluster:"
        echo ""
        echo "  CapacityReservationTarget:"
        echo "    CapacityReservationId: $RESERVATION_ID"
    fi

    echo ""
    echo "[INFO] To cancel this reservation (if needed), run:"
    echo "  $0 cancel $RESERVATION_ID $REGION"
}

# ============================================================================
# コマンド: list - 予約一覧を表示
# ============================================================================
cmd_list() {
    local REGION="${1:-$DEFAULT_REGION}"
    local INSTANCE_TYPE="${2:-}"

    echo "[INFO] Listing ML Capacity Block reservations in $REGION"
    if [ -n "$INSTANCE_TYPE" ]; then
        echo "[INFO] Filtering by instance type: $INSTANCE_TYPE"
    fi
    echo ""

    # 予約を取得
    local RESERVATIONS
    if [ -n "$INSTANCE_TYPE" ]; then
        RESERVATIONS=$(aws ec2 describe-capacity-reservations \
            --region "$REGION" \
            --filters "Name=state,Values=active,scheduled,payment-pending,payment-failed" \
                      "Name=instance-type,Values=$INSTANCE_TYPE" \
            --query 'CapacityReservations[*].[CapacityReservationId,State,InstanceType,AvailabilityZone,TotalInstanceCount,StartDate,EndDate,CapacityReservationType]' \
            --output text)
    else
        RESERVATIONS=$(aws ec2 describe-capacity-reservations \
            --region "$REGION" \
            --filters "Name=state,Values=active,scheduled,payment-pending,payment-failed" \
            --query 'CapacityReservations[*].[CapacityReservationId,State,InstanceType,AvailabilityZone,TotalInstanceCount,StartDate,EndDate,CapacityReservationType]' \
            --output text)
    fi

    if [ -z "$RESERVATIONS" ]; then
        echo "[INFO] No active ML Capacity Block reservations found"
        return 0
    fi

    echo "Active ML Capacity Block Reservations:"
    echo "========================================"
    echo ""

    echo "$RESERVATIONS" | while IFS=$'\t' read -r id state type az count start end res_type; do
        echo "Reservation ID: $id"
        echo "  State: $state"
        echo "  Instance Type: $type"
        echo "  Availability Zone: $az"
        echo "  Instance Count: $count"
        echo "  Start Date: $start"
        echo "  End Date: $end"
        echo "  Type: $res_type"
        echo ""
    done

    echo "[INFO] To cancel a reservation, run:"
    echo "  $0 cancel <RESERVATION_ID> $REGION"
}

# ============================================================================
# コマンド: cancel - 予約をキャンセル
# ============================================================================
cmd_cancel() {
    local RESERVATION_ID="${1:-}"
    local REGION="${2:-$DEFAULT_REGION}"

    if [ -z "$RESERVATION_ID" ]; then
        echo "[ERROR] Reservation ID is required"
        echo ""
        echo "Usage: $0 cancel <RESERVATION_ID> [REGION]"
        echo ""
        echo "Example:"
        echo "  $0 cancel cr-0abcd1234efgh5678 sa-east-1"
        echo ""
        echo "To list your reservations, run:"
        echo "  $0 list"
        return 1
    fi

    echo "[INFO] Checking reservation details..."

    # 予約の詳細を取得
    local RESERVATION_INFO
    RESERVATION_INFO=$(aws ec2 describe-capacity-reservations \
        --region "$REGION" \
        --capacity-reservation-ids "$RESERVATION_ID" \
        --output json 2>&1)

    if echo "$RESERVATION_INFO" | grep -q "InvalidCapacityReservationId"; then
        echo "[ERROR] Reservation $RESERVATION_ID not found in region $REGION"
        return 1
    fi

    local STATE=$(echo "$RESERVATION_INFO" | jq -r '.CapacityReservations[0].State')
    local INSTANCE_TYPE=$(echo "$RESERVATION_INFO" | jq -r '.CapacityReservations[0].InstanceType')
    local AZ=$(echo "$RESERVATION_INFO" | jq -r '.CapacityReservations[0].AvailabilityZone')
    local START_DATE=$(echo "$RESERVATION_INFO" | jq -r '.CapacityReservations[0].StartDate')
    local END_DATE=$(echo "$RESERVATION_INFO" | jq -r '.CapacityReservations[0].EndDate')

    echo ""
    echo "Reservation Details:"
    echo "  Reservation ID: $RESERVATION_ID"
    echo "  State: $STATE"
    echo "  Instance Type: $INSTANCE_TYPE"
    echo "  Availability Zone: $AZ"
    echo "  Start Date: $START_DATE"
    echo "  End Date: $END_DATE"
    echo ""

    if [ "$STATE" == "cancelled" ]; then
        echo "[INFO] Reservation is already cancelled"
        return 0
    fi

    if [ "$STATE" == "expired" ]; then
        echo "[INFO] Reservation has already expired"
        return 0
    fi

    # 確認プロンプト
    read -p "[WARNING] Are you sure you want to cancel this reservation? (yes/no): " CONFIRM

    if [ "$CONFIRM" != "yes" ]; then
        echo "[INFO] Cancellation aborted"
        return 0
    fi

    echo ""
    echo "[INFO] Cancelling reservation..."

    # 予約をキャンセル
    aws ec2 cancel-capacity-reservation \
        --region "$REGION" \
        --capacity-reservation-id "$RESERVATION_ID" \
        --output json > /dev/null

    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to cancel reservation"
        return 1
    fi

    echo "[SUCCESS] Reservation $RESERVATION_ID has been cancelled"
    echo ""

    # キャンセル後の状態を確認
    echo "[INFO] Verifying cancellation..."
    sleep 2

    local NEW_STATE=$(aws ec2 describe-capacity-reservations \
        --region "$REGION" \
        --capacity-reservation-ids "$RESERVATION_ID" \
        --query 'CapacityReservations[0].State' \
        --output text)

    echo "[INFO] Current state: $NEW_STATE"
    echo ""

    if [ "$NEW_STATE" == "cancelled" ]; then
        echo "[SUCCESS] Reservation successfully cancelled"
    else
        echo "[WARNING] Reservation state is $NEW_STATE (expected: cancelled)"
        echo "[INFO] It may take a few moments for the cancellation to be reflected"
    fi
}

# ============================================================================
# メイン処理
# ============================================================================
main() {
    local COMMAND="${1:-}"

    if [ -z "$COMMAND" ]; then
        show_help
        exit 1
    fi

    case "$COMMAND" in
        check)
            shift
            cmd_check "$@"
            ;;
        reserve)
            shift
            cmd_reserve "$@"
            ;;
        list)
            shift
            cmd_list "$@"
            ;;
        cancel)
            shift
            cmd_cancel "$@"
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            echo "[ERROR] Unknown command: $COMMAND"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# スクリプト実行
main "$@"
