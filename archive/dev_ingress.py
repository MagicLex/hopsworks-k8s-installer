#!/usr/bin/env python3

import subprocess
import time
import sys
import os
import uuid
from datetime import datetime
import yaml
import requests
import json
import shutil
import argparse

# Constants
SERVER_URL = "https://magiclex--hopsworks-installation-hopsworks-installation.modal.run/"
STARTUP_LICENSE_URL = "https://www.hopsworks.ai/startup-license"
EVALUATION_LICENSE_URL = "https://www.hopsworks.ai/evaluation-license"
REQUIRED_NODES = 6

def print_colored(message, color):
    colors = {
        "red": "\033[91m", "green": "\033[92m", "yellow": "\033[93m",
        "blue": "\033[94m", "magenta": "\033[95m", "cyan": "\033[96m",
        "white": "\033[97m", "reset": "\033[0m"
    }
    print(f"{colors.get(color, '')}{message}{colors['reset']}")

def run_command(command, verbose=True, timeout=300):
    if verbose:
        print_colored(f"Running command: {command}", "cyan")
    try:
        result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        if verbose:
            if result.stdout:
                print(result.stdout)
            if result.stderr:
                print_colored(result.stderr, "yellow")
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        print_colored(f"Command timed out after {timeout} seconds: {command}", "red")
        return False, "", "Timeout"

def get_user_input(prompt, options=None):
    while True:
        response = input(prompt + " ").strip()
        if options is None or response.lower() in [option.lower() for option in options]:
            return response
        else:
            print_colored(f"Invalid input. Expected one of: {', '.join(options)}", "yellow")

def get_license_agreement():
    print_colored("\nChoose a license agreement:", "blue")
    print("1. Startup Software License")
    print("2. Evaluation Agreement")
    
    choice = get_user_input("Enter 1 or 2:", ["1", "2"])
    license_type = "Startup" if choice == "1" else "Evaluation"
    license_url = STARTUP_LICENSE_URL if choice == "1" else EVALUATION_LICENSE_URL
    
    print_colored(f"\nReview the {license_type} License Agreement at:", "blue")
    print_colored(license_url, "cyan")
    
    agreement = get_user_input("\nDo you agree to the terms and conditions? (yes/no):", ["yes", "no"]).lower() == "yes"
    if not agreement:
        print_colored("You must agree to the terms and conditions to proceed.", "red")
        sys.exit(1)
    return license_type, agreement

def get_user_info():
    print_colored("\nProvide the following information:", "blue")
    name = input("Your name: ")
    email = input("Your email address: ")
    company = input("Your company name: ")
    return name, email, company

def send_user_data(name, email, company, license_type, agreed_to_license):
    print_colored("\nSending user data...", "blue")
    installation_id = str(uuid.uuid4())
    data = {
        "name": name, "email": email, "company": company,
        "license_type": license_type, "agreed_to_license": agreed_to_license,
        "installation_id": installation_id,
        "action": "install_hopsworks",
        "installation_date": datetime.now().isoformat()
    }
    try:
        response = requests.post(SERVER_URL, json=data, timeout=30)
        response.raise_for_status()
        print_colored("User data sent successfully.", "green")
        return True, installation_id
    except requests.RequestException as e:
        print_colored(f"Failed to send user data: {str(e)}", "red")
        return False, installation_id

def check_node_count():
    print_colored("\nChecking Kubernetes nodes...", "blue")
    cmd = "kubectl get nodes -o json"
    success, output, error = run_command(cmd, verbose=False)
    if not success:
        print_colored("Failed to get Kubernetes nodes. Ensure your kubeconfig is correct and Kubernetes cluster is accessible.", "red")
        sys.exit(1)
    try:
        nodes = json.loads(output)['items']
        node_count = len(nodes)
        print_colored(f"Number of nodes in the cluster: {node_count}", "green")
        if node_count < REQUIRED_NODES:
            print_colored(f"At least {REQUIRED_NODES} nodes are required. Please add more nodes to your cluster.", "red")
            sys.exit(1)
    except json.JSONDecodeError:
        print_colored("Failed to parse nodes JSON output.", "red")
        sys.exit(1)

