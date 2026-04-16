#!/bin/bash
#SBATCH --job-name=nki_test
#SBATCH --partition=trn2-queue
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --output=%x_%j.out
#SBATCH --error=%x_%j.err

echo "[INFO] Starting NKI test job"
echo "[INFO] Job ID: $SLURM_JOB_ID"
echo "[INFO] Node: $SLURMD_NODENAME"
echo "[INFO] Date: $(date)"

# Check if Neuron SDK is installed
if [ ! -d "/opt/neuron_venv" ]; then
    echo "[INFO] Neuron SDK not found, installing..."

    # Copy and run installation script
    if [ -f "/home/ubuntu/install-neuron-sdk.sh" ]; then
        sudo bash /home/ubuntu/install-neuron-sdk.sh
    else
        echo "[ERROR] Installation script not found"
        exit 1
    fi
fi

# Activate Neuron environment
echo "[INFO] Activating Neuron environment"
source /opt/neuron_venv/bin/activate

# Check NKI version
echo "[INFO] Checking NKI installation"
python3 -c "import nki; print(f'[OK] NKI version: {nki.__version__}')" || exit 1

# Run test script
echo "[INFO] Running NKI test"
python3 /home/ubuntu/test_nki.py

echo "[INFO] NKI test job completed"
