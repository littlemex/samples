#!/bin/bash

# FPGA Developer AMI の最新版を取得するスクリプト
# 使用方法: ./get_fpga_ami.sh [region] [os]
# 例: ./get_fpga_ami.sh us-east-1 ubuntu

set -e

# デフォルト値
REGION="${1:-us-east-1}"
OS_TYPE="${2:-ubuntu}"

echo "FPGA Developer AMI を検索中..."
echo "リージョン: ${REGION}"
echo "OS タイプ: ${OS_TYPE}"
echo ""

# OS に応じたフィルタパターンを設定
case "${OS_TYPE}" in
  ubuntu)
    NAME_PATTERN="*FPGA Developer AMI*Ubuntu*"
    ;;
  rocky|rockylinux)
    NAME_PATTERN="*FPGA Developer AMI*Rocky*"
    ;;
  *)
    NAME_PATTERN="*FPGA Developer AMI*"
    ;;
esac

# 最新の FPGA Developer AMI を取得
# FPGA Developer AMI は AWS Marketplace パートナー (679593333241) が提供
AMI_JSON=$(aws ec2 describe-images \
  --region "${REGION}" \
  --owners 679593333241 \
  --filters \
    "Name=name,Values=${NAME_PATTERN}" \
    "Name=state,Values=available" \
    "Name=architecture,Values=x86_64" \
  --query 'sort_by(Images, &CreationDate)[-1]' \
  --output json)

if [ -z "${AMI_JSON}" ] || [ "${AMI_JSON}" = "null" ]; then
  echo "エラー: FPGA Developer AMI が見つかりませんでした"
  echo "別の OS タイプを試すか、リージョンを変更してください"
  exit 1
fi

# 結果をパースして表示
AMI_ID=$(echo "${AMI_JSON}" | jq -r '.ImageId')
AMI_NAME=$(echo "${AMI_JSON}" | jq -r '.Name')
AMI_DATE=$(echo "${AMI_JSON}" | jq -r '.CreationDate')
AMI_DESC=$(echo "${AMI_JSON}" | jq -r '.Description')

echo "最新の FPGA Developer AMI が見つかりました:"
echo "AMI ID: ${AMI_ID}"
echo "名前: ${AMI_NAME}"
echo "作成日: ${AMI_DATE}"
echo "説明: ${AMI_DESC}"
echo ""

# CloudFormation パラメータ形式で出力
echo "AMI ID (コピー用): ${AMI_ID}"
echo ""
echo "CloudFormation パラメータ用:"
echo "  FpgaAmiId: ${AMI_ID}"
