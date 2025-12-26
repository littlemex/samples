#!/bin/bash

# Amazon SageMaker HyperPod Slurm Observability Setup Script (Open Source Grafana)
# This script automates the complete setup of observability for HyperPod Slurm clusters using Open Source Grafana
# 
# Features:
# - Idempotent execution (safe to run multiple times)
# - Complete automation of IAM, CloudFormation, and cluster configuration
# - Uses Open Source Grafana (compatible with AWS Organizations member accounts)
# - Comprehensive error handling and logging
#
# Requirements:
# - AWS CLI configured with appropriate permissions
# - HyperPod cluster "cpu-slurm-cluster" must exist in us-east-1

set -euo pipefail

# Configuration
readonly CLUSTER_NAME="cpu-slurm-cluster"
readonly REGION="us-east-1"
readonly STACK_NAME="HyperpodSlurmOSObservability"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly LOG_FILE="/tmp/hyperpod_oss_observability_setup.log"

# Colors for output
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

# Error handler
error_handler() {
    local line_no=$1
    log_error "Script failed at line $line_no. Check log file: $LOG_FILE"
    exit 1
}

trap 'error_handler $LINENO' ERR

# Utility functions
check_aws_cli() {
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install AWS CLI first."
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS CLI is not properly configured. Please configure AWS credentials."
        exit 1
    fi
    
    log_success "AWS CLI is properly configured"
}

check_hyperpod_cluster() {
    log_info "Checking HyperPod cluster: $CLUSTER_NAME"
    
    local cluster_status
    cluster_status=$(aws sagemaker describe-cluster \
        --cluster-name "$CLUSTER_NAME" \
        --region "$REGION" \
        --query 'ClusterStatus' \
        --output text 2>/dev/null || echo "NotFound")
    
    if [[ "$cluster_status" == "NotFound" ]]; then
        log_error "HyperPod cluster '$CLUSTER_NAME' not found in region '$REGION'"
        exit 1
    elif [[ "$cluster_status" != "InService" ]]; then
        log_error "HyperPod cluster '$CLUSTER_NAME' is not in InService state. Current status: $cluster_status"
        exit 1
    fi
    
    log_success "HyperPod cluster '$CLUSTER_NAME' is available and InService"
}

get_instance_group_role() {
    local role_arn
    role_arn=$(aws sagemaker describe-cluster \
        --cluster-name "$CLUSTER_NAME" \
        --region "$REGION" \
        --query 'InstanceGroups[0].ExecutionRole' \
        --output text)
    
    if [[ -z "$role_arn" || "$role_arn" == "None" ]]; then
        log_error "Failed to get IAM role from HyperPod cluster"
        exit 1
    fi
    
    # Extract role name from ARN
    local role_name
    role_name=$(echo "$role_arn" | sed 's|.*/||')
    echo "$role_name"
}

check_managed_policy_attached() {
    local role_name=$1
    local policy_arn="arn:aws:iam::aws:policy/AmazonPrometheusRemoteWriteAccess"
    
    aws iam list-attached-role-policies \
        --role-name "$role_name" \
        --query "AttachedPolicies[?PolicyArn=='$policy_arn']" \
        --output text | grep -q "AmazonPrometheusRemoteWriteAccess" 2>/dev/null
}

check_inline_policy_exists() {
    local role_name=$1
    local policy_name="ECRAccessPolicy"
    
    aws iam get-role-policy \
        --role-name "$role_name" \
        --policy-name "$policy_name" &>/dev/null
}

setup_iam_permissions() {
    log_info "Setting up IAM permissions for HyperPod cluster"
    
    local role_name
    role_name=$(get_instance_group_role)
    log_info "Using IAM role: $role_name"
    
    # Check and attach managed policy
    if check_managed_policy_attached "$role_name"; then
        log_success "AmazonPrometheusRemoteWriteAccess policy already attached"
    else
        log_info "Attaching AmazonPrometheusRemoteWriteAccess policy"
        aws iam attach-role-policy \
            --role-name "$role_name" \
            --policy-arn "arn:aws:iam::aws:policy/AmazonPrometheusRemoteWriteAccess"
        log_success "AmazonPrometheusRemoteWriteAccess policy attached"
    fi
    
    # Check and add inline policy
    if check_inline_policy_exists "$role_name"; then
        log_success "ECR inline policy already exists"
    else
        log_info "Adding ECR inline policy"
        aws iam put-role-policy \
            --role-name "$role_name" \
            --policy-name "ECRAccessPolicy" \
            --policy-document "file://$SCRIPT_DIR/ecr-policy.json"
        log_success "ECR inline policy added"
    fi
}

