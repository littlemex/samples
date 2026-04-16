#!/bin/bash
# ParallelCluster 環境変数収集スクリプト
# Usage: bash create_config.sh <CR_ID>

set -e

CR_ID="${1:-}"

if [ -z "$CR_ID" ]; then
    echo "[ERROR] Usage: $0 <CAPACITY_RESERVATION_ID>"
    echo ""
    echo "Example:"
    echo "  $0 cr-0d2dc154a2679c429"
    echo ""
    echo "To find your capacity reservation ID:"
    echo "  cd ~/samples/aws-neuron/ml-capacity-block && bash mlcb.sh list"
    exit 1
fi

echo "[INFO] Collecting ParallelCluster configuration..."

# リージョン設定
export AWS_REGION=${AWS_REGION:-sa-east-1}
echo "[INFO] Region: ${AWS_REGION}"

# VPC スタックから情報を取得
STACK_NAME="${STACK_NAME:-parallelcluster-prerequisites}"
echo "[INFO] Fetching VPC information from CloudFormation stack: ${STACK_NAME}..."
export VPC_ID=$(aws cloudformation describe-stacks \
  --stack-name ${STACK_NAME} \
  --region ${AWS_REGION} \
  --query 'Stacks[0].Outputs[?OutputKey==`VpcId`].OutputValue' \
  --output text 2>/dev/null)

if [ -z "$VPC_ID" ] || [ "$VPC_ID" == "None" ]; then
    echo "[ERROR] VPC stack '${STACK_NAME}' not found in region ${AWS_REGION}"
    echo "[INFO] Please create the VPC stack first using vpc-multi-az.yaml"
    exit 1
fi

echo "[INFO] VPC_ID: ${VPC_ID}"

# パブリックサブネット（HeadNode 用、最初の AZ を使用）
export PUBLIC_SUBNET_ID=$(aws ec2 describe-subnets \
  --region ${AWS_REGION} \
  --filters "Name=vpc-id,Values=${VPC_ID}" \
            "Name=tag:Name,Values=*Public*" \
  --query 'Subnets | sort_by(@, &AvailabilityZone) | [0].SubnetId' \
  --output text)

if [ -z "$PUBLIC_SUBNET_ID" ] || [ "$PUBLIC_SUBNET_ID" == "None" ]; then
    echo "[ERROR] Public subnet not found in VPC ${VPC_ID}"
    exit 1
fi

echo "[INFO] PUBLIC_SUBNET_ID: ${PUBLIC_SUBNET_ID}"

# セキュリティグループ
export SECURITY_GROUP=$(aws ec2 describe-security-groups \
  --region ${AWS_REGION} \
  --filters "Name=vpc-id,Values=${VPC_ID}" \
            "Name=group-name,Values=*default*" \
  --query 'SecurityGroups[0].GroupId' \
  --output text)

if [ -z "$SECURITY_GROUP" ] || [ "$SECURITY_GROUP" == "None" ]; then
    echo "[ERROR] Security group not found in VPC ${VPC_ID}"
    exit 1
fi

echo "[INFO] SECURITY_GROUP: ${SECURITY_GROUP}"

# ML Capacity Block の詳細を取得
echo ""
echo "[INFO] Fetching ML Capacity Block information..."
CR_INFO=$(aws ec2 describe-capacity-reservations \
    --region ${AWS_REGION} \
    --capacity-reservation-ids ${CR_ID} \
    --output json 2>&1)

if echo "$CR_INFO" | grep -q "InvalidCapacityReservationId"; then
    echo "[ERROR] Capacity Reservation ${CR_ID} not found in region ${AWS_REGION}"
    exit 1
fi

export CR_AZ=$(echo "$CR_INFO" | jq -r '.CapacityReservations[0].AvailabilityZone')
export INSTANCE_TYPE=$(echo "$CR_INFO" | jq -r '.CapacityReservations[0].InstanceType')
export INSTANCE_COUNT=$(echo "$CR_INFO" | jq -r '.CapacityReservations[0].TotalInstanceCount')
export CR_STATE=$(echo "$CR_INFO" | jq -r '.CapacityReservations[0].State')

echo "[INFO] Capacity Reservation Details:"
echo "  CR_ID: ${CR_ID}"
echo "  State: ${CR_STATE}"
echo "  AZ: ${CR_AZ}"
echo "  Instance Type: ${INSTANCE_TYPE}"
echo "  Instance Count: ${INSTANCE_COUNT}"

# CR_AZ に対応するプライベートサブネットを自動選択
echo ""
echo "[INFO] Selecting private subnet for AZ ${CR_AZ}..."
export PRIVATE_SUBNET_ID=$(aws ec2 describe-subnets \
  --region ${AWS_REGION} \
  --filters "Name=vpc-id,Values=${VPC_ID}" \
            "Name=availability-zone,Values=${CR_AZ}" \
            "Name=tag:Name,Values=*Private*" \
  --query 'Subnets[0].SubnetId' \
  --output text)

if [ -z "$PRIVATE_SUBNET_ID" ] || [ "$PRIVATE_SUBNET_ID" == "None" ]; then
    echo "[ERROR] Private subnet not found for AZ ${CR_AZ} in VPC ${VPC_ID}"
    echo "[INFO] Available subnets:"
    aws ec2 describe-subnets \
      --region ${AWS_REGION} \
      --filters "Name=vpc-id,Values=${VPC_ID}" \
      --query 'Subnets[*].[SubnetId,AvailabilityZone,Tags[?Key==`Name`].Value|[0]]' \
      --output table
    exit 1
fi

echo "[INFO] PRIVATE_SUBNET_ID: ${PRIVATE_SUBNET_ID} (AZ: ${CR_AZ})"

# SSH キー名（デフォルト）
export KEY_NAME="${KEY_NAME:-pcluster-trn2-key}"

# 環境変数を env_vars ファイルに保存
cat > env_vars << EOF
export AWS_REGION=${AWS_REGION}
export VPC_ID=${VPC_ID}
export PUBLIC_SUBNET_ID=${PUBLIC_SUBNET_ID}
export PRIVATE_SUBNET_ID=${PRIVATE_SUBNET_ID}
export SECURITY_GROUP=${SECURITY_GROUP}
export CR_ID=${CR_ID}
export CR_AZ=${CR_AZ}
export INSTANCE_TYPE=${INSTANCE_TYPE}
export INSTANCE_COUNT=${INSTANCE_COUNT}
export CR_STATE=${CR_STATE}
export KEY_NAME=${KEY_NAME}
EOF

echo ""
echo "[SUCCESS] Environment variables saved to env_vars"
echo "[INFO] To load variables: source env_vars"
echo ""
echo "[INFO] Summary:"
echo "  AWS_REGION: ${AWS_REGION}"
echo "  VPC_ID: ${VPC_ID}"
echo "  PUBLIC_SUBNET_ID: ${PUBLIC_SUBNET_ID}"
echo "  PRIVATE_SUBNET_ID: ${PRIVATE_SUBNET_ID} (AZ: ${CR_AZ})"
echo "  SECURITY_GROUP: ${SECURITY_GROUP}"
echo "  CR_ID: ${CR_ID}"
echo "  INSTANCE_TYPE: ${INSTANCE_TYPE}"
echo "  INSTANCE_COUNT: ${INSTANCE_COUNT}"
echo "  KEY_NAME: ${KEY_NAME}"
