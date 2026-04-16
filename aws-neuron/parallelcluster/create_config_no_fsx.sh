#!/bin/bash
# ParallelCluster 環境変数収集スクリプト（FSx なし版）
# Usage: bash create_config.sh <CR_ID>

set -e

CR_ID="${1:-}"
STACK_NAME="${STACK_NAME:-parallelcluster-prerequisites}"

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

# Check for JQ
if ! command -v jq &> /dev/null; then
    echo "[ERROR] jq is not installed. Please install jq:"
    echo "  sudo yum install -y jq  # Amazon Linux"
    echo "  brew install jq         # macOS"
    exit 1
fi

echo "[INFO] Collecting ParallelCluster configuration..."

# リージョン設定
if [ -z ${AWS_REGION} ]; then
    echo "[WARNING] AWS_REGION environment variable is not set, automatically set depending on aws cli default region."
    export AWS_REGION=$(aws configure get region)
fi
echo "export AWS_REGION=${AWS_REGION}" > env_vars
echo "[INFO] AWS_REGION = ${AWS_REGION}"

# VPC ID を取得
export VPC_ID=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --query 'Stacks[0].Outputs[?OutputKey==`VPC`].OutputValue' \
    --region ${AWS_REGION} \
    --output text 2>/dev/null)

if [ -z "$VPC_ID" ] || [ "$VPC_ID" == "None" ]; then
    echo "[ERROR] VPC stack '${STACK_NAME}' not found in region ${AWS_REGION}"
    echo "[INFO] Please create the VPC stack first using vpc-multi-az.yaml"
    exit 1
fi

echo "export VPC_ID=${VPC_ID}" >> env_vars
echo "[INFO] VPC_ID = ${VPC_ID}"

# パブリックサブネット ID を取得
export PUBLIC_SUBNET_ID=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --query 'Stacks[0].Outputs[?OutputKey==`PublicSubnet`].OutputValue' \
    --region ${AWS_REGION} \
    --output text)

if [ -z "$PUBLIC_SUBNET_ID" ] || [ "$PUBLIC_SUBNET_ID" == "None" ]; then
    echo "[ERROR] Failed to retrieve Public SUBNET ID from stack ${STACK_NAME}"
    exit 1
fi

echo "export PUBLIC_SUBNET_ID=${PUBLIC_SUBNET_ID}" >> env_vars
echo "[INFO] PUBLIC_SUBNET_ID = ${PUBLIC_SUBNET_ID}"

# セキュリティグループ ID を取得
export SECURITY_GROUP=$(aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --query 'Stacks[0].Outputs[?OutputKey==`SecurityGroup`].OutputValue' \
    --region ${AWS_REGION} \
    --output text)

if [ -z "$SECURITY_GROUP" ] || [ "$SECURITY_GROUP" == "None" ]; then
    echo "[ERROR] Failed to retrieve Security Group from stack ${STACK_NAME}"
    exit 1
fi

echo "export SECURITY_GROUP=${SECURITY_GROUP}" >> env_vars
echo "[INFO] SECURITY_GROUP = ${SECURITY_GROUP}"

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

echo "export CR_ID=${CR_ID}" >> env_vars
echo "export CR_AZ=${CR_AZ}" >> env_vars
echo "export INSTANCE_TYPE=${INSTANCE_TYPE}" >> env_vars
echo "export INSTANCE_COUNT=${INSTANCE_COUNT}" >> env_vars
echo "export CR_STATE=${CR_STATE}" >> env_vars

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

echo "export PRIVATE_SUBNET_ID=${PRIVATE_SUBNET_ID}" >> env_vars
echo "[INFO] PRIVATE_SUBNET_ID = ${PRIVATE_SUBNET_ID} (AZ: ${CR_AZ})"

# SSH キー名（デフォルト）
export KEY_NAME="${KEY_NAME:-pcluster-trn2-key}"
echo "export KEY_NAME=${KEY_NAME}" >> env_vars

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
