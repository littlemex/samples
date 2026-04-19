#!/bin/bash
set -euo pipefail

# ============================================================================
# ML Capacity Block Manager
# ============================================================================
# Version: 1.1.0
# All-in-one script for managing AWS ML Capacity Blocks
# Repository: https://github.com/littlemex/samples
# ============================================================================

SCRIPT_VERSION="1.1.0"

# デフォルト値
DEFAULT_REGION="sa-east-1"
DEFAULT_INSTANCE_TYPE="trn2.3xlarge"
DEFAULT_DURATION_HOURS=72
DEFAULT_INSTANCE_COUNT=1

# ============================================================================
# 共通ユーティリティ
# ============================================================================

# ISO8601 UTC -> "YYYY-MM-DD HH:MM:SS JST"
to_jst() {
    local iso="$1"
    if [ -z "$iso" ] || [ "$iso" == "None" ] || [ "$iso" == "null" ]; then
        echo "-"
        return
    fi
    # 秒以下やタイムゾーン表記ゆれを吸収（以後 UTC の naive ISO として扱う）
    iso="${iso%%.*}"
    iso="${iso%+00:00}"
    iso="${iso%Z}"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        local epoch
        epoch=$(TZ=UTC date -j -u -f "%Y-%m-%dT%H:%M:%S" "$iso" "+%s" 2>/dev/null) || { echo "$iso UTC"; return; }
        TZ="Asia/Tokyo" date -j -r "$epoch" "+%Y-%m-%d %H:%M:%S JST"
    else
        TZ="Asia/Tokyo" date -d "${iso}Z" "+%Y-%m-%d %H:%M:%S JST" 2>/dev/null || echo "$iso UTC"
    fi
}

# 共通オプション解析: --region / --instance-type / --instance-count /
#   --duration-hours / --az / --include-expired を抜き出して環境変数にセット
# 位置引数（存在すれば）は echo で標準出力に返し、呼び出し側が eval 不要で受け取る
parse_opts() {
    OPT_REGION=""
    OPT_INSTANCE_TYPE=""
    OPT_INSTANCE_COUNT=""
    OPT_DURATION_HOURS=""
    OPT_AZ=""
    OPT_INCLUDE_EXPIRED="false"
    POSITIONAL=()
    while [ $# -gt 0 ]; do
        case "$1" in
            --region)          OPT_REGION="$2"; shift 2 ;;
            --instance-type)   OPT_INSTANCE_TYPE="$2"; shift 2 ;;
            --instance-count)  OPT_INSTANCE_COUNT="$2"; shift 2 ;;
            --duration-hours)  OPT_DURATION_HOURS="$2"; shift 2 ;;
            --az)              OPT_AZ="$2"; shift 2 ;;
            --include-expired) OPT_INCLUDE_EXPIRED="true"; shift 1 ;;
            --) shift; break ;;
            -*) echo "[WARN] Unknown option: $1" >&2; shift ;;
            *)  POSITIONAL+=("$1"); shift ;;
        esac
    done
}

# ============================================================================
# ヘルプ表示
# ============================================================================
show_help() {
    cat << EOF
ML Capacity Block Manager v${SCRIPT_VERSION}

Usage: $0 <command> [options]

Commands:
  check    Check available ML Capacity Block offerings
  reserve  Reserve ML Capacity Block with offering ID
  list     List ML Capacity Block reservations
  cancel   Cancel ML Capacity Block reservation
  help     Show this help message

Common options (where applicable):
  --region REGION              AWS region (default: ${DEFAULT_REGION})
  --instance-type TYPE         Instance type (default: ${DEFAULT_INSTANCE_TYPE})
  --instance-count N           Instance count (default: ${DEFAULT_INSTANCE_COUNT})
  --duration-hours HOURS       Capacity duration (default: ${DEFAULT_DURATION_HOURS})
  --az ZONE                    Filter by availability zone (e.g. sa-east-1b)
  --include-expired            (list only) include expired/cancelled items

Examples:
  # Check available capacity filtered by AZ
  $0 check --az sa-east-1b

  # List active reservations (capacity-block only)
  $0 list
  $0 list --az sa-east-1b
  $0 list --include-expired

  # Reserve capacity
  $0 reserve cbr-01be24b6d4ffbbe25 --instance-count 2

  # Cancel reservation
  $0 cancel cr-0d2dc154a2679c429

EOF
}

