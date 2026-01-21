#!/bin/bash

# CloudFormation Stack Manager for FPGA Development Environment
# Simplified version for F2 FPGA instances

set -e

# Default values
STACK_NAME="fpga-dev"
REGION="us-east-1"
INSTANCE_TYPE="f2.6xlarge"
INSTANCE_NAME="FPGADevelopment"
VOLUME_SIZE="500"
KEY_PAIR=""
ALLOWED_SSH_CIDR="0.0.0.0/0"
FPGA_AMI=""
S3_BUCKET=""
S3_PREFIX="cloudformation-templates"
AWS_PROFILE=""
PORT=""
LOCAL_PORT=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Functions
print_usage() {
  cat << EOF
Usage: ./cfn_manager.sh COMMAND [OPTIONS]

Commands:
  create       Create a new CloudFormation stack
  update       Update an existing stack
  delete       Delete a stack
  status       Show stack status
  outputs      Show stack outputs
  events       Show stack events (last 10)
  logs         Show stack events with errors
  validate     Validate CloudFormation templates
  connect      Connect to instance via SSM
  port-forward Forward local port to instance port via SSM
  get-ami      Get latest FPGA Developer AMI ID
  help         Show this help message

Options:
  -n NAME       Stack name (default: fpga-dev)
  -r REGION     AWS region (default: us-east-1)
  -t TYPE       Instance type (default: f2.6xlarge)
  -i NAME       Instance name (default: FPGADevelopment)
  -v SIZE       Volume size in GB (default: 500)
  -k KEYPAIR    Key pair name for SSH access (optional)
  -c CIDR       Allowed SSH CIDR (default: 0.0.0.0/0)
  -a AMI_ID     FPGA Developer AMI ID (optional, will prompt if not set)
  -b BUCKET     S3 bucket for templates (auto-created if not exists)
  -s PREFIX     S3 prefix for templates (default: cloudformation-templates)
  --profile STR AWS profile name (optional)
  --port NUM    Remote port number for port forwarding (required for port-forward)
  --local NUM   Local port number for port forwarding (default: same as remote port)

Examples:
  # Create stack with defaults
  ./cfn_manager.sh create

  # Create with custom settings
  ./cfn_manager.sh create -n my-fpga -t f2.12xlarge -r us-west-2

  # Get latest FPGA AMI
  ./cfn_manager.sh get-ami

  # Create with specific AMI
  ./cfn_manager.sh create -a ami-0cb1b6ae2ff99f8bf

  # Create with SSH access
  ./cfn_manager.sh create -k my-keypair -c 203.0.113.0/24

  # Check status
  ./cfn_manager.sh status -n my-fpga

  # Connect via SSM
  ./cfn_manager.sh connect -n my-fpga

  # Connect via SSM with profile
  ./cfn_manager.sh connect -n my-fpga --profile my-profile

  # Port forward (e.g., for Jupyter on port 8888)
  ./cfn_manager.sh port-forward -n my-fpga --port 8888

  # Port forward with different local port
  ./cfn_manager.sh port-forward -n my-fpga --port 3001 --local 3000 --profile my-profile

  # Delete stack
  ./cfn_manager.sh delete -n my-fpga

EOF
}

log_info() {
  echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
  echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
  echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
  echo -e "${RED}[ERROR]${NC} $1"
}

check_aws_cli() {
  if ! command -v aws &> /dev/null; then
    log_error "AWS CLI is not installed"
    exit 1
  fi
}

# Helper function to build AWS CLI command with optional profile
aws_cmd() {
  if [ -n "${AWS_PROFILE}" ]; then
    echo "aws --profile ${AWS_PROFILE}"
  else
    echo "aws"
  fi
}

get_fpga_ami() {
  local region="${1:-us-east-1}"
  log_info "Fetching latest FPGA Developer AMI in ${region}..." >&2

  # FPGA Developer AMI は AWS Marketplace パートナー (679593333241) が提供
  local ami_info=$(aws ec2 describe-images \
    --region "${region}" \
    --owners 679593333241 \
    --filters \
      "Name=name,Values=*FPGA Developer AMI*Ubuntu*" \
      "Name=state,Values=available" \
      "Name=architecture,Values=x86_64" \
    --query 'sort_by(Images, &CreationDate)[-1].[ImageId,Name,CreationDate]' \
    --output text)

  if [ -z "${ami_info}" ]; then
    log_error "No FPGA Developer AMI found in ${region}" >&2
    return 1
  fi

  # タブ区切りでパース (AMI Name に空白が含まれるため)
  local ami_id=$(echo "${ami_info}" | awk -F'\t' '{print $1}')
  local ami_name=$(echo "${ami_info}" | awk -F'\t' '{print $2}')
  local ami_date=$(echo "${ami_info}" | awk -F'\t' '{print $3}')

  log_success "Found: ${ami_id}" >&2
  log_info "Name: ${ami_name}" >&2
  log_info "Created: ${ami_date}" >&2

  echo "${ami_id}"
}

