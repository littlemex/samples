#!/bin/bash
# Phase 0: AWS FPGA Simulation Environment Setup Script
#
# This script sets up aws-fpga environment on an EC2 instance for Phase 0 (simulation only).
# It can be executed via SSM Run Command or directly on the instance.

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Usage
print_usage() {
  cat << EOF
Usage: ./setup-phase0.sh [OPTIONS]

Setup aws-fpga environment for Phase 0 (simulation).

Options:
  -i INSTANCE_ID    EC2 instance ID (required for remote execution)
  -r REGION         AWS region (default: us-east-1)
  --local           Run setup locally (on the instance itself)
  --help            Show this help message

Examples:
  # Remote execution via SSM
  ./setup-phase0.sh -i i-0123456789abcdef0 -r us-east-1

  # Local execution (on the instance)
  ./setup-phase0.sh --local

  # Remote execution with profile
  AWS_PROFILE=my-profile ./setup-phase0.sh -i i-0123456789abcdef0
EOF
}

# Parse arguments
INSTANCE_ID=""
REGION="us-east-1"
LOCAL_MODE=false

while [[ $# -gt 0 ]]; do
  case $1 in
    -i)
      INSTANCE_ID="$2"
      shift 2
      ;;
    -r)
      REGION="$2"
      shift 2
      ;;
    --local)
      LOCAL_MODE=true
      shift
      ;;
    --help)
      print_usage
      exit 0
      ;;
    *)
      log_error "Unknown option: $1"
      print_usage
      exit 1
      ;;
  esac
done

# Setup function (executed on the instance)
setup_phase0() {
  log_info "Starting Phase 0 setup..."

  # 1. Clone aws-fpga repository
  log_info "[1/6] Cloning aws-fpga repository..."
  if [ ! -d /home/ubuntu/aws-fpga ]; then
    cd /home/ubuntu
    sudo -u ubuntu git clone https://github.com/aws/aws-fpga.git
    cd aws-fpga
    sudo -u ubuntu git checkout master
    log_success "aws-fpga cloned successfully"
  else
    log_warn "aws-fpga already exists, pulling latest..."
    cd /home/ubuntu/aws-fpga
    sudo -u ubuntu git pull
    log_success "aws-fpga updated"
  fi

  # 2. Configure Vivado path (F2 AMI uses /opt/Xilinx instead of /tools)
  log_info "[2/6] Configuring Vivado path..."
  if [ -d /opt/Xilinx/2025.2/Vivado/bin ]; then
    export XILINX_VIVADO=/opt/Xilinx/2025.2/Vivado
    export PATH=/opt/Xilinx/2025.2/Vivado/bin:$PATH
    log_success "Vivado found at /opt/Xilinx/2025.2/Vivado"
  elif [ -d /tools/Xilinx/Vivado ]; then
    export XILINX_VIVADO=/tools/Xilinx/Vivado
    log_success "Vivado found at /tools/Xilinx/Vivado"
  else
    log_warn "Vivado not found in standard locations"
  fi

  # 3. Patch supported Vivado versions if needed
  log_info "[3/6] Checking Vivado version compatibility..."
  cd /home/ubuntu/aws-fpga
  if ! grep -q "v2025.2" supported_vivado_versions.txt 2>/dev/null; then
    echo "vivado v2025.2 (64-bit)" >> supported_vivado_versions.txt
    log_success "Added Vivado 2025.2 to supported versions"
  else
    log_success "Vivado 2025.2 already in supported versions"
  fi

  # 4. Configure git ownership
  log_info "[4/6] Configuring git ownership..."
  git config --global --add safe.directory /home/ubuntu/aws-fpga
  log_success "Git ownership configured"

  # 5. Setup HDK environment
  log_info "[5/6] Setting up HDK environment..."
  sudo -u ubuntu bash -c 'export XILINX_VIVADO='"$XILINX_VIVADO"' && export PATH='"$PATH"' && source hdk_setup.sh && env | grep -E "(HDK|VIVADO)" > /home/ubuntu/.fpga_env'
  log_success "HDK environment configured"

  # 6. Add to .bashrc
  log_info "[6/9] Adding HDK setup to .bashrc..."
  if ! grep -q 'hdk_setup.sh' /home/ubuntu/.bashrc; then
    cat >> /home/ubuntu/.bashrc << 'EOF'

# AWS FPGA HDK Environment
if [ -f ~/aws-fpga/hdk_setup.sh ]; then
  source ~/aws-fpga/hdk_setup.sh
fi
EOF
    log_success ".bashrc updated"
  else
    log_warn ".bashrc already contains hdk_setup.sh"
  fi

  # 7. Check Vivado
  log_info "[7/9] Checking Vivado installation..."
  if command -v vivado &> /dev/null; then
    VIVADO_VERSION=$(vivado -version 2>/dev/null | head -1 || echo "Unable to get version")
    log_success "Vivado found: $VIVADO_VERSION"
  else
    log_warn "Vivado not found in PATH"
    log_warn "This is expected if using Ubuntu base AMI"
    log_warn "For FPGA Developer AMI, Vivado should be at /tools/Xilinx/Vivado/"
  fi

  # 8. Create Phase 0 workspace
  log_info "[8/9] Creating Phase 0 workspace..."
  sudo -u ubuntu mkdir -p /home/ubuntu/fpga-phase0/{experiments,results/{benchmarks,waveforms},artifacts}
  log_success "Phase 0 workspace created: /home/ubuntu/fpga-phase0"

  # 9. Verification
  log_info "[9/9] Setup verification..."
  echo ""
  echo "=== Setup Summary ==="
  echo "aws-fpga location: /home/ubuntu/aws-fpga"
  if [ -f /home/ubuntu/.fpga_env ]; then
    echo "HDK environment variables:"
    cat /home/ubuntu/.fpga_env | head -5
  fi
  echo "Phase 0 workspace: /home/ubuntu/fpga-phase0"
  echo ""

  # Completion flag
  echo 'Phase 0 setup completed successfully' > /tmp/phase0-setup-complete.txt
  echo "Completed at: $(date)" >> /tmp/phase0-setup-complete.txt

  log_success "Phase 0 setup complete!"
  echo ""
  echo "=== Next Steps ==="
  echo "1. Verify setup: source ~/.bashrc && echo \$HDK_DIR"
  echo "2. Run cl_hello_world simulation:"
  echo "   cd ~/aws-fpga/hdk/cl/examples/cl_hello_world/verif/scripts"
  echo "   make TEST=test_hello_world"
  echo ""
}