# ============================================================================
# コマンド: check - 利用可能な容量を確認
# ============================================================================
cmd_check() {
    parse_opts "$@"
    local REGION="${OPT_REGION:-${POSITIONAL[0]:-$DEFAULT_REGION}}"
    local INSTANCE_TYPE="${OPT_INSTANCE_TYPE:-${POSITIONAL[1]:-$DEFAULT_INSTANCE_TYPE}}"
    local DURATION_HOURS="${OPT_DURATION_HOURS:-${POSITIONAL[2]:-$DEFAULT_DURATION_HOURS}}"
    local INSTANCE_COUNT="${OPT_INSTANCE_COUNT:-$DEFAULT_INSTANCE_COUNT}"
    local FILTER_AZ="${OPT_AZ:-}"

    echo "[INFO] Checking ML Capacity Block availability"
    echo "  Region: $REGION"
    echo "  Instance Type: $INSTANCE_TYPE"
    echo "  Instance Count: $INSTANCE_COUNT"
    echo "  Duration: $DURATION_HOURS hours"
    if [ -n "$FILTER_AZ" ]; then
        echo "  Filter AZ: $FILTER_AZ"
    fi
    echo "  Search period: next 7 days"
    echo "  Timezone: JST (Asia/Tokyo)"
    echo ""

    # 開始日（今）〜終了日（7日後）
    local START_DATE END_DATE
    START_DATE=$(date -u +"%Y-%m-%dT%H:%M:%S.000Z")
    if [[ "$OSTYPE" == "darwin"* ]]; then
        END_DATE=$(date -u -v+7d +"%Y-%m-%dT%H:%M:%S.000Z")
    else
        END_DATE=$(date -u -d "+7 days" +"%Y-%m-%dT%H:%M:%S.000Z")
    fi

    echo "[INFO] Search period: $START_DATE to $END_DATE"
    echo "[INFO] Searching for available capacity block offerings..."
    echo ""

    local OFFERINGS
    OFFERINGS=$(aws ec2 describe-capacity-block-offerings \
        --region "$REGION" \
        --instance-type "$INSTANCE_TYPE" \
        --instance-count "$INSTANCE_COUNT" \
        --start-date-range "$START_DATE" \
        --end-date-range "$END_DATE" \
        --capacity-duration-hours "$DURATION_HOURS" \
        --output json 2>&1)

    if echo "$OFFERINGS" | grep -q "InvalidParameterValue\|An error occurred"; then
        echo "[WARNING] ML Capacity Block is not available for $INSTANCE_TYPE in $REGION"
        echo "$OFFERINGS" | head -5
        echo ""
        echo "[INFO] Checking if $INSTANCE_TYPE is available as On-Demand or Spot..."
        aws ec2 describe-instance-type-offerings \
            --location-type availability-zone \
            --filters "Name=instance-type,Values=$INSTANCE_TYPE" \
            --region "$REGION" \
            --query 'InstanceTypeOfferings[*].[Location,InstanceType]' \
            --output table
        return 0
    fi

    # AZ フィルタを jq 側で適用
    local FILTER_EXPR='.CapacityBlockOfferings[]'
    if [ -n "$FILTER_AZ" ]; then
        FILTER_EXPR=".CapacityBlockOfferings[] | select(.AvailabilityZone == \"$FILTER_AZ\")"
    fi

    local OFFERING_COUNT
    OFFERING_COUNT=$(echo "$OFFERINGS" | jq -r "[$FILTER_EXPR] | length" 2>/dev/null || echo "0")

    if [ "$OFFERING_COUNT" == "0" ]; then
        echo "[WARNING] No ML Capacity Block offerings found${FILTER_AZ:+ in $FILTER_AZ}"
        echo "[INFO] Try adjusting the date range, AZ, or duration"
        return 0
    fi

    if [ -n "$FILTER_AZ" ]; then
        echo "[SUCCESS] Available ML Capacity Block offerings in $FILTER_AZ:"
    else
        echo "[SUCCESS] Available ML Capacity Block offerings:"
    fi
    echo ""

    # JSON を解析して表示（JST）
    echo "$OFFERINGS" | jq -c "$FILTER_EXPR" | while read -r offering; do
        local oid az start end dur fee cur cnt
        oid=$(echo "$offering" | jq -r '.CapacityBlockOfferingId')
        az=$(echo "$offering" | jq -r '.AvailabilityZone')
        start=$(echo "$offering" | jq -r '.StartDate')
        end=$(echo "$offering" | jq -r '.EndDate')
        dur=$(echo "$offering" | jq -r '.CapacityBlockDurationHours')
        fee=$(echo "$offering" | jq -r '.UpfrontFee')
        cur=$(echo "$offering" | jq -r '.CurrencyCode')
        cnt=$(echo "$offering" | jq -r '.InstanceCount // empty')

        echo "Offering ID: $oid"
        echo "  AZ: $az"
        [ -n "$cnt" ] && echo "  Instance Count: $cnt"
        echo "  Start: $(to_jst "$start")"
        echo "  End: $(to_jst "$end")"
        echo "  Duration: $dur hours"
        echo "  Upfront Fee: \$${fee} ${cur}"
        echo ""
    done

    echo "[INFO] To reserve capacity, run:"
    echo "  $0 reserve <OFFERING_ID> --region $REGION"
}