check_marketplace_subscription() {
  local ami_id="${1}"
  local region="${2:-us-east-1}"

  log_info "Checking if AMI is a Marketplace product..." >&2

  # AMIの詳細を取得してProductCodesをチェック
  local ami_info=$(aws ec2 describe-images \
    --image-ids "${ami_id}" \
    --region "${region}" \
    --query 'Images[0].{ProductCodes:ProductCodes[0].ProductCodeId,ProductCodeType:ProductCodes[0].ProductCodeType}' \
    --output json 2>/dev/null)

  local product_code=$(echo "${ami_info}" | jq -r '.ProductCodes // empty')
  local product_type=$(echo "${ami_info}" | jq -r '.ProductCodeType // empty')

  if [ -z "${product_code}" ] || [ "${product_code}" = "null" ]; then
    log_info "AMI is not a Marketplace product. No subscription required." >&2
    return 0
  fi

  log_info "AMI is a Marketplace product (${product_code})" >&2
  log_info "Checking subscription status..." >&2

  # dry-runでインスタンス起動をテストしてサブスクリプション状態を確認
  local default_vpc=$(aws ec2 describe-vpcs \
    --filters "Name=isDefault,Values=true" \
    --region "${region}" \
    --query 'Vpcs[0].VpcId' \
    --output text 2>/dev/null)

  if [ -z "${default_vpc}" ] || [ "${default_vpc}" = "None" ]; then
    log_warn "No default VPC found. Cannot verify subscription status." >&2
    return 0
  fi

  # t2.microで dry-run テスト（最小コスト）
  local dry_run_result=$(aws ec2 run-instances \
    --image-id "${ami_id}" \
    --instance-type t2.micro \
    --dry-run \
    --region "${region}" 2>&1)

  local exit_code=$?

  # dry-runの結果を解析
  if echo "${dry_run_result}" | grep -q "OptInRequired\|accept terms and subscribe"; then
    log_warn "Marketplace subscription required for this AMI!" >&2
    echo "not_subscribed:${product_code}"
    return 1
  elif echo "${dry_run_result}" | grep -q "DryRunOperation"; then
    log_success "Marketplace subscription is active" >&2
    return 0
  else
    log_warn "Unable to verify subscription status" >&2
    log_info "Dry-run result: ${dry_run_result}" >&2
    return 0
  fi
}

open_marketplace_url() {
  local product_code="${1}"
  local marketplace_url="https://aws.amazon.com/marketplace/pp?sku=${product_code}"

  log_info "Opening Marketplace URL in browser..." >&2

  # OSに応じてブラウザを開く
  if command -v xdg-open &> /dev/null; then
    xdg-open "${marketplace_url}" 2>/dev/null &
  elif command -v open &> /dev/null; then
    open "${marketplace_url}" 2>/dev/null &
  elif command -v wslview &> /dev/null; then
    wslview "${marketplace_url}" 2>/dev/null &
  else
    log_warn "Could not automatically open browser" >&2
  fi

  echo "${marketplace_url}"
}

wait_for_subscription() {
  local ami_id="${1}"
  local product_code="${2}"
  local region="${3:-us-east-1}"

  echo ""
  log_warn "FPGA Developer AMI requires AWS Marketplace subscription" >&2
  echo "" >&2
  log_info "Steps to subscribe:" >&2
  log_info "  1. Open the URL below in your browser" >&2
  log_info "  2. Click 'Continue to Subscribe'" >&2
  log_info "  3. Accept the terms and click 'Accept Terms'" >&2
  log_info "  4. Wait for subscription to be processed (may take 1-2 minutes)" >&2
  echo "" >&2

  local marketplace_url=$(open_marketplace_url "${product_code}")
  log_info "Marketplace URL: ${marketplace_url}" >&2
  echo "" >&2

  read -p "Press Enter after you have completed the subscription..." >&2
  echo "" >&2

  # サブスクリプション完了を確認
  log_info "Verifying subscription..." >&2
  local max_retries=5
  local retry_count=0

  while [ ${retry_count} -lt ${max_retries} ]; do
    if check_marketplace_subscription "${ami_id}" "${region}" >/dev/null 2>&1; then
      log_success "Subscription verified successfully!" >&2
      return 0
    fi

    retry_count=$((retry_count + 1))
    if [ ${retry_count} -lt ${max_retries} ]; then
      log_warn "Subscription not yet active. Retrying in 10 seconds... (${retry_count}/${max_retries})" >&2
      sleep 10
    fi
  done

  log_error "Could not verify subscription after ${max_retries} attempts" >&2
  log_warn "Please ensure you have completed the subscription and try again" >&2
  return 1
}