check_cloudformation_stack() {
    local stack_status
    stack_status=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "NOT_EXISTS")
    
    echo "$stack_status"
}

wait_for_stack_completion() {
    local operation=$1
    log_info "Waiting for CloudFormation stack $operation to complete..."
    
    local max_attempts=60  # 30 minutes (60 * 30 seconds)
    local attempt=0
    
    while [[ $attempt -lt $max_attempts ]]; do
        local status
        status=$(check_cloudformation_stack)
        
        case "$status" in
            "CREATE_COMPLETE"|"UPDATE_COMPLETE")
                log_success "CloudFormation stack $operation completed successfully"
                return 0
                ;;
            "CREATE_FAILED"|"UPDATE_FAILED"|"ROLLBACK_COMPLETE"|"DELETE_COMPLETE")
                log_error "CloudFormation stack $operation failed with status: $status"
                return 1
                ;;
            "CREATE_IN_PROGRESS"|"UPDATE_IN_PROGRESS")
                echo -n "."
                sleep 30
                ((attempt++))
                ;;
            *)
                log_error "Unexpected CloudFormation stack status: $status"
                return 1
                ;;
        esac
    done
    
    log_error "CloudFormation stack $operation timed out after 30 minutes"
    return 1
}

get_ec2_metadata_token() {
    # Get IMDSv2 token with 6-hour TTL
    curl -X PUT "http://169.254.169.254/latest/api/token" \
         -H "X-aws-ec2-metadata-token-ttl-seconds: 21600" \
         -s --connect-timeout 5 2>/dev/null || echo ""
}

get_ec2_metadata() {
    local metadata_path="$1"
    local token=$(get_ec2_metadata_token)
    
    if [[ -n "$token" ]]; then
        # Use IMDSv2 with token
        curl -H "X-aws-ec2-metadata-token: $token" \
             -s --connect-timeout 5 \
             "http://169.254.169.254/latest/meta-data/$metadata_path" 2>/dev/null || echo ""
    else
        # Fallback to IMDSv1 (may not work if IMDSv2 is enforced)
        curl -s --connect-timeout 5 \
             "http://169.254.169.254/latest/meta-data/$metadata_path" 2>/dev/null || echo ""
    fi
}