# ============================================================================
# コマンド: reserve - 容量を予約
# ============================================================================
cmd_reserve() {
    parse_opts "$@"
    local OFFERING_ID="${POSITIONAL[0]:-}"
    local REGION="${OPT_REGION:-${POSITIONAL[1]:-$DEFAULT_REGION}}"
    local INSTANCE_COUNT="${OPT_INSTANCE_COUNT:-${POSITIONAL[2]:-$DEFAULT_INSTANCE_COUNT}}"

    if [ -z "$OFFERING_ID" ]; then
        echo "[ERROR] Offering ID is required"
        echo ""
        echo "Usage: $0 reserve <OFFERING_ID> [--region REGION] [--instance-count N]"
        return 1
    fi

    echo "[INFO] Reserving ML Capacity Block..."
    echo "  Offering ID: $OFFERING_ID"
    echo "  Region: $REGION"
    echo "  Instance Count: $INSTANCE_COUNT"
    echo ""

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

    local RESERVATION_ID STATE INSTANCE_TYPE AZ START_DATE END_DATE
    RESERVATION_ID=$(echo "$RESERVATION_OUTPUT" | jq -r '.CapacityReservation.CapacityReservationId')
    STATE=$(echo "$RESERVATION_OUTPUT" | jq -r '.CapacityReservation.State')
    INSTANCE_TYPE=$(echo "$RESERVATION_OUTPUT" | jq -r '.CapacityReservation.InstanceType')
    AZ=$(echo "$RESERVATION_OUTPUT" | jq -r '.CapacityReservation.AvailabilityZone')
    START_DATE=$(echo "$RESERVATION_OUTPUT" | jq -r '.CapacityReservation.StartDate')
    END_DATE=$(echo "$RESERVATION_OUTPUT" | jq -r '.CapacityReservation.EndDate')

    echo ""
    echo "[SUCCESS] Capacity reservation created!"
    echo ""
    echo "Reservation Details:"
    echo "  Reservation ID: $RESERVATION_ID"
    echo "  State: $STATE"
    echo "  Instance Type: $INSTANCE_TYPE"
    echo "  AZ: $AZ"
    echo "  Start: $(to_jst "$START_DATE")"
    echo "  End: $(to_jst "$END_DATE")"
    echo ""

    if [ "$STATE" == "payment-pending" ]; then
        echo "[INFO] State is 'payment-pending'. Waiting for payment confirmation..."
        echo "[INFO] Check again with: $0 list --region $REGION"
    elif [ "$STATE" == "active" ]; then
        echo "[INFO] Reservation is active! Use in ParallelCluster with:"
        echo "  CapacityReservationTarget:"
        echo "    CapacityReservationId: $RESERVATION_ID"
    fi
}

