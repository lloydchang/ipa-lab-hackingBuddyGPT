#!/usr/bin/python

import os
import time

from dotenv import load_dotenv

from history import ResultHistory, num_tokens_from_string
from targets.ssh import get_ssh_connection, SSHHostConn
from llms.openai_rest import openai_config, get_openai_response
from prompt_helper import LLM

from rich.console import Console
from rich.panel import Panel

# setup some infrastructure
cmd_history = ResultHistory()

# read configuration from env and configure system parts
load_dotenv()
openai_config()
conn = get_ssh_connection()
conn.connect()

print("Get initial user from virtual machine:")
initial_user = conn.run("whoami")

llm = LLM(get_openai_response)

sysinfo = "This is a linux-based system."

console = Console()

context_size = int(os.getenv("CONTEXT_SIZE"))
print("used model: " + os.getenv("MODEL") + " context-size: " + os.getenv("CONTEXT_SIZE"))

state = """
- this is a linux system
- your low privilege user credentials are lowpriv:trustno1
"""

# maybe generate list of potential vulnerabilities based upon the system facts


while True:
    # todo: take the list of potential vulnerabilities, go through each element and try up to 10 times to exploit the vulnerability

    state_size = num_tokens_from_string(state)

    tic = time.perf_counter()
    next_cmd = llm.create_and_ask_prompt('query_next_command.txt', "next-cmd", user=initial_user, password=os.getenv("TARGET_PASSWORD"), history=cmd_history.get_history(limit=context_size-state_size), state=state)
    toc = time.perf_counter()
    diff = str(toc-tic)

    if next_cmd["type"]  == "cmd":
        # run the command
        cmd = next_cmd["cmd"]
        resp = conn.run(cmd)
        console.print(Panel(resp, title=cmd))

        # analyze the result and update your state
        resp_success = llm.create_and_ask_prompt('successfull.txt', 'success?', cmd=cmd, resp=resp, facts=state)
        state = "\n".join(map(lambda x: "- " + x, resp_success["facts"]))
        console.print(Panel(state, title="my new fact list"))

        # update our command history
        cmd_history.append(diff, "cmd", cmd, resp, resp_success["success"], resp_success["reason"])

        # this asks for additional vulnerabilities identifiable in the last command output
        # next_vulns = create_and_ask_prompt('query_vulnerabilitites.txt', 'vulns', user=initial_user, next_cmd=cmd, resp=resp)
        # console.print(Panel(str(next_vulns), title="Next Vulns"))

    elif next_cmd["type"] == "ssh":
        ip = os.getenv('TARGET_IP')
        user = next_cmd["username"]
        password = next_cmd["password"]
        
        # TODO: this is currently highly broken
        test = SSHHostConn(ip, user, password)
        print(str(test.test()))
        if result == "root":
            cmd_history.append(diff, "ssh", "tried ssh with username " + next_cmd["username"] + " and password " + next_cmd["password"], True, "Login was successful")
        else:
            cmd_history.append(diff, "ssh", "tried ssh with username " + next_cmd["username"] + " and password " + next_cmd["password"], False, "Login was not successful")

    # aks chatgpt to explain what it expects about the tested
    # system. Understanding this might help human learning
    # system_explanation = create_and_ask_prompt('explain_system.txt', 'explain-system', sysinfo=sysinfo, cmd=next_cmd, cmd_output=resp)

    console.print(cmd_history.create_history_table())
