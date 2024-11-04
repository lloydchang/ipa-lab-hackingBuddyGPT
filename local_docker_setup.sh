#!/opt/homebrew/bin/bash

# Purpose: Automates the setup of Docker containers for local testing on mac.
# Usage: ./local_docker_setup.sh

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

# Default value for base port
BASE_PORT=${BASE_PORT:-49152}

# Step 2: Define helper functions
# Function to find an available port
find_available_port() {
    local base_port="$1"
    local port=$base_port
    local max_port=65535
    while lsof -i :$port &>/dev/null; do 
        port=$((port + 1))
        if [ "$port" -gt "$max_port" ]; then
            echo "No available ports in the range $base_port-$max_port." >&2
            exit 1
        fi
    done
    echo $port
}

# Function to generate SSH key pair
generate_ssh_key() {
    ssh-keygen -t rsa -b 4096 -f ./local_ansible_id_rsa -N '' -q <<< y
    echo "New SSH key pair generated."
    chmod 600 ./local_ansible_id_rsa
}

# Function to create and start Docker container with SSH enabled
start_container() {
    local container_name="$1"
    local port="$2"
    local image_name="ansible-ready-ubuntu"

    if docker ps -aq -f name=${container_name} &>/dev/null; then
        echo "Container ${container_name} already exists. Removing it..." >&2
        docker stop ${container_name} &>/dev/null || true
        docker rm ${container_name} &>/dev/null || true
    fi

    echo "Starting Docker container ${container_name} on port ${port}..." >&2
    docker run -d --name ${container_name} -h ${container_name} -p "${port}:22" ${image_name}
    
    # Copy SSH public key to container
    docker cp ./local_ansible_id_rsa.pub ${container_name}:/home/ansible/.ssh/authorized_keys
    docker exec ${container_name} chown ansible:ansible /home/ansible/.ssh/authorized_keys
    docker exec ${container_name} chmod 600 /home/ansible/.ssh/authorized_keys
}

# Function to check if SSH is ready on a container
check_ssh_ready() {
    local port="$1"
    ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ./local_ansible_id_rsa -p ${port} ansible@127.0.0.1 exit 2>/dev/null
    return $?
}

# Step 3: Verify Docker Desktop
echo "Checking if Docker Desktop is running..."
if ! docker info >/dev/null 2>&1; then
    echo "Docker Desktop is not running. Please start Docker Desktop and try again."
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

# Step 5: Build Docker image
echo "Building Docker image with SSH enabled..."
if ! docker build -t ansible-ready-ubuntu -f codespaces_create_and_start_containers.Dockerfile .; then
    echo "Failed to build Docker image." >&2
    exit 1
fi

# Generate SSH key
generate_ssh_key

# Step 6: Create local inventory file
echo "Creating local Ansible inventory..."
cat > local_ansible_hosts.ini << EOF
[local]
127.0.0.1 ansible_port=PLACEHOLDER ansible_user=ansible ansible_ssh_private_key_file=./local_ansible_id_rsa ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null'

[all:vars]
ansible_python_interpreter=/usr/bin/python3
EOF

# Step 7: Start container and update inventory
available_port=$(find_available_port "$BASE_PORT")
start_container "local_ansible_test" "$available_port"

# Update the port in the inventory file
sed -i '' "s/PLACEHOLDER/$available_port/" local_ansible_hosts.ini

# Step 8: Wait for SSH service
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

# Step 9: Create ansible.cfg
cat > local_ansible.cfg << EOF
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

# Step 10: Set ANSIBLE_CONFIG and run playbook
export ANSIBLE_CONFIG=$(pwd)/local_ansible.cfg

echo "Running Ansible playbook..."
ansible-playbook -i local_ansible_hosts.ini tasks.yaml

echo "Setup complete. Container is ready for testing."
exit 0