# ============================================================================
# コマンド: list - 予約一覧を表示
# ============================================================================
cmd_list() {
    parse_opts "$@"
    local REGION="${OPT_REGION:-${POSITIONAL[0]:-$DEFAULT_REGION}}"
    local INSTANCE_TYPE="${OPT_INSTANCE_TYPE:-${POSITIONAL[1]:-}}"
    local FILTER_AZ="${OPT_AZ:-}"
    local INCLUDE_EXPIRED_FLAG="${OPT_INCLUDE_EXPIRED:-false}"
    # 後方互換: 環境変数でも切替可能
    if [ "${INCLUDE_EXPIRED:-false}" == "true" ]; then
        INCLUDE_EXPIRED_FLAG="true"
    fi

    echo "[INFO] Listing ML Capacity Block reservations"
    echo "  Region: $REGION"
    [ -n "$INSTANCE_TYPE" ] && echo "  Instance Type: $INSTANCE_TYPE"
    [ -n "$FILTER_AZ" ] && echo "  Filter AZ: $FILTER_AZ"
    [ "$INCLUDE_EXPIRED_FLAG" == "true" ] && echo "  Include: expired/cancelled"
    echo "  Timezone: JST (Asia/Tokyo)"
    echo ""

    # state フィルタ
    local STATE_FILTER="active,scheduled,payment-pending,payment-failed"
    if [ "$INCLUDE_EXPIRED_FLAG" == "true" ]; then
        STATE_FILTER="${STATE_FILTER},expired,cancelled"
    fi

    # filter 配列を構築
    local FILTERS=(
        "Name=state,Values=${STATE_FILTER}"
        "Name=reservation-type,Values=capacity-block"
    )
    [ -n "$INSTANCE_TYPE" ] && FILTERS+=("Name=instance-type,Values=$INSTANCE_TYPE")
    [ -n "$FILTER_AZ" ]     && FILTERS+=("Name=availability-zone,Values=$FILTER_AZ")

    local RESERVATIONS_JSON
    RESERVATIONS_JSON=$(aws ec2 describe-capacity-reservations \
        --region "$REGION" \
        --filters "${FILTERS[@]}" \
        --output json)

    local COUNT
    COUNT=$(echo "$RESERVATIONS_JSON" | jq -r '.CapacityReservations | length')

    if [ "$COUNT" == "0" ]; then
        echo "[INFO] No ML Capacity Block reservations found"
        return 0
    fi

    echo "ML Capacity Block Reservations:"
    echo "========================================"
    echo ""

    echo "$RESERVATIONS_JSON" | jq -c '.CapacityReservations[]' | while read -r r; do
        local id state itype az total avail start end rtype
        id=$(echo "$r" | jq -r '.CapacityReservationId')
        state=$(echo "$r" | jq -r '.State')
        itype=$(echo "$r" | jq -r '.InstanceType')
        az=$(echo "$r" | jq -r '.AvailabilityZone')
        total=$(echo "$r" | jq -r '.TotalInstanceCount // 0')
        avail=$(echo "$r" | jq -r '.AvailableInstanceCount // 0')
        start=$(echo "$r" | jq -r '.StartDate // empty')
        end=$(echo "$r" | jq -r '.EndDate // empty')
        rtype=$(echo "$r" | jq -r '.ReservationType // "-"')

        echo "Reservation ID: $id"
        echo "  State: $state"
        echo "  Instance Type: $itype"
        echo "  AZ: $az"
        echo "  Instance Count: $total"
        echo "  Available: $avail"
        echo "  Start: $(to_jst "$start")"
        echo "  End: $(to_jst "$end")"
        echo "  Type: $rtype"
        echo ""
    done

    echo "[INFO] To cancel a reservation, run:"
    echo "  $0 cancel <RESERVATION_ID> --region $REGION"
}