def setup_kubeconfig():
    print_colored("\nSetting up kubeconfig...", "blue")
    
    kubeconfig_path = input("Enter the path to your kubeconfig file: ").strip()
    kubeconfig_path = os.path.expanduser(kubeconfig_path)

    if not os.path.exists(kubeconfig_path):
        print_colored(f"The file {kubeconfig_path} does not exist. Check the path and try again.", "red")
        return None

    default_kubeconfig = os.path.expanduser("~/.kube/config")
    os.makedirs(os.path.dirname(default_kubeconfig), exist_ok=True)
    try:
        shutil.copy(kubeconfig_path, default_kubeconfig)
        print_colored(f"Copied kubeconfig to {default_kubeconfig}", "green")
    except Exception as e:
        print_colored(f"Failed to copy kubeconfig: {str(e)}", "red")
        return None

    try:
        os.chmod(default_kubeconfig, 0o600)
        print_colored("Updated kubeconfig file permissions to 600.", "green")
    except Exception as e:
        print_colored(f"Failed to update kubeconfig file permissions: {str(e)}", "yellow")
        print_colored(f"Manually run: chmod 600 {default_kubeconfig}", "yellow")

    success, output, error = run_command("kubectl config current-context", verbose=False)
    if not success:
        print_colored("Failed to get current context. Check if the kubeconfig is valid.", "red")
        print_colored(f"Error output: {error}", "red")
        return None
    
    print_colored(f"Current context: {output.strip()}", "green")
    return default_kubeconfig

def modify_dev_yaml():
    dev_yaml_path = './hopsworks/values.dev.yaml'
    
    if not os.path.exists(dev_yaml_path):
        print_colored(f"Dev YAML file not found at {dev_yaml_path}", "red")
        return False

    try:
        with open(dev_yaml_path, 'r') as file:
            data = yaml.safe_load(file)

        # Modify values for better performance
        data['hopsworks']['debug'] = False
        # Add more modifications as needed

        with open(dev_yaml_path, 'w') as file:
            yaml.dump(data, file)

        print_colored("Updated dev YAML file for better performance", "green")
        return True
    except Exception as e:
        print_colored(f"Failed to modify dev YAML: {str(e)}", "red")
        return False

def install_hopsworks(namespace):
    print_colored("\nInstalling Hopsworks...", "blue")
    
    if not run_command("helm repo add hopsworks https://nexus.hops.works/repository/hopsworks-helm --force-update")[0]:
        print_colored("Failed to add Hopsworks Helm repo. Check your internet connection and try again.", "red")
        return False

    if not run_command("helm repo update")[0]:
        print_colored("Failed to update Helm repos. Check your internet connection and try again.", "red")
        return False
    
    if os.path.exists('hopsworks'):
        shutil.rmtree('hopsworks', ignore_errors=True)
    
    success, _, error = run_command("helm pull hopsworks/hopsworks --untar --devel")
    if not success:
        print_colored(f"Failed to pull Hopsworks chart. Error: {error}", "red")
        return False
    
    if not modify_dev_yaml():
        print_colored("Failed to modify dev YAML. Continuing with default settings.", "yellow")
    
    helm_command = (
        f"helm install hopsworks-release ./hopsworks "
        f"--namespace={namespace} "
        f"--create-namespace "
        f"--values hopsworks/values.services.yaml "
        f"--values hopsworks/values.yaml "
        f"--values hopsworks/values.dev.yaml "
        f"--timeout 60m "
        f"--wait "
        f"--debug "
        f"--devel"
    )
    
    success, output, error = run_command(helm_command, timeout=3600)
    
    if success:
        print_colored("Hopsworks installation command executed successfully.", "green")
    else:
        print_colored("Hopsworks installation command failed. Check the logs for details.", "red")
        print_colored(f"Error: {error}", "red")
        return False
    
    print_colored("Waiting for Hopsworks pods to be ready...", "yellow")
    return wait_for_pods_ready(namespace)