get_current_ip() {
    local provided_ip="$1"
    
    if [[ -n "$provided_ip" ]]; then
        # Use provided IP address
        echo "$(date): [INFO] Using provided IP address: $provided_ip" >> "$LOG_FILE"
        echo "$provided_ip"
    else
        # Auto-detect current IP address
        echo "$(date): [INFO] Auto-detecting current public IP address for security restriction" >> "$LOG_FILE"
        
        local current_ip
        
        # First try to get IP from EC2 metadata (if running on EC2)
        current_ip=$(get_ec2_metadata "public-ipv4" 2>/dev/null)
        
        if [[ -z "$current_ip" ]]; then
            # Fallback to external IP detection services
            echo "$(date): [INFO] EC2 metadata not available, trying external IP detection services" >> "$LOG_FILE"
            current_ip=$(curl -s --connect-timeout 10 https://checkip.amazonaws.com || \
                        curl -s --connect-timeout 10 http://ifconfig.me || \
                        curl -s --connect-timeout 10 http://ipecho.net/plain)
        fi
        
        if [[ -z "$current_ip" ]]; then
            echo "$(date): [ERROR] Failed to get current IP address. Please check internet connectivity or provide IP manually with --ip option." >> "$LOG_FILE"
            echo -e "${RED}[ERROR]${NC} Failed to get current IP address. Please check internet connectivity or provide IP manually with --ip option." >&2
            exit 1
        fi
        
        echo "$(date): [SUCCESS] Auto-detected IP address: $current_ip" >> "$LOG_FILE"
        echo "$current_ip"
    fi
}

validate_ip_address() {
    local ip="$1"
    
    # Basic IPv4 validation
    if [[ $ip =~ ^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$ ]]; then
        local IFS='.'
        local -a octets=($ip)
        
        for octet in "${octets[@]}"; do
            if [[ $octet -gt 255 ]]; then
                return 1
            fi
        done
        return 0
    fi
    
    return 1
}

check_local_template() {
    local template_path="$SCRIPT_DIR/cluster-observability-with-os-grafana.yaml"
    
    if [[ ! -f "$template_path" ]]; then
        echo "$(date): [ERROR] Local CloudFormation template not found: $template_path" >> "$LOG_FILE"
        echo "$(date): [INFO] This script requires the improved local template to be present" >> "$LOG_FILE"
        echo -e "${RED}[ERROR]${NC} Local CloudFormation template not found: $template_path" >&2
        echo -e "${BLUE}[INFO]${NC} This script requires the improved local template to be present" >&2
        exit 1
    fi
    
    # Log to file only to avoid polluting function return value
    echo "$(date): [SUCCESS] Local CloudFormation template found: $template_path" >> "$LOG_FILE"
    echo "$template_path"
}

deploy_observability_stack() {
    local provided_ip="$1"
    
    log_info "Deploying secure Open Source Grafana + Prometheus CloudFormation stack"
    
    # Check for local template
    local local_template
    local_template=$(check_local_template)
    
    # Determine IP address for security group
    local current_ip
    current_ip=$(get_current_ip "$provided_ip")
    
    local stack_status
    stack_status=$(check_cloudformation_stack)
    
    case "$stack_status" in
        "NOT_EXISTS")
            log_info "Creating CloudFormation stack with IP restriction: $STACK_NAME"
            log_info "Using IP address: $current_ip/32"
            
            aws cloudformation create-stack \
                --stack-name "$STACK_NAME" \
                --region "$REGION" \
                --template-body "file://$local_template" \
                --parameters ParameterKey=AllowedIPRange,ParameterValue="$current_ip/32" \
                --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM
            
            wait_for_stack_completion "creation"
            ;;
        "CREATE_COMPLETE"|"UPDATE_COMPLETE")
            log_success "CloudFormation stack already exists and is complete"
            ;;
        "UPDATE_IN_PROGRESS"|"CREATE_IN_PROGRESS")
            log_info "CloudFormation stack operation already in progress"
            wait_for_stack_completion "current operation"
            ;;
        *)
            log_warning "CloudFormation stack exists with status: $stack_status"
            log_info "Attempting to update the stack with IP restriction..."
            log_info "Using IP address: $current_ip/32"
            
            aws cloudformation update-stack \
                --stack-name "$STACK_NAME" \
                --region "$REGION" \
                --template-body "file://$local_template" \
                --parameters ParameterKey=AllowedIPRange,ParameterValue="$current_ip/32" \
                --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM 2>/dev/null || {
                log_warning "No updates needed for CloudFormation stack"
                return 0
            }
            
            wait_for_stack_completion "update"
            ;;
    esac
}

get_prometheus_endpoint() {
    log_info "Getting Prometheus remote write URL from CloudFormation stack"
    
    local prometheus_url
    prometheus_url=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`PrometheusRemoteWriteURL`].OutputValue' \
        --output text)
    
    if [[ -z "$prometheus_url" || "$prometheus_url" == "None" ]]; then
        log_error "Failed to get Prometheus remote write URL from CloudFormation stack"
        exit 1
    fi
    
    log_success "Prometheus remote write URL: $prometheus_url"
    echo "$prometheus_url"
}

get_grafana_instance_address() {
    log_info "Getting Grafana instance address from CloudFormation stack"
    
    local grafana_address
    grafana_address=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`GrafanaInstanceAddress`].OutputValue' \
        --output text)
    
    if [[ -z "$grafana_address" || "$grafana_address" == "None" ]]; then
        log_error "Failed to get Grafana instance address from CloudFormation stack"
        exit 1
    fi
    
    log_success "Grafana instance address: $grafana_address"
    echo "$grafana_address"
}

get_s3_bucket_name() {
    # Log to file only to avoid polluting function return value
    echo "$(date): [INFO] Getting S3 bucket name for lifecycle scripts" >> "$LOG_FILE"
    
    local bucket_name
    bucket_name=$(aws sagemaker describe-cluster \
        --cluster-name "$CLUSTER_NAME" \
        --region "$REGION" \
        --query 'InstanceGroups[0].LifeCycleConfig.SourceS3Uri' \
        --output text | sed 's|s3://||' | cut -d'/' -f1)
    
    if [[ -z "$bucket_name" || "$bucket_name" == "None" ]]; then
        echo "$(date): [ERROR] Failed to get S3 bucket name from HyperPod cluster" >> "$LOG_FILE"
        echo -e "${RED}[ERROR]${NC} Failed to get S3 bucket name from HyperPod cluster" >&2
        exit 1
    fi
    
    echo "$(date): [SUCCESS] S3 bucket name: $bucket_name" >> "$LOG_FILE"
    echo "$bucket_name"
}

