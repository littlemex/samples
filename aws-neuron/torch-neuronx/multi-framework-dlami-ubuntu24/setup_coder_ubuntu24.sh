#!/bin/bash
set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parameters
CODE_SERVER_USER="coder"
HOME_FOLDER="/home/coder"
CODE_SERVER_PASSWORD=$(openssl rand -base64 32)

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Ubuntu 24 Code Server Setup Script${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Parameters:"
echo "  User: ${CODE_SERVER_USER}"
echo "  Home: ${HOME_FOLDER}"
echo ""

# Function to print step
print_step() {
    echo -e "${YELLOW}===> $1${NC}"
}

# Function to check command status
check_status() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Success${NC}"
    else
        echo -e "${RED}✗ Failed${NC}"
        exit 1
    fi
}

# Step 1: Configure needrestart settings
print_step "Step 1: Configuring needrestart settings"
dpkg --configure -a
sed -i 's/#$nrconf{kernelhints} = -1;/$nrconf{kernelhints} = 0;/' /etc/needrestart/needrestart.conf
sed -i 's/#$nrconf{verbosity} = 2;/$nrconf{verbosity} = 0;/' /etc/needrestart/needrestart.conf
sed -i "s/#\$nrconf{restart} = 'i';/\$nrconf{restart} = 'a';/" /etc/needrestart/needrestart.conf
echo "Checking needrestart configuration..."
cat /etc/needrestart/needrestart.conf | grep -E '(kernelhints|verbosity|restart)'
check_status

# Step 2: Cleanup old Neuron repo
print_step "Step 2: Cleaning up old Neuron repository"
rm -f /etc/apt/sources.list.d/neuron.list
check_status

# Step 3: Wait for dpkg lock and install base packages
print_step "Step 3: Waiting for dpkg lock and installing base packages"
echo "Waiting for dpkg lock to be released..."
timeout=300
elapsed=0
while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || \
      fuser /var/lib/apt/lists/lock >/dev/null 2>&1 || \
      fuser /var/cache/apt/archives/lock >/dev/null 2>&1; do
  if [ $elapsed -ge $timeout ]; then
    echo "Timeout waiting for dpkg lock"
    break
  fi
  echo "Waiting for dpkg lock... ($elapsed seconds)"
  sleep 5
  elapsed=$((elapsed + 5))
done

dpkg --configure -a
apt-get -q update
DEBIAN_FRONTEND=noninteractive apt-get install -y -q curl gnupg whois argon2 unzip nginx openssl locales locales-all apt-transport-https ca-certificates software-properties-common python3-pip nodejs npm graphviz jq
check_status

# Step 4: Add user
print_step "Step 4: Creating/configuring user: ${CODE_SERVER_USER}"
dpkg --configure -a
if [[ "${CODE_SERVER_USER}" == "ubuntu" ]]; then
  echo "Using existing user: ${CODE_SERVER_USER}"
else
  if id "${CODE_SERVER_USER}" &>/dev/null; then
    echo "User ${CODE_SERVER_USER} already exists"
  else
    adduser --disabled-password --gecos '' ${CODE_SERVER_USER}
    echo "${CODE_SERVER_USER}:${CODE_SERVER_PASSWORD}" | chpasswd
    usermod -aG sudo ${CODE_SERVER_USER}
  fi
fi

tee /etc/sudoers.d/91-vscode-user <<EOF
${CODE_SERVER_USER} ALL=(ALL) NOPASSWD:ALL
EOF

mkdir -p /home/${CODE_SERVER_USER}
chown -R ${CODE_SERVER_USER}:${CODE_SERVER_USER} /home/${CODE_SERVER_USER}
mkdir -p /home/${CODE_SERVER_USER}/.local/bin
chown -R ${CODE_SERVER_USER}:${CODE_SERVER_USER} /home/${CODE_SERVER_USER}
echo "User configuration:"
getent passwd ${CODE_SERVER_USER}
check_status

# Step 5: Update profile
print_step "Step 5: Updating user profile"
echo "LANG=en_US.utf-8" >> /etc/environment
echo "LC_ALL=en_US.UTF-8" >> /etc/environment
echo "PATH=\$PATH:/home/${CODE_SERVER_USER}/.local/bin" >> /home/${CODE_SERVER_USER}/.bashrc
echo "export PATH" >> /home/${CODE_SERVER_USER}/.bashrc
echo "export NEXT_TELEMETRY_DISABLED=1" >> /home/${CODE_SERVER_USER}/.bashrc
echo "export PS1='\[\033[01;32m\]\u:\[\033[01;34m\]\w\[\033[00m\]\$ '" >> /home/${CODE_SERVER_USER}/.bashrc
chown -R ${CODE_SERVER_USER}:${CODE_SERVER_USER} /home/${CODE_SERVER_USER}
check_status