def wait_for_pods_ready(namespace, timeout=1800):  # 30 minutes timeout
    print_colored(f"Waiting for pods in namespace '{namespace}' to be ready...", "yellow")
    start_time = time.time()
    while time.time() - start_time < timeout:
        cmd = f"kubectl get pods -n {namespace} -o json"
        success, output, _ = run_command(cmd, verbose=False)
        if success:
            try:
                pods = json.loads(output)['items']
                total_pods = len(pods)
                ready_pods = 0
                for pod in pods:
                    pod_phase = pod['status'].get('phase', '')
                    if pod_phase in ['Running', 'Succeeded']:
                        ready_pods += 1
                if total_pods > 0:
                    readiness = (ready_pods / total_pods) * 100
                    print_colored(f"Pods readiness: {readiness:.2f}% ({ready_pods}/{total_pods})", "green")
                    if readiness >= 80:
                        print_colored("Sufficient pods are ready!", "green")
                        return True
                else:
                    print_colored("No pods found. Waiting...", "yellow")
            except json.JSONDecodeError as e:
                print_colored(f"Failed to parse pod status JSON: {str(e)}", "red")
        time.sleep(10)
    print_colored(f"Timed out waiting for pods to be ready in namespace '{namespace}'", "red")
    return False

def get_hopsworks_url(namespace):
    cmd = f"kubectl get ingress -n {namespace} -o json"
    success, output, _ = run_command(cmd, verbose=False)
    if success:
        try:
            ingress_data = json.loads(output)
            items = ingress_data.get('items', [])
            if items:
                ingress = items[0]
                rules = ingress['spec'].get('rules', [])
                if rules:
                    host = rules[0].get('host', '')
                    if host:
                        return f"https://{host}"
        except json.JSONDecodeError:
            print_colored("Failed to parse ingress JSON output.", "red")
    return None

def check_ingress_controller():
    print_colored("\nChecking for an existing ingress controller...", "blue")
    cmd = "kubectl get pods --all-namespaces -l app.kubernetes.io/name=ingress-nginx -o json"
    success, output, _ = run_command(cmd, verbose=False)
    if success:
        try:
            pods = json.loads(output).get('items', [])
            if pods:
                print_colored("Ingress controller is already installed.", "green")
                return True
            else:
                print_colored("No ingress controller found.", "yellow")
                return False
        except json.JSONDecodeError:
            print_colored("Failed to parse pods JSON output.", "red")
            return False
    else:
        print_colored("Failed to check ingress controller. Proceeding to install one.", "yellow")
        return False

def install_ingress_controller():
    print_colored("\nInstalling ingress-nginx controller...", "blue")
    if not run_command("helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx")[0]:
        print_colored("Failed to add ingress-nginx Helm repo.", "red")
        return False
    if not run_command("helm repo update")[0]:
        print_colored("Failed to update Helm repos.", "red")
        return False
    helm_command = (
        "helm install ingress-nginx ingress-nginx/ingress-nginx "
        "--namespace ingress-nginx "
        "--create-namespace "
        "--set controller.service.type=LoadBalancer"
    )
    success, _, error = run_command(helm_command)
    if success:
        print_colored("Ingress controller installed successfully.", "green")
        return True
    else:
        print_colored(f"Failed to install ingress controller: {error}", "red")
        return False

def wait_for_ingress_address(namespace, timeout=600):
    print_colored("\nWaiting for ingress address to be assigned...", "yellow")
    start_time = time.time()
    while time.time() - start_time < timeout:
        # Get the ingress address from the ingress resource
        cmd = f"kubectl get ingress -n {namespace} -o jsonpath='{{.items[0].status.loadBalancer.ingress[0].ip}}'"
        success, ip_output, _ = run_command(cmd, verbose=False)
        cmd = f"kubectl get ingress -n {namespace} -o jsonpath='{{.items[0].status.loadBalancer.ingress[0].hostname}}'"
        success_hostname, hostname_output, _ = run_command(cmd, verbose=False)
        ingress_address = ip_output.strip() or hostname_output.strip()
        if ingress_address:
            print_colored(f"Ingress address found: {ingress_address}", "green")
            return ingress_address
        else:
            # Get the EXTERNAL-IP from ingress-nginx-controller service
            cmd = "kubectl get service ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].ip}'"
            success, svc_ip_output, _ = run_command(cmd, verbose=False)
            cmd = "kubectl get service ingress-nginx-controller -n ingress-nginx -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'"
            success_hostname, svc_hostname_output, _ = run_command(cmd, verbose=False)
            svc_ingress_address = svc_ip_output.strip() or svc_hostname_output.strip()
            if svc_ingress_address:
                print_colored(f"Ingress controller address found: {svc_ingress_address}", "green")
                return svc_ingress_address
        time.sleep(10)
    print_colored("Timed out waiting for ingress address to be assigned.", "red")
    return None

