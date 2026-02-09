#!/bin/bash
# This script is executed on the remote instance via SSM Run Command
set -e

echo '=== Phase 0: AWS FPGA Simulation Setup ==='
echo "Started at: $(date)"
echo ""

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
sudo -u ubuntu bash -c "export XILINX_VIVADO=$XILINX_VIVADO && export PATH=$PATH && source hdk_setup.sh && env | grep -E '(HDK|VIVADO)' > /home/ubuntu/.fpga_env"

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

echo ""
echo '=== Phase 0 Setup Complete ==='