# Step 6: Install and configure code-server
print_step "Step 6: Installing and configuring code-server"
export HOME=/home/${CODE_SERVER_USER}
curl -fsSL https://code-server.dev/install.sh | bash -s -- 2>&1
systemctl enable --now code-server@${CODE_SERVER_USER} 2>&1

# Create nginx configuration (without DevServer location block)
tee /etc/nginx/conf.d/code-server.conf <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name *.cloudfront.net;
    location / {
      proxy_pass http://localhost:8080/;
      proxy_set_header Host \$host;
      proxy_set_header Upgrade \$http_upgrade;
      proxy_set_header Connection upgrade;
      proxy_set_header Accept-Encoding gzip;
    }
}
EOF

# Configure code-server
mkdir -p /home/${CODE_SERVER_USER}/.config/code-server
tee /home/${CODE_SERVER_USER}/.config/code-server/config.yaml <<EOF
cert: false
auth: password
hashed-password: "$(echo -n ${CODE_SERVER_PASSWORD} | argon2 $(openssl rand -base64 12) -e)"
EOF

mkdir -p /home/${CODE_SERVER_USER}/.local/share/code-server/User/
touch /home/${CODE_SERVER_USER}/.hushlogin
mkdir -p ${HOME_FOLDER}
chown -R ${CODE_SERVER_USER}:${CODE_SERVER_USER} ${HOME_FOLDER}

tee /home/${CODE_SERVER_USER}/.local/share/code-server/User/settings.json <<EOF
{
  "extensions.autoUpdate": false,
  "extensions.autoCheckUpdates": false,
  "telemetry.telemetryLevel": "off",
  "security.workspace.trust.startupPrompt": "never",
  "security.workspace.trust.enabled": false,
  "security.workspace.trust.banner": "never",
  "security.workspace.trust.emptyWindow": false,
  "auto-run-command.rules": [
    {
      "command": "workbench.action.terminal.new"
    }
  ]
}
EOF

chown -R ${CODE_SERVER_USER}:${CODE_SERVER_USER} /home/${CODE_SERVER_USER}
systemctl restart code-server@${CODE_SERVER_USER}
systemctl restart nginx

# Install VS Code extensions
echo "Installing VS Code extensions..."
sudo -u ${CODE_SERVER_USER} --login code-server --install-extension AmazonWebServices.aws-toolkit-vscode --force || echo "AWS Toolkit installation skipped"
sudo -u ${CODE_SERVER_USER} --login code-server --install-extension AmazonWebServices.amazon-q-vscode --force || echo "Amazon Q installation skipped"
sudo -u ${CODE_SERVER_USER} --login code-server --install-extension saoudrizwan.claude-dev --force || echo "Cline installation skipped"
chown -R ${CODE_SERVER_USER}:${CODE_SERVER_USER} /home/${CODE_SERVER_USER}

echo "Testing nginx configuration..."
nginx -t 2>&1
echo "Checking nginx status..."
systemctl status nginx --no-pager || true
echo "Checking code-server version..."
code-server -v
echo "Checking code-server status..."
systemctl status code-server@${CODE_SERVER_USER} --no-pager || true
check_status

# Step 7: Setup code command
print_step "Step 7: Setting up 'code' command"
cat > /usr/local/bin/code << 'EOF'
#!/bin/bash
if [ "$1" = "." ]; then
  current_dir=$(pwd)
  /usr/bin/code-server $current_dir
elif [ -n "$1" ]; then
  target=$(realpath "$1" 2>/dev/null || echo "$1")
  /usr/bin/code-server $target
fi
EOF
chmod +x /usr/local/bin/code
check_status

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup completed successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Code-server is running on port 8080"
echo "Nginx is proxying on port 80"
echo ""
echo "Password: ${CODE_SERVER_PASSWORD}"
echo ""
echo "IMPORTANT: Save this password! You'll need it to access code-server."
echo ""
echo "To access code-server, visit: http://<your-server-ip> (via nginx on port 80)"
echo ""