update_lifecycle_scripts() {
    log_info "Updating lifecycle scripts for Observability"
    
    local prometheus_url
    prometheus_url=$(get_prometheus_endpoint)
    
    local bucket_name
    bucket_name=$(get_s3_bucket_name)
    
    local temp_dir="/tmp/hyperpod_lifecycle_scripts_$$"
    mkdir -p "$temp_dir"
    
    # Download current lifecycle scripts
    log_info "Downloading current lifecycle scripts from S3"
    aws s3 sync "s3://$bucket_name/" "$temp_dir/"
    
    # Check if config.py exists
    if [[ ! -f "$temp_dir/config.py" ]]; then
        log_error "config.py not found in lifecycle scripts"
        rm -rf "$temp_dir"
        exit 1
    fi
    
    # Update config.py for observability
    log_info "Updating config.py for Observability"
    
    # Check if observability is already enabled
    if grep -q "enable_observability = True" "$temp_dir/config.py"; then
        log_success "Observability already enabled in config.py"
    else
        log_info "Enabling observability in config.py"
        sed -i 's/enable_observability = False/enable_observability = True/' "$temp_dir/config.py"
    fi
    
    # Update ObservabilityConfig using Python for safe URL handling
    if grep -F "prometheus_remote_write_url" "$temp_dir/config.py" | grep -qF "$prometheus_url"; then
        log_success "Prometheus URL already configured correctly"
    else
        log_info "Updating Prometheus remote write URL"
        python3 -c "
import re
with open('$temp_dir/config.py', 'r') as f:
    content = f.read()
content = re.sub(r'prometheus_remote_write_url = \".*?\"', 'prometheus_remote_write_url = \"$prometheus_url\"', content)
with open('$temp_dir/config.py', 'w') as f:
    f.write(content)
"
    fi
    
    # Enable advanced metrics
    if grep -q "advanced_metrics = True" "$temp_dir/config.py"; then
        log_success "Advanced metrics already enabled"
    else
        log_info "Enabling advanced metrics"
        sed -i 's/advanced_metrics = False/advanced_metrics = True/' "$temp_dir/config.py"
    fi
    
    # Upload updated scripts
    log_info "Uploading updated lifecycle scripts to S3"
    aws s3 sync "$temp_dir/" "s3://$bucket_name/"
    
    # Cleanup
    rm -rf "$temp_dir"
    
    log_success "Lifecycle scripts updated successfully"
}

get_head_node_instance_id() {
    local instance_id
    instance_id=$(aws sagemaker describe-cluster \
        --cluster-name "$CLUSTER_NAME" \
        --region "$REGION" \
        --query 'InstanceGroups[?InstanceGroupName==`controller-group`].Instances[0].InstanceId' \
        --output text 2>/dev/null || echo "None")
    
    if [[ "$instance_id" == "None" || -z "$instance_id" ]]; then
        log_error "Failed to get head node instance ID"
        exit 1
    fi
    
    echo "$instance_id"
}