# ============================================================================
# コマンド: cancel - 予約をキャンセル
# ============================================================================
cmd_cancel() {
    parse_opts "$@"
    local RESERVATION_ID="${POSITIONAL[0]:-}"
    local REGION="${OPT_REGION:-${POSITIONAL[1]:-$DEFAULT_REGION}}"

    if [ -z "$RESERVATION_ID" ]; then
        echo "[ERROR] Reservation ID is required"
        echo "Usage: $0 cancel <RESERVATION_ID> [--region REGION]"
        return 1
    fi

    echo "[INFO] Checking reservation details..."

    local RESERVATION_INFO
    RESERVATION_INFO=$(aws ec2 describe-capacity-reservations \
        --region "$REGION" \
        --capacity-reservation-ids "$RESERVATION_ID" \
        --output json 2>&1)

    if echo "$RESERVATION_INFO" | grep -q "InvalidCapacityReservationId"; then
        echo "[ERROR] Reservation $RESERVATION_ID not found in region $REGION"
        return 1
    fi

    local STATE INSTANCE_TYPE AZ START_DATE END_DATE
    STATE=$(echo "$RESERVATION_INFO" | jq -r '.CapacityReservations[0].State')
    INSTANCE_TYPE=$(echo "$RESERVATION_INFO" | jq -r '.CapacityReservations[0].InstanceType')
    AZ=$(echo "$RESERVATION_INFO" | jq -r '.CapacityReservations[0].AvailabilityZone')
    START_DATE=$(echo "$RESERVATION_INFO" | jq -r '.CapacityReservations[0].StartDate')
    END_DATE=$(echo "$RESERVATION_INFO" | jq -r '.CapacityReservations[0].EndDate')

    echo ""
    echo "Reservation Details:"
    echo "  Reservation ID: $RESERVATION_ID"
    echo "  State: $STATE"
    echo "  Instance Type: $INSTANCE_TYPE"
    echo "  AZ: $AZ"
    echo "  Start: $(to_jst "$START_DATE")"
    echo "  End: $(to_jst "$END_DATE")"
    echo ""

    if [ "$STATE" == "cancelled" ]; then
        echo "[INFO] Reservation is already cancelled"
        return 0
    fi
    if [ "$STATE" == "expired" ]; then
        echo "[INFO] Reservation has already expired"
        return 0
    fi

    read -p "[WARNING] Are you sure you want to cancel this reservation? (yes/no): " CONFIRM
    if [ "$CONFIRM" != "yes" ]; then
        echo "[INFO] Cancellation aborted"
        return 0
    fi

    echo ""
    echo "[INFO] Cancelling reservation..."
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
    sleep 2

    local NEW_STATE
    NEW_STATE=$(aws ec2 describe-capacity-reservations \
        --region "$REGION" \
        --capacity-reservation-ids "$RESERVATION_ID" \
        --query 'CapacityReservations[0].State' \
        --output text)
    echo "[INFO] Current state: $NEW_STATE"
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
        check)   shift; cmd_check "$@" ;;
        reserve) shift; cmd_reserve "$@" ;;
        list)    shift; cmd_list "$@" ;;
        cancel)  shift; cmd_cancel "$@" ;;
        help|--help|-h) show_help ;;
        *)
            echo "[ERROR] Unknown command: $COMMAND"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

main "$@"
