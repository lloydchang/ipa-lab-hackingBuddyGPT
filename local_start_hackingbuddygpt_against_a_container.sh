#!/bin/bash

# Purpose: Locally start hackingBuddyGPT against a container
# Usage: ./local_start_hackingbuddygpt_against_a_container.sh

# Enable strict error handling for better script robustness
set -e  # Exit immediately if a command exits with a non-zero status
set -u  # Treat unset variables as an error and exit immediately
set -o pipefail  # Return the exit status of the last command in a pipeline that failed
set -x  # Print each command before executing it (useful for debugging)

# Step 1: Install prerequisites

# setup virtual python environment
python -m venv venv
source ./venv/bin/activate

# install python requirements
pip install -e .

# Step 2: Request an OpenAI API key

# echo
# echo 'Currently, May 2024, running hackingBuddyGPT with GPT-4-turbo against a benchmark containing 13 VMs (with maximum 20 tries per VM) cost around $5.'
# echo
# echo 'Therefore, running hackingBuddyGPT with GPT-4-turbo against containing a container with maximum 10 tries would cost around $0.20.'
# echo
# echo "Enter your OpenAI API key and press the return key:"
# read OPENAI_API_KEY
# echo
# OPENAI_API_KEY=

# Step 3: Start hackingBuddyGPT against a container

echo "Starting hackingBuddyGPT against a container..."
echo

# ollama serve

# wintermute LinuxPrivesc --llm.api_key=$OPENAI_API_KEY --llm.model=llama3.1:latest --llm.context_size=8192 --conn.host=127.0.0.1 --conn.port 49152 --conn.username=lowpriv --conn.password=trustno1 --conn.hostname=test1 --llm.api_url=http://localhost:11434

# docker run -d -p 8080:8080/tcp zhu327/gemini-openai-proxy

wintermute LinuxPrivesc --llm.api_key=$OPENAI_API_KEY --llm.model=gpt-4-turbo --llm.context_size=8192 --conn.host=127.0.0.1 --conn.port 49152 --conn.username=lowpriv --conn.password=trustno1 --conn.hostname=test1 --llm.api_url=http://localhost:8080 --llm.api_backoff=60