get_or_create_s3_bucket() {
  local bucket_name="${1}"
  local region="${2:-us-east-1}"

  log_info "Checking S3 bucket: ${bucket_name}" >&2

  # Check if bucket exists
  if aws s3api head-bucket --bucket "${bucket_name}" --region "${region}" 2>/dev/null >/dev/null; then
    log_success "S3 bucket exists: ${bucket_name}" >&2
    echo "${bucket_name}"
    return 0
  fi

  log_info "Creating S3 bucket: ${bucket_name}" >&2

  # Create bucket (region-specific configuration)
  if [ "${region}" = "us-east-1" ]; then
    aws s3api create-bucket \
      --bucket "${bucket_name}" \
      --region "${region}" \
      > /dev/null
  else
    aws s3api create-bucket \
      --bucket "${bucket_name}" \
      --region "${region}" \
      --create-bucket-configuration LocationConstraint="${region}" \
      > /dev/null
  fi

  # Enable versioning
  aws s3api put-bucket-versioning \
    --bucket "${bucket_name}" \
    --versioning-configuration Status=Enabled

  # Enable server-side encryption
  aws s3api put-bucket-encryption \
    --bucket "${bucket_name}" \
    --server-side-encryption-configuration '{
      "Rules": [{
        "ApplyServerSideEncryptionByDefault": {
          "SSEAlgorithm": "AES256"
        }
      }]
    }'

  log_success "S3 bucket created: ${bucket_name}" >&2
  echo "${bucket_name}"
}

upload_templates_to_s3() {
  local bucket_name="${1}"
  local prefix="${2}"
  local region="${3}"

  log_info "Uploading templates to S3..." >&2

  # Upload ec2.yml
  aws s3 cp ec2.yml "s3://${bucket_name}/${prefix}/ec2.yml" --region "${region}" >&2
  log_success "Uploaded ec2.yml" >&2

  # Get S3 URL for ec2.yml
  local ec2_template_url="https://${bucket_name}.s3.${region}.amazonaws.com/${prefix}/ec2.yml"
  echo "${ec2_template_url}"
}

create_main_yml_with_s3() {
  local ec2_template_url="${1}"
  local output_file="${2:-main-s3.yml}"

  log_info "Creating main.yml with S3 template URL..." >&2

  # Replace TemplateURL in main.yml (use @ as delimiter to avoid issues with / in URLs)
  sed "s@TemplateURL: ./ec2.yml@TemplateURL: ${ec2_template_url}@" main.yml > "${output_file}"

  log_success "Created ${output_file}" >&2
  echo "${output_file}"
}

validate_templates() {
  log_info "Validating CloudFormation templates..."

  for template in ec2.yml main.yml; do
    if [ -f "${template}" ]; then
      log_info "Validating ${template}..."
      aws cloudformation validate-template \
        --template-body file://${template} \
        --region ${REGION} \
        > /dev/null
      log_success "${template} is valid"
    else
      log_error "${template} not found"
      return 1
    fi
  done
}