install_observability_components() {
    log_info "Installing Observability components on HyperPod cluster"
    
    local prometheus_url
    prometheus_url=$(get_prometheus_endpoint)
    
    local head_node_id
    head_node_id=$(get_head_node_instance_id)
    
    log_info "Head node instance ID: $head_node_id"
    
    # Get worker node count
    local num_workers
    num_workers=$(aws sagemaker describe-cluster \
        --cluster-name "$CLUSTER_NAME" \
        --region "$REGION" \
        --query 'InstanceGroups[?InstanceGroupName!=`controller-group`] | [0].InstanceCount' \
        --output text)
    
    if [[ -z "$num_workers" || "$num_workers" == "None" ]]; then
        num_workers=2  # Default fallback
        log_warning "Could not determine worker count, using default: $num_workers"
    fi
    
    log_info "Worker node count: $num_workers"
    
    # Create installation script
    local install_script="/tmp/install_observability_remote.sh"
    cat > "$install_script" << EOF
#!/bin/bash
set -euo pipefail

export NUM_WORKERS=$num_workers
export PROMETHEUS_REMOTE_WRITE_URL="$prometheus_url"
export ARG_ADVANCED="--advanced"

# Setup observability directory
mkdir -p ~/observability-setup
cd ~/observability-setup

# Clone or update awsome-distributed-training repository
if [[ -d "awsome-distributed-training" ]]; then
    cd awsome-distributed-training
    git pull
    cd ..
else
    git clone https://github.com/aws-samples/awsome-distributed-training.git
fi

cd awsome-distributed-training/1.architectures/5.sagemaker-hyperpod/LifecycleScripts/base-config/observability

# Check if observability is already installed
if systemctl is-active --quiet slurm_exporter.service 2>/dev/null; then
    echo "Slurm exporter already running, stopping existing services..."
    sudo python3 stop_observability.py --node-type controller || true
    srun -N \$NUM_WORKERS sudo python3 stop_observability.py --node-type compute || true
fi

# Install observability components
echo "Installing observability components..."
sudo python3 install_observability.py --node-type controller --prometheus-remote-write-url "\$PROMETHEUS_REMOTE_WRITE_URL" \$ARG_ADVANCED
srun -N \$NUM_WORKERS sudo python3 install_observability.py --node-type compute --prometheus-remote-write-url "\$PROMETHEUS_REMOTE_WRITE_URL" \$ARG_ADVANCED

# Verify installation
echo "Verifying installation..."
systemctl status slurm_exporter.service --no-pager -l
docker ps
srun -N \$NUM_WORKERS docker ps

echo "Observability installation completed successfully"
EOF
    
    chmod +x "$install_script"
    
    # Copy script to head node and execute
    log_info "Copying installation script to head node"
    aws ssm send-command \
        --instance-ids "$head_node_id" \
        --document-name "AWS-RunShellScript" \
        --region "$REGION" \
        --parameters "commands=[\"$(base64 -w 0 < "$install_script" | tr -d '\n')\"]" \
        --timeout-seconds 1800 \
        --output text > /dev/null
    
    log_success "Observability installation initiated on cluster"
    log_info "Note: Installation may take 10-15 minutes to complete"
    
    # Cleanup
    rm -f "$install_script"
}

get_prometheus_query_url() {
    log_info "Getting Prometheus query URL from CloudFormation stack"
    
    local prometheus_query_url
    prometheus_query_url=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`PrometheusQueryURL`].OutputValue' \
        --output text)
    
    if [[ -z "$prometheus_query_url" || "$prometheus_query_url" == "None" ]]; then
        log_error "Failed to get Prometheus query URL from CloudFormation stack"
        exit 1
    fi
    
    log_success "Prometheus query URL: $prometheus_query_url"
    echo "$prometheus_query_url"
}

