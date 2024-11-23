#!/opt/homebrew/bin/bash

# Purpose: Automates the setup of docker containers for local testing on Mac.
# Usage: ./mac_create_and_start_containers.sh

# Enable strict error handling
set -e
set -u
set -o pipefail
set -x

# Step 1: Initialization

if [ ! -f hosts.ini ]; then
    echo "hosts.ini not found! Please ensure your Ansible inventory file exists."
    exit 1
fi

if [ ! -f tasks.yaml ]; then
    echo "tasks.yaml not found! Please ensure your Ansible playbook file exists."
    exit 1
fi

# Default values for network and base port, can be overridden by environment variables
DOCKER_NETWORK_NAME=${DOCKER_NETWORK_NAME:-192_168_65_0_24}
DOCKER_NETWORK_SUBNET="192.168.65.0/24"
BASE_PORT=${BASE_PORT:-49152}

# Step 2: Source common functions
source ./common_functions.sh

# Step 3: Verify docker Desktop

echo "Checking if docker Desktop is running..."
if ! docker --debug info; then
    echo If the above says
    echo
    echo "Server:"
    echo "ERROR: request returned Internal Server Error for API route and version http://%2FUsers%2Fusername%2F.docker%2Frun%2Fdocker.sock/v1.47/info, check if the server supports the requested API version"
    echo "errors pretty printing info"
    echo
    echo You may need to uninstall Docker Desktop https://docs.docker.com/desktop/uninstall/ and reinstall it from https://docs.docker.com/desktop/setup/install/mac-install/ and try again.
    echo
    echo Alternatively, restart Docker Desktop and try again.
    echo
    echo There are known issues with Docker Desktop on Mac, such as:
    echo
    echo Bug: Docker CLI Hangs for all commands
    echo https://github.com/docker/for-mac/issues/6940
    echo
    echo Regression: Docker does not recover from resource saver mode
    echo https://github.com/docker/for-mac/issues/6933
    echo
    echo "Docker Desktop is not running. Please start Docker Desktop and try again."
    echo
    exit 1
fi

# Step 4: Install prerequisites

echo "Installing required Python packages..."
if ! command -v pip3 >/dev/null 2>&1; then
    echo "pip3 not found. Please install Python3 and pip3 first."
    exit 1
fi

echo "Installing Ansible and passlib using pip..."
pip3 install ansible passlib

# Step 5: Build docker image

echo "Building docker image with SSH enabled..."
if ! docker --debug build -t ansible-ready-ubuntu -f codespaces_create_and_start_containers.Dockerfile .; then
    echo "Failed to build docker image." >&2
    exit 1
fi

# Step 6: Generate SSH key
generate_ssh_key

# Step 7: Create mac inventory file

echo "Creating mac Ansible inventory..."
cat > mac_ansible_hosts.ini << EOF
[local]
localhost ansible_port=PLACEHOLDER ansible_user=ansible ansible_ssh_private_key_file=./mac_ansible_id_rsa ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'

[all:vars]
ansible_python_interpreter=/usr/bin/python3
EOF

# Step 8: Start container and update inventory

available_port=$(find_available_port "$BASE_PORT")
# Pass localhost as container_ip since we're running on macOS
start_container "ansible-ready-ubuntu" "$available_port" "localhost"

# Update the port in the inventory file
sed -i '' "s/PLACEHOLDER/$available_port/" mac_ansible_hosts.ini

# Step 9: Wait for SSH service

echo "Waiting for SSH service to start..."
max_attempts=30
attempt=1
while [ $attempt -le $max_attempts ]; do
    if check_ssh_ready "$available_port"; then
        echo "SSH is ready!"
        break
    fi
    echo "Waiting for SSH to be ready (attempt $attempt/$max_attempts)..."
    sleep 2
    attempt=$((attempt + 1))
done

if [ $attempt -gt $max_attempts ]; then
    echo "SSH service failed to start. Exiting."
    exit 1
fi

# Step 10: Create ansible.cfg

cat > mac_ansible.cfg << EOF
[defaults]
interpreter_python = auto_silent
host_key_checking = False
remote_user = ansible

[privilege_escalation]
become = True
become_method = sudo
become_user = root
become_ask_pass = False
EOF

# Step 11: Set ANSIBLE_CONFIG and run playbook

export ANSIBLE_CONFIG=$(pwd)/mac_ansible.cfg

echo "Running Ansible playbook..."
ansible-playbook -i mac_ansible_hosts.ini tasks.yaml

echo "Setup complete. Container ansible-ready-ubuntu is ready for testing."

# Step 12: Run gemini-openai-proxy container

if docker --debug ps -aq -f name=gemini-openai-proxy; then
    echo "Container gemini-openai-proxy already exists. Removing it..." >&2
    docker --debug stop gemini-openai-proxy || true
    docker --debug rm gemini-openai-proxy || true
fi

docker --debug run --restart=unless-stopped -it -d -p 8080:8080 --name gemini-openai-proxy zhu327/gemini-openai-proxy:latest

# Step 13: Ready to run hackingBuddyGPT

echo "You can now run ./mac_start_hackingbuddygpt_against_a_container.sh"

exit 0
