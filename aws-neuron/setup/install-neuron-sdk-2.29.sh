#!/bin/bash
set -euo pipefail

# ============================================================================
# Neuron SDK Installation Script
# ============================================================================
# Version: 1.0.0
# Target Neuron SDK: 2.29.x
# Target OS: Ubuntu 22.04
# Last Updated: 2026-04-15
# Repository: https://github.com/littlemex/samples
# ============================================================================

SCRIPT_VERSION="1.0.0"
TARGET_NEURON_SDK="2.29.x"
TARGET_OS="Ubuntu 22.04"

# Map Neuron SDK version to PyTorch Neuron packages
case "${TARGET_NEURON_SDK}" in
  2.29.*)
    TORCH_NEURONX_VERSION="2.6.*"
    NEURONX_CC_VERSION="2.*"
    ;;
  2.30.*)
    # Placeholder for future version
    TORCH_NEURONX_VERSION="2.7.*"
    NEURONX_CC_VERSION="2.*"
    ;;
  *)
    echo "[ERROR] Unsupported Neuron SDK version: ${TARGET_NEURON_SDK}"
    exit 1
    ;;
esac

echo "============================================================================"
echo "Neuron SDK Installation Script"
echo "  Script Version: ${SCRIPT_VERSION}"
echo "  Target Neuron SDK: ${TARGET_NEURON_SDK}"
echo "  Target OS: ${TARGET_OS}"
echo "  torch-neuronx: ${TORCH_NEURONX_VERSION}"
echo "  neuronx-cc: ${NEURONX_CC_VERSION}"
echo "============================================================================"
echo ""
echo "[INFO] Starting Neuron SDK installation"

# Neuron APT repository setup
. /etc/os-release
sudo tee /etc/apt/sources.list.d/neuron.list > /dev/null <<EOF
deb https://apt.repos.neuron.amazonaws.com ${VERSION_CODENAME} main
EOF

wget -qO - https://apt.repos.neuron.amazonaws.com/GPG-PUB-KEY-AMAZON-AWS-NEURON.PUB | sudo apt-key add -

# Update and install Neuron packages
sudo apt-get update -y
sudo apt-get install -y aws-neuronx-dkms aws-neuronx-collectives aws-neuronx-runtime-lib aws-neuronx-tools

# Install Python and create venv
sudo apt-get install -y python3.10 python3.10-venv python3-pip

# Create Neuron Python environment
python3.10 -m venv /opt/neuron_venv
source /opt/neuron_venv/bin/activate

pip install -U pip setuptools
pip install torch-neuronx==${TORCH_NEURONX_VERSION} neuronx-cc==${NEURONX_CC_VERSION} --extra-index-url https://pip.repos.neuron.amazonaws.com
pip install neuronx-distributed
# NKI is installed automatically as a dependency of neuronx-cc

# Create activation script
sudo tee /etc/profile.d/neuron.sh > /dev/null <<'ENVEOF'
export PATH=/opt/aws/neuron/bin:$PATH
source /opt/neuron_venv/bin/activate
ENVEOF

# Verification
echo ""
echo "[INFO] Verifying installation..."
neuron-ls --version || true
python3 -c "import torch_neuronx; print(f'torch-neuronx: {torch_neuronx.__version__}')" || true
python3 -c "import neuronx_cc; import neuronx_cc.nki as nki; print(f'neuronx-cc: {neuronx_cc.__version__}'); print(f'NKI: {nki.__version__}')" || true

deactivate

echo ""
echo "============================================================================"
echo "[SUCCESS] Neuron SDK installation completed"
echo "  Script Version: ${SCRIPT_VERSION}"
echo "  Target Neuron SDK: ${TARGET_NEURON_SDK}"
echo "  torch-neuronx: ${TORCH_NEURONX_VERSION}"
echo "  neuronx-cc: ${NEURONX_CC_VERSION}"
echo "  Installation Path: /opt/neuron_venv"
echo "============================================================================"
