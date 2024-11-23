#!/bin/bash

# Function to find an available port starting from a base port
find_available_port() {
    local base_port="$1"
    local port=$base_port
    local max_port=65535
    while ss -tuln | grep -q ":$port "; do
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
    ssh-keygen -t rsa -b 4096 -f ./codespaces_ansible_id_rsa -N '' -q <<< y
    echo "New SSH key pair generated."
    chmod 600 ./codespaces_ansible_id_rsa
}

# Function to create and start Docker container with SSH enabled
start_container() {
    local container_name="$1"
    local base_port="$2"
    local container_ip="$3"
    local image_name="ansible-ready-ubuntu"

    if [ "$(docker ps -aq -f name=${container_name})" ]; then
        echo "Container ${container_name} already exists. Removing it..." >&2
        docker stop ${container_name} > /dev/null 2>&1 || true
        docker rm ${container_name} > /dev/null 2>&1 || true
    fi

    echo "Starting Docker container ${container_name} with IP ${container_ip} on port ${base_port}..." >&2
    docker run -d --name ${container_name} -h ${container_name} --network ${DOCKER_NETWORK_NAME} --ip ${container_ip} -p "${base_port}:22" ${image_name} > /dev/null 2>&1
    
    # Copy SSH public key to container
    docker cp ./codespaces_ansible_id_rsa.pub ${container_name}:/home/ansible/.ssh/authorized_keys
    docker exec ${container_name} chown ansible:ansible /home/ansible/.ssh/authorized_keys
    docker exec ${container_name} chmod 600 /home/ansible/.ssh/authorized_keys

    echo "${container_ip}"
}

# Function to check if SSH is ready on a container
check_ssh_ready() {
    local container_ip="$1"
    timeout 1 ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ./codespaces_ansible_id_rsa ansible@${container_ip} exit 2>/dev/null
    return $?
}

# Function to replace IP address and add Ansible configuration
replace_ip_and_add_config() {
    local original_ip="$1"
    local container_name="${original_ip//./_}"

    # Find an available port for the container
    local available_port=$(find_available_port "$BASE_PORT")

    # Start the container with the available port
    local container_ip=$(start_container "$container_name" "$available_port" "$original_ip")

    # Replace the original IP with the new container IP and add Ansible configuration
    sed -i "s/^[[:space:]]*$original_ip[[:space:]]*$/$container_ip ansible_user=ansible ansible_ssh_private_key_file=.\/codespaces_ansible_id_rsa ansible_ssh_common_args='-o StrictHostKeyChecking=no -o UserKnownHostsFile=\/dev\/null'/" codespaces_ansible_hosts.ini

    echo "Started container ${container_name} with IP ${container_ip}, mapped to host port ${available_port}"
    echo "Updated IP ${original_ip} to ${container_ip} in codespaces_ansible_hosts.ini"

    # Increment BASE_PORT for the next container
    BASE_PORT=$((available_port + 1))
}