create_stack() {
  log_info "Creating CloudFormation stack: ${STACK_NAME}"

  # Get AMI if not provided
  if [ -z "${FPGA_AMI}" ]; then
    log_warn "No AMI ID provided. Fetching latest FPGA Developer AMI..."
    FPGA_AMI=$(get_fpga_ami "${REGION}")
    if [ -z "${FPGA_AMI}" ]; then
      log_error "Failed to get FPGA AMI. Please provide AMI ID with -a option"
      exit 1
    fi

    read -p "Use AMI ${FPGA_AMI}? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]] && [[ ! -z $REPLY ]]; then
      log_info "Aborted"
      exit 0
    fi
  fi

  # Check Marketplace subscription
  local subscription_check=$(check_marketplace_subscription "${FPGA_AMI}" "${REGION}")
  if [ $? -ne 0 ]; then
    # Extract product code from result
    local product_code=$(echo "${subscription_check}" | cut -d':' -f2)

    # Wait for user to subscribe
    if ! wait_for_subscription "${FPGA_AMI}" "${product_code}" "${REGION}"; then
      log_error "Marketplace subscription is required to proceed"
      exit 1
    fi
  fi

  # Setup S3 bucket for nested templates
  if [ -z "${S3_BUCKET}" ]; then
    # Generate default bucket name using AWS account ID
    local account_id=$(aws sts get-caller-identity --query Account --output text)
    S3_BUCKET="cfn-templates-${account_id}-${REGION}"
  fi

  # Get or create S3 bucket
  S3_BUCKET=$(get_or_create_s3_bucket "${S3_BUCKET}" "${REGION}")

  # Upload templates to S3
  local ec2_template_url=$(upload_templates_to_s3 "${S3_BUCKET}" "${S3_PREFIX}" "${REGION}")

  # Create modified main.yml with S3 URL
  local main_yml_file=$(create_main_yml_with_s3 "${ec2_template_url}" "main-s3.yml")

  # Validate templates
  validate_templates

  log_info "Stack parameters:"
  log_info "  Region: ${REGION}"
  log_info "  Instance Type: ${INSTANCE_TYPE}"
  log_info "  Instance Name: ${INSTANCE_NAME}"
  log_info "  Volume Size: ${VOLUME_SIZE} GB"
  log_info "  AMI ID: ${FPGA_AMI}"
  [ ! -z "${KEY_PAIR}" ] && log_info "  Key Pair: ${KEY_PAIR}"
  [ ! -z "${KEY_PAIR}" ] && log_info "  Allowed SSH: ${ALLOWED_SSH_CIDR}"

  # Build parameters as array for proper quoting
  local params=(
    "ParameterKey=InstanceName,ParameterValue=${INSTANCE_NAME}"
    "ParameterKey=InstanceType,ParameterValue=${INSTANCE_TYPE}"
    "ParameterKey=InstanceVolumeSize,ParameterValue=${VOLUME_SIZE}"
    "ParameterKey=FpgaAmiId,ParameterValue=${FPGA_AMI}"
    "ParameterKey=KeyPairName,ParameterValue=${KEY_PAIR}"
    "ParameterKey=AllowedSSHCidr,ParameterValue=${ALLOWED_SSH_CIDR}"
  )

  aws cloudformation create-stack \
    --stack-name "${STACK_NAME}" \
    --template-body "file://${main_yml_file}" \
    --parameters "${params[@]}" \
    --capabilities CAPABILITY_IAM \
    --region "${REGION}"

  log_success "Stack creation initiated"
  log_info "Waiting for stack creation to complete..."

  aws cloudformation wait stack-create-complete \
    --stack-name ${STACK_NAME} \
    --region ${REGION}

  log_success "Stack created successfully!"
  show_outputs
}

update_stack() {
  log_info "Updating CloudFormation stack: ${STACK_NAME}"

  validate_templates

  # Build parameters as array for proper quoting
  local params=(
    "ParameterKey=InstanceName,UsePreviousValue=true"
    "ParameterKey=InstanceType,UsePreviousValue=true"
    "ParameterKey=InstanceVolumeSize,UsePreviousValue=true"
    "ParameterKey=FpgaAmiId,UsePreviousValue=true"
    "ParameterKey=KeyPairName,UsePreviousValue=true"
    "ParameterKey=AllowedSSHCidr,UsePreviousValue=true"
  )

  aws cloudformation update-stack \
    --stack-name "${STACK_NAME}" \
    --template-body file://main.yml \
    --parameters "${params[@]}" \
    --capabilities CAPABILITY_IAM \
    --region "${REGION}"

  log_success "Stack update initiated"
}

delete_stack() {
  log_warn "Deleting stack: ${STACK_NAME}"
  read -p "Are you sure? [y/N] " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Aborted"
    exit 0
  fi

  aws cloudformation delete-stack \
    --stack-name ${STACK_NAME} \
    --region ${REGION}

  log_success "Stack deletion initiated"
  log_info "Waiting for deletion to complete..."

  aws cloudformation wait stack-delete-complete \
    --stack-name ${STACK_NAME} \
    --region ${REGION}

  log_success "Stack deleted successfully"
}

show_status() {
  log_info "Stack status for: ${STACK_NAME}"

  aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query 'Stacks[0].[StackName,StackStatus,CreationTime]' \
    --output table
}

show_outputs() {
  log_info "Stack outputs for: ${STACK_NAME}"

  aws cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query 'Stacks[0].Outputs' \
    --output table
}

show_events() {
  log_info "Recent stack events for: ${STACK_NAME}"

  aws cloudformation describe-stack-events \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --max-items 10 \
    --query 'StackEvents[].[Timestamp,ResourceStatus,ResourceType,LogicalResourceId,ResourceStatusReason]' \
    --output table
}

