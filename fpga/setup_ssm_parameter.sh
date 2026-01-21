#!/bin/bash

# FPGA Developer AMI ID を SSM Parameter Store にセットアップするスクリプト
# これにより、CloudFormation で {{resolve:ssm:...}} 構文を使って AMI ID を参照できます

set -e

# デフォルト値
REGION="${1:-us-east-1}"
OS_TYPE="${2:-ubuntu}"
PARAMETER_NAME="/fpga/ami/latest"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

log_info "FPGA Developer AMI の最新版を取得して SSM パラメータストアに保存します"
log_info "リージョン: ${REGION}"
log_info "OS タイプ: ${OS_TYPE}"
log_info "パラメータ名: ${PARAMETER_NAME}"
echo ""

# OS に応じたフィルタパターンを設定
case "${OS_TYPE}" in
  ubuntu)
    NAME_PATTERN="*FPGA Developer AMI*Ubuntu*"
    PARAMETER_DESC="Latest FPGA Developer AMI for Ubuntu"
    ;;
  rocky|rockylinux)
    NAME_PATTERN="*FPGA Developer AMI*Rocky*"
    PARAMETER_DESC="Latest FPGA Developer AMI for Rocky Linux"
    ;;
  *)
    NAME_PATTERN="*FPGA Developer AMI*"
    PARAMETER_DESC="Latest FPGA Developer AMI"
    ;;
esac

# 最新の FPGA Developer AMI を取得
log_info "AMI を検索中..."

AMI_INFO=$(aws ec2 describe-images \
  --region "${REGION}" \
  --owners amazon \
  --filters \
    "Name=name,Values=${NAME_PATTERN}" \
    "Name=state,Values=available" \
    "Name=architecture,Values=x86_64" \
  --query 'sort_by(Images, &CreationDate)[-1].[ImageId,Name,CreationDate,Description]' \
  --output text)

if [ -z "${AMI_INFO}" ]; then
  log_error "FPGA Developer AMI が見つかりませんでした"
  log_info "別の OS タイプを試すか、リージョンを変更してください"
  exit 1
fi

AMI_ID=$(echo "${AMI_INFO}" | awk '{print $1}')
AMI_NAME=$(echo "${AMI_INFO}" | awk '{print $2}')
AMI_DATE=$(echo "${AMI_INFO}" | awk '{print $3}')

log_success "最新の FPGA Developer AMI が見つかりました:"
log_info "  AMI ID: ${AMI_ID}"
log_info "  名前: ${AMI_NAME}"
log_info "  作成日: ${AMI_DATE}"
echo ""

# 既存のパラメータをチェック
log_info "既存の SSM パラメータをチェック中..."
EXISTING_VALUE=$(aws ssm get-parameter \
  --name "${PARAMETER_NAME}" \
  --region "${REGION}" \
  --query 'Parameter.Value' \
  --output text 2>/dev/null || echo "")

if [ ! -z "${EXISTING_VALUE}" ]; then
  log_info "既存のパラメータが見つかりました: ${EXISTING_VALUE}"

  if [ "${EXISTING_VALUE}" == "${AMI_ID}" ]; then
    log_success "パラメータは既に最新です"
    exit 0
  fi

  read -p "パラメータを更新しますか? [Y/n] " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]] && [[ ! -z $REPLY ]]; then
    log_info "キャンセルしました"
    exit 0
  fi

  # パラメータを更新
  log_info "SSM パラメータを更新中..."
  aws ssm put-parameter \
    --name "${PARAMETER_NAME}" \
    --value "${AMI_ID}" \
    --description "${PARAMETER_DESC} - ${AMI_NAME}" \
    --type String \
    --overwrite \
    --region "${REGION}" \
    > /dev/null

  log_success "SSM パラメータを更新しました"
else
  # 新規パラメータを作成
  log_info "SSM パラメータを作成中..."
  aws ssm put-parameter \
    --name "${PARAMETER_NAME}" \
    --value "${AMI_ID}" \
    --description "${PARAMETER_DESC} - ${AMI_NAME}" \
    --type String \
    --region "${REGION}" \
    > /dev/null

  log_success "SSM パラメータを作成しました"
fi

echo ""
log_success "セットアップ完了！"
log_info "CloudFormation で以下の構文で参照できます:"
log_info "  ImageId: '{{resolve:ssm:${PARAMETER_NAME}}}'"
echo ""
log_info "パラメータ情報:"
aws ssm get-parameter \
  --name "${PARAMETER_NAME}" \
  --region "${REGION}" \
  --query 'Parameter.[Name,Value,LastModifiedDate,Description]' \
  --output table