def wait_for_ingress(namespace, ingress_host, timeout=600):
    print_colored("Waiting for ingress to be ready...", "yellow")
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(ingress_host, timeout=10, verify=False)
            if response.status_code < 500:
                print_colored("Ingress is responding!", "green")
                return True
        except requests.RequestException:
            pass
        time.sleep(10)
    print_colored("Timed out waiting for ingress to be ready", "red")
    return False

def update_hosts_file(ingress_address, ingress_host):
    print_colored("\nTo access Hopsworks UI, you may need to update your /etc/hosts file.", "yellow")
    print_colored(f"Add the following entry to your /etc/hosts file:", "cyan")
    print_colored(f"{ingress_address} {ingress_host}", "green")
    update_hosts = get_user_input("Would you like the script to attempt to update your /etc/hosts file? (yes/no):", ["yes", "no"]).lower() == "yes"
    if update_hosts:
        try:
            with open("/etc/hosts", "a") as hosts_file:
                hosts_file.write(f"\n{ingress_address} {ingress_host}\n")
            print_colored("Successfully updated /etc/hosts.", "green")
        except PermissionError:
            print_colored("Permission denied when trying to update /etc/hosts.", "red")
            print_colored("Please run the script as root or manually update /etc/hosts.", "yellow")
    else:
        print_colored("Please manually add the entry to your /etc/hosts file.", "yellow")

def main():
    parser = argparse.ArgumentParser(description="Hopsworks Installation Script")
    parser.add_argument('--ingress-only', action='store_true', help='Jump directly to the ingress setup')
    args = parser.parse_args()

    if not args.ingress_only:
        print_colored("Welcome to the Hopsworks Installation Script!", "blue")

        license_type, agreement = get_license_agreement()
        name, email, company = get_user_info()
        success, installation_id = send_user_data(name, email, company, license_type, agreement)

        if success:
            print_colored(f"Installation ID: {installation_id}", "green")
            print_colored("Keep this ID for your records and support purposes.", "yellow")
        else:
            print_colored("Failed to process user information. Continuing with installation.", "yellow")
            installation_id = "unknown"

        kubeconfig = setup_kubeconfig()
        if not kubeconfig:
            print_colored("Failed to set up a valid kubeconfig. Exiting.", "red")
            sys.exit(1)

        check_node_count()

        namespace = get_user_input("Enter the namespace for Hopsworks installation (default: hopsworks):") or "hopsworks"
        
        if not install_hopsworks(namespace):
            print_colored("Hopsworks installation failed. Please check the logs and try again.", "red")
            sys.exit(1)
    else:
        namespace = get_user_input("Enter the namespace for Hopsworks installation (default: hopsworks):") or "hopsworks"
        installation_id = "unknown"

    # Check and install ingress controller if necessary
    if not check_ingress_controller():
        if not install_ingress_controller():
            print_colored("Failed to install ingress controller. Exiting.", "red")
            sys.exit(1)

    ingress_address = wait_for_ingress_address(namespace)
    if not ingress_address:
        print_colored("Failed to obtain ingress address. Exiting.", "red")
        sys.exit(1)

    hopsworks_url = get_hopsworks_url(namespace)
    if not hopsworks_url:
        print_colored("Unable to determine Hopsworks URL. Please check your ingress configuration.", "yellow")
    else:
        ingress_host = hopsworks_url.replace("https://", "")
        update_hosts_file(ingress_address, ingress_host)

        if not wait_for_ingress(namespace, hopsworks_url):
            print_colored("Warning: Ingress might not be fully set up. Check your cluster's networking.", "yellow")
        else:
            print_colored(f"Hopsworks UI should be accessible at: {hopsworks_url}", "cyan")

    print_colored("\nInstallation completed!", "green")
    print_colored(f"Your installation ID is: {installation_id}", "green")
    print_colored("Note: It may take a few minutes for all services to become fully operational.", "yellow")
    print_colored("If you're having trouble accessing the UI, ensure your ingress and DNS are properly configured.", "yellow")
    print_colored("If you need any assistance, contact our support team and provide your installation ID.", "blue")

if __name__ == "__main__":
    main()