show_logs() {
  log_info "Stack events with errors for: ${STACK_NAME}"

  aws cloudformation describe-stack-events \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query 'StackEvents[?contains(ResourceStatus, `FAILED`) || contains(ResourceStatus, `ROLLBACK`)].[Timestamp,ResourceStatus,ResourceType,LogicalResourceId,ResourceStatusReason]' \
    --output table
}

connect_ssm() {
  log_info "Connecting to instance via SSM..."

  local aws_cli=$(aws_cmd)
  local instance_id=$(${aws_cli} cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' \
    --output text)

  if [ -z "${instance_id}" ] || [ "${instance_id}" = "None" ]; then
    log_error "Could not find instance ID in stack outputs"
    exit 1
  fi

  log_info "Connecting to instance: ${instance_id}"
  [ -n "${AWS_PROFILE}" ] && log_info "Using profile: ${AWS_PROFILE}"

  ${aws_cli} ssm start-session \
    --target ${instance_id} \
    --region ${REGION}
}

port_forward_ssm() {
  if [ -z "${PORT}" ]; then
    log_error "Port number is required. Use --port option"
    exit 1
  fi

  # Default local port to remote port if not specified
  if [ -z "${LOCAL_PORT}" ]; then
    LOCAL_PORT="${PORT}"
  fi

  log_info "Setting up port forwarding..."

  local aws_cli=$(aws_cmd)
  local instance_id=$(${aws_cli} cloudformation describe-stacks \
    --stack-name ${STACK_NAME} \
    --region ${REGION} \
    --query 'Stacks[0].Outputs[?OutputKey==`InstanceId`].OutputValue' \
    --output text)

  if [ -z "${instance_id}" ] || [ "${instance_id}" = "None" ]; then
    log_error "Could not find instance ID in stack outputs"
    exit 1
  fi

  log_info "Instance: ${instance_id}"
  log_info "Remote port: ${PORT}"
  log_info "Local port: ${LOCAL_PORT}"
  [ -n "${AWS_PROFILE}" ] && log_info "Using profile: ${AWS_PROFILE}"
  echo ""
  log_success "Port forwarding active. Access via: http://localhost:${LOCAL_PORT}"
  log_info "Press Ctrl+C to stop"
  echo ""

  ${aws_cli} ssm start-session \
    --target ${instance_id} \
    --region ${REGION} \
    --document-name AWS-StartPortForwardingSession \
    --parameters "{\"portNumber\":[\"${PORT}\"],\"localPortNumber\":[\"${LOCAL_PORT}\"]}"
}

# Parse command
COMMAND="${1:-help}"
shift || true

# Parse options (both short and long options)
while [[ $# -gt 0 ]]; do
  case $1 in
    -n)
      STACK_NAME="$2"
      shift 2
      ;;
    -r)
      REGION="$2"
      shift 2
      ;;
    -t)
      INSTANCE_TYPE="$2"
      shift 2
      ;;
    -i)
      INSTANCE_NAME="$2"
      shift 2
      ;;
    -v)
      VOLUME_SIZE="$2"
      shift 2
      ;;
    -k)
      KEY_PAIR="$2"
      shift 2
      ;;
    -c)
      ALLOWED_SSH_CIDR="$2"
      shift 2
      ;;
    -a)
      FPGA_AMI="$2"
      shift 2
      ;;
    -b)
      S3_BUCKET="$2"
      shift 2
      ;;
    -s)
      S3_PREFIX="$2"
      shift 2
      ;;
    --profile)
      AWS_PROFILE="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    --local)
      LOCAL_PORT="$2"
      shift 2
      ;;
    -h|--help)
      print_usage
      exit 0
      ;;
    -*)
      log_error "Invalid option: $1"
      print_usage
      exit 1
      ;;
    *)
      break
      ;;
  esac
done

# Check AWS CLI
check_aws_cli

# Execute command
case ${COMMAND} in
  create)
    create_stack
    ;;
  update)
    update_stack
    ;;
  delete)
    delete_stack
    ;;
  status)
    show_status
    ;;
  outputs)
    show_outputs
    ;;
  events)
    show_events
    ;;
  logs)
    show_logs
    ;;
  validate)
    validate_templates
    log_success "All templates are valid"
    ;;
  connect)
    connect_ssm
    ;;
  port-forward)
    port_forward_ssm
    ;;
  get-ami)
    get_fpga_ami "${REGION}"
    ;;
  help|--help|-h)
    print_usage
    ;;
  *)
    log_error "Unknown command: ${COMMAND}"
    print_usage
    exit 1
    ;;
esac