# Main execution
if [ "$LOCAL_MODE" = true ]; then
  # Local execution (on the instance)
  log_info "Running setup locally..."
  setup_phase0
else
  # Remote execution via SSM
  if [ -z "$INSTANCE_ID" ]; then
    log_error "Instance ID is required for remote execution"
    print_usage
    exit 1
  fi

  log_info "Running Phase 0 setup on instance $INSTANCE_ID..."

  # Execute via SSM Run Command
  COMMAND_ID=$(aws ssm send-command \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" \
    --document-name "AWS-RunShellScript" \
    --comment "Phase 0: FPGA Simulation Setup" \
    --parameters commands="$(cat << 'SCRIPT'
#!/bin/bash
set -e

echo '=== Phase 0: AWS FPGA Simulation Setup ==='
echo "Started at: $(date)"

# 1. Clone aws-fpga
if [ ! -d /home/ubuntu/aws-fpga ]; then
  echo '[1/9] Cloning aws-fpga repository...'
  cd /home/ubuntu
  sudo -u ubuntu git clone https://github.com/aws/aws-fpga.git
  cd aws-fpga
  sudo -u ubuntu git checkout master
else
  echo '[1/9] Updating aws-fpga repository...'
  cd /home/ubuntu/aws-fpga
  sudo -u ubuntu git pull
fi

# 2. Configure Vivado path (F2 AMI uses /opt/Xilinx instead of /tools)
echo '[2/9] Configuring Vivado path...'
if [ -d /opt/Xilinx/2025.2/Vivado/bin ]; then
  export XILINX_VIVADO=/opt/Xilinx/2025.2/Vivado
  export PATH=/opt/Xilinx/2025.2/Vivado/bin:$PATH
  echo 'Vivado found at /opt/Xilinx/2025.2/Vivado'
elif [ -d /tools/Xilinx/Vivado ]; then
  export XILINX_VIVADO=/tools/Xilinx/Vivado
  echo 'Vivado found at /tools/Xilinx/Vivado'
else
  echo 'Vivado not found in standard locations'
fi

# 3. Patch supported Vivado versions if needed
echo '[3/9] Checking Vivado version compatibility...'
cd /home/ubuntu/aws-fpga
if ! grep -q "v2025.2" supported_vivado_versions.txt 2>/dev/null; then
  echo "vivado v2025.2 (64-bit)" >> supported_vivado_versions.txt
  echo 'Added Vivado 2025.2 to supported versions'
else
  echo 'Vivado 2025.2 already in supported versions'
fi

# 4. Configure git ownership
echo '[4/9] Configuring git ownership...'
git config --global --add safe.directory /home/ubuntu/aws-fpga
echo 'Git ownership configured'

# 5. Setup HDK environment
echo '[5/9] Setting up HDK environment...'
cd /home/ubuntu/aws-fpga
sudo -u ubuntu bash -c 'export XILINX_VIVADO='$XILINX_VIVADO' && export PATH='$PATH' && source hdk_setup.sh && env | grep -E "(HDK|VIVADO)" > /home/ubuntu/.fpga_env'

# 6. Add to .bashrc
echo '[6/9] Adding to .bashrc...'
if ! grep -q 'hdk_setup.sh' /home/ubuntu/.bashrc; then
  echo '' >> /home/ubuntu/.bashrc
  echo '# AWS FPGA HDK Environment' >> /home/ubuntu/.bashrc
  echo 'if [ -f ~/aws-fpga/hdk_setup.sh ]; then' >> /home/ubuntu/.bashrc
  echo '  source ~/aws-fpga/hdk_setup.sh' >> /home/ubuntu/.bashrc
  echo 'fi' >> /home/ubuntu/.bashrc
fi

# 7. Check Vivado
echo '[7/9] Checking Vivado...'
if command -v vivado &> /dev/null; then
  vivado -version | head -1
else
  echo 'Vivado not found (expected for Ubuntu base AMI)'
fi

# 8. Create workspace
echo '[8/9] Creating Phase 0 workspace...'
sudo -u ubuntu mkdir -p /home/ubuntu/fpga-phase0/{experiments,results/{benchmarks,waveforms},artifacts}

# 9. Complete
echo '[9/9] Setup complete!'
echo 'Phase 0 setup completed' > /tmp/phase0-setup-complete.txt
echo "Completed at: $(date)" >> /tmp/phase0-setup-complete.txt
SCRIPT
)" \
    --output json \
    --query 'Command.CommandId' \
    --output text)

  log_info "Command ID: $COMMAND_ID"
  log_info "Waiting for command execution..."

  # Wait for completion
  aws ssm wait command-executed \
    --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" \
    --region "$REGION" || true

  # Get command result
  COMMAND_STATUS=$(aws ssm get-command-invocation \
    --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" \
    --region "$REGION" \
    --query 'Status' \
    --output text)

  if [ "$COMMAND_STATUS" = "Success" ]; then
    log_success "Phase 0 setup completed successfully!"

    # Show output
    echo ""
    echo "=== Command Output ==="
    aws ssm get-command-invocation \
      --command-id "$COMMAND_ID" \
      --instance-id "$INSTANCE_ID" \
      --region "$REGION" \
      --query 'StandardOutputContent' \
      --output text
  else
    log_error "Setup failed with status: $COMMAND_STATUS"

    # Show error
    echo ""
    echo "=== Error Output ==="
    aws ssm get-command-invocation \
      --command-id "$COMMAND_ID" \
      --instance-id "$INSTANCE_ID" \
      --region "$REGION" \
      --query 'StandardErrorContent' \
      --output text
    exit 1
  fi
fi