display_next_steps() {
    local provided_ip="$1"
    
    log_info "Secure Open Source Grafana Observability setup completed successfully!"
    echo
    echo "==============================================="
    echo "NEXT STEPS - GRAFANA CONFIGURATION"
    echo "==============================================="
    echo
    
    local grafana_address
    grafana_address=$(get_grafana_instance_address)
    
    local prometheus_query_url
    prometheus_query_url=$(get_prometheus_query_url)
    
    local current_ip
    current_ip=$(get_current_ip "$provided_ip")
    
    echo "1. Access Secure Open Source Grafana:"
    
    # Ensure URL format is correct (avoid http://http:// duplication)
    if [[ "$grafana_address" =~ ^https?:// ]]; then
        echo "   - URL: $grafana_address"
        echo "   - Copy to browser: $grafana_address"
    else
        echo "   - URL: http://$grafana_address"
        echo "   - Copy to browser: http://$grafana_address"
    fi
    
    echo "   - Default login: admin/admin"
    echo "   - Change password after first login"
    echo "   - ✅ SigV4 Authentication: PRE-CONFIGURED (no manual setup required)"
    echo "   - SECURITY: Access is restricted to your configured IP ($current_ip/32)"
    echo
    echo "2. Configure Amazon Managed Prometheus data source:"
    echo "   - Go to Configuration > Data Sources"
    echo "   - Click 'Add data source'"
    echo "   - ⚠️  Select 'Amazon Managed Service for Prometheus' (NOT regular Prometheus)"
    echo "   - ℹ️  Note: Core Prometheus SigV4 is deprecated - use dedicated AMP plugin"
    echo "   - URL: $prometheus_query_url"
    echo "   - Authentication Provider: AWS SDK Default"
    echo "   - Default Region: $REGION"
    echo "   - Click 'Save & Test' (should show 'Data source is working')"
    echo "   - ✅ Amazon Managed Prometheus plugin is pre-installed and configured"
    echo
    echo "3. Import pre-built dashboards:"
    echo "   - Slurm Dashboard: https://grafana.com/grafana/dashboards/4323-slurm-dashboard/"
    echo "   - Node Exporter: https://grafana.com/grafana/dashboards/1860-node-exporter-full/"
    echo "   - DCGM Exporter: https://grafana.com/grafana/dashboards/12239-nvidia-dcgm-exporter-dashboard/"
    echo "   - FSx for Lustre: https://grafana.com/grafana/dashboards/20906-fsx/"
    echo
    echo "4. Security Information:"
    echo "   - Grafana access is restricted to IP: $current_ip/32"
    echo "   - To allow access from a different IP, re-run this script with --ip option"
    echo "   - Or manually update the security group in AWS Console"
    echo
    echo "5. Troubleshooting:"
    echo "   - If SigV4 Auth option is not visible, wait 2-3 minutes for Grafana initialization"
    echo "   - If authentication fails, verify IAM permissions on Grafana EC2 instance"
    echo "   - CloudFormation logs: /var/log/grafana-setup.log on EC2 instance"
    echo
    echo "==============================================="
}

dry_run_template_check() {
    local provided_ip="$1"
    
    log_info "DRY RUN MODE: Verifying local CloudFormation template and parameters"
    echo
    
    # Check for local template
    local local_template
    local_template=$(check_local_template)
    
    # Determine IP address for parameter
    local current_ip
    current_ip=$(get_current_ip "$provided_ip")
    
    echo "==============================================="
    echo "DRY RUN VERIFICATION (PARAMETER METHOD)"
    echo "==============================================="
    echo "Local Template: $local_template"
    echo "IP Parameter: $current_ip/32"
    echo
    
    # Show IP source information
    if [[ -n "$provided_ip" ]]; then
        echo "IP Address Source: Manually provided"
    else
        echo "IP Address Source: Auto-detected"
    fi
    echo
    
    # Validate CloudFormation template syntax
    log_info "Validating CloudFormation template syntax..."
    if aws cloudformation validate-template --template-body "file://$local_template" &>/dev/null; then
        echo "✓ CloudFormation template syntax is valid"
    else
        echo "✗ CloudFormation template syntax validation failed"
        echo "Run: aws cloudformation validate-template --template-body file://$local_template"
        return 1
    fi
    
    # Show parameter that will be passed
    echo
    echo "CloudFormation Parameters:"
    echo "  ParameterKey=AllowedIPRange,ParameterValue=$current_ip/32"
    echo
    echo "Template Features:"
    echo "  ✓ SigV4 Authentication: Pre-configured in UserData"
    echo "  ✓ Instance Type: m5.xlarge (enhanced performance)"
    echo "  ✓ Storage: 50GB GP3 (encrypted)"
    echo "  ✓ Security: Parameterized IP restriction"
    echo "  ✓ Monitoring: CloudFormation signals for deployment verification"
    echo
    echo "==============================================="
    echo "DRY RUN COMPLETE - Template is ready for deployment"
    echo "Remove --dry-run option to proceed with actual deployment"
    echo "==============================================="
}

check_stack_status() {
    log_info "STATUS CHECK MODE: Monitoring CloudFormation stack completion"
    echo
    
    echo "=============================================="
    echo "CloudFormation Stack Status Monitor"
    echo "=============================================="
    echo "Stack Name: $STACK_NAME"
    echo "Region: $REGION"
    echo "Check Interval: 5 seconds"
    echo
    
    local max_attempts=360  # 30 minutes (360 * 5 seconds)
    local attempt=0
    
    while [[ $attempt -lt $max_attempts ]]; do
        local status
        status=$(check_cloudformation_stack)
        
        local current_time
        current_time=$(date '+%H:%M:%S')
        
        case "$status" in
            "CREATE_COMPLETE")
                echo
                echo "🎉 CloudFormation Stack Creation COMPLETED! 🎉"
                echo "==============================================="
                echo
                
                # Get Grafana URL
                echo "📊 Retrieving Grafana Information..."
                local grafana_address
                if grafana_address=$(aws cloudformation describe-stacks \
                    --stack-name "$STACK_NAME" \
                    --region "$REGION" \
                    --query 'Stacks[0].Outputs[?OutputKey==`GrafanaInstanceAddress`].OutputValue' \
                    --output text 2>/dev/null); then
                    
                    local current_ip
                    current_ip=$(curl -s https://checkip.amazonaws.com 2>/dev/null || echo "Unable to determine")
                    
                    echo "✅ SUCCESS: Grafana is ready!"
                    echo
                    echo "🌐 Grafana Access Information:"
                    
                    # Ensure URL format is correct (avoid http://http:// duplication)
                    if [[ "$grafana_address" =~ ^https?:// ]]; then
                        echo "   URL: $grafana_address"
                    else
                        echo "   URL: http://$grafana_address"
                    fi
                    
                    echo "   Default Login: admin/admin"
                    echo "   Security: Access restricted to $current_ip/32"
                    echo
                    echo "🔗 Direct Browser Access:"
                    
                    # Show clickable URL for easy access
                    if [[ "$grafana_address" =~ ^https?:// ]]; then
                        echo "   Copy this URL to your browser: $grafana_address"
                    else
                        echo "   Copy this URL to your browser: http://$grafana_address"
                    fi
                    
                    echo
                    echo "📋 Next Steps:"
                    echo "   1. Access Grafana and change default password"
                    echo "   2. Configure Prometheus data source"
                    echo "   3. Import observability dashboards"
                    echo
                    echo "==============================================="
                else
                    echo "⚠️  Stack completed but Grafana URL not found"
                    echo "   Please check AWS Console for stack outputs"
                fi
                
                return 0
                ;;
            "UPDATE_COMPLETE")
                echo
                echo "🎉 CloudFormation Stack Update COMPLETED! 🎉"
                echo "==============================================="
                
                # Get Grafana URL for update case
                local grafana_address
                if grafana_address=$(aws cloudformation describe-stacks \
                    --stack-name "$STACK_NAME" \
                    --region "$REGION" \
                    --query 'Stacks[0].Outputs[?OutputKey==`GrafanaInstanceAddress`].OutputValue' \
                    --output text 2>/dev/null); then
                    
                    local current_ip
                    current_ip=$(curl -s https://checkip.amazonaws.com 2>/dev/null || echo "Unable to determine")
                    
                    echo "✅ Grafana Updated Successfully!"
                    
                    # Ensure URL format is correct (avoid http://http:// duplication)
                    if [[ "$grafana_address" =~ ^https?:// ]]; then
                        echo "   URL: $grafana_address"
                        echo "   Copy this URL to your browser: $grafana_address"
                    else
                        echo "   URL: http://$grafana_address"
                        echo "   Copy this URL to your browser: http://$grafana_address"
                    fi
                    
                    echo "   Security: Access restricted to $current_ip/32"
                fi
                
                return 0
                ;;
            "CREATE_FAILED"|"UPDATE_FAILED"|"ROLLBACK_COMPLETE"|"DELETE_COMPLETE")
                echo
                echo "❌ CloudFormation Stack FAILED with status: $status"
                echo "Check AWS Console for detailed error information"
                return 1
                ;;
            "CREATE_IN_PROGRESS")
                echo "[$current_time] ⏳ Creating... (attempt $((attempt+1))/$max_attempts)"
                ;;
            "UPDATE_IN_PROGRESS")
                echo "[$current_time] ⏳ Updating... (attempt $((attempt+1))/$max_attempts)"
                ;;
            "NOT_EXISTS")
                echo "❌ Stack does not exist. Please run the setup script first."
                return 1
                ;;
            *)
                echo "[$current_time] ❓ Unknown status: $status (attempt $((attempt+1))/$max_attempts)"
                ;;
        esac
        
        sleep 5
        ((attempt++))
    done
    
    echo
    echo "⏰ Timeout: Stack operation did not complete within 30 minutes"
    echo "Check AWS Console for current status"
    return 1
}

parse_arguments() {
    local provided_ip=""
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --ip)
                if [[ -n "$2" && ! "$2" =~ ^-- ]]; then
                    provided_ip="$2"
                    shift 2
                else
                    echo -e "${RED}[ERROR]${NC} Option --ip requires an IP address argument" >&2
                    show_usage
                    exit 1
                fi
                ;;
            --dry-run|--check-status|--help)
                # These options are handled in main function
                shift
                ;;
            *)
                echo -e "${RED}[ERROR]${NC} Unknown option: $1" >&2
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Validate IP address if provided
    if [[ -n "$provided_ip" ]]; then
        if ! validate_ip_address "$provided_ip"; then
            echo -e "${RED}[ERROR]${NC} Invalid IP address format: $provided_ip" >&2
            echo "Please provide a valid IPv4 address (e.g., 192.168.1.100)" >&2
            exit 1
        fi
        # Log to file only to avoid polluting function return value
        echo "$(date): [INFO] Using provided IP address: $provided_ip" >> "$LOG_FILE"
    fi
    
    echo "$provided_ip"
}

show_usage() {
    echo "Usage: $0 [OPTIONS]"
    echo
    echo "Options:"
    echo "  --ip IP_ADDRESS Specify IP address for security group restriction (default: auto-detect)"
    echo "  --dry-run       Verify CloudFormation template modification only (no deployment)"
    echo "  --check-status  Monitor CloudFormation stack completion and display Grafana URL when ready"
    echo "  --help          Show this help message"
    echo
    echo "Examples:"
    echo "  $0                              # Full setup with auto-detected IP (default)"
    echo "  $0 --ip 192.168.1.100         # Full setup with specific IP address"
    echo "  $0 --dry-run                   # Template verification only"
    echo "  $0 --dry-run --ip 10.0.0.50   # Template verification with specific IP"
    echo "  $0 --check-status              # Monitor stack completion (5-second intervals)"
    echo
    echo "Security Notes:"
    echo "  - The Grafana instance will be restricted to access from the specified IP address only"
    echo "  - If no IP is provided, the script will auto-detect your current public IP address"
    echo "  - Use a specific IP when running from environments where auto-detection might fail"
    echo
}

main() {
    echo "=============================================="
    echo "HyperPod Slurm Open Source Grafana Setup"
    echo "=============================================="
    echo
    echo "This script will set up observability using Open Source Grafana for:"
    echo "Cluster: $CLUSTER_NAME"
    echo "Region: $REGION"
    echo "Stack: $STACK_NAME"
    echo
    echo "Log file: $LOG_FILE"
    echo
    
    # Check for help option first
    if [[ "$*" == *"--help"* ]]; then
        show_usage
        exit 0
    fi
    
    # Check for dry-run option
    if [[ "$*" == *"--dry-run"* ]]; then
        echo "DRY RUN MODE: Template verification only"
        
        # Parse IP argument for dry run
        local provided_ip
        provided_ip=$(parse_arguments "$@")
        
        # Pass IP to dry run check
        dry_run_template_check "$provided_ip"
        exit 0
    fi
    
    # Check for status check option
    if [[ "$*" == *"--check-status"* ]]; then
        echo "STATUS CHECK MODE: Monitoring CloudFormation stack completion"
        check_stack_status
        exit $?
    fi
    
    # Parse command line arguments
    local provided_ip
    provided_ip=$(parse_arguments "$@")
    
    # Initialize log file
    echo "$(date): Starting HyperPod Open Source Grafana Observability Setup" > "$LOG_FILE"
    
    # Step 1: Check prerequisites (AWS and cluster)
    log_info "Step 1: Checking AWS and cluster prerequisites"
    check_aws_cli
    check_hyperpod_cluster
    
    # Step 2: Setup IAM permissions
    log_info "Step 2: Setting up IAM permissions"
    setup_iam_permissions
    
    # Step 3: Deploy CloudFormation stack
    log_info "Step 3: Deploying CloudFormation stack (Open Source Grafana + Prometheus)"
    deploy_observability_stack "$provided_ip"
    
    # Step 4: Update lifecycle scripts
    log_info "Step 4: Updating lifecycle scripts"
    update_lifecycle_scripts
    
    # Step 5: Install observability components
    log_info "Step 5: Installing observability components"
    install_observability_components
    
    # Step 6: Display next steps
    display_next_steps "$provided_ip"
    
    log_success "All automated steps completed successfully!"
}

# Execute main function if script is run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
