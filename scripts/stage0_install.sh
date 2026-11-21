#!/usr/bin/env bash
# Stage 0: Docker Engine, kubectl, kind, helm and terraform inside the Ubuntu 24.04 WSL2 distribution.
# Run as root inside the distribution:  bash scripts/stage0_install.sh
# Every downloaded binary is checked against the hash its publisher serves; a mismatch stops the script.
set -euo pipefail

KIND_VERSION="v0.33.0"
HELM_VERSION="v4.3.1"
TERRAFORM_VERSION="1.17.2"
export DEBIAN_FRONTEND=noninteractive
work="$(mktemp -d)"
cd "$work"

echo "== apt: Docker's own repository (docs.docker.com/engine/install/ubuntu)"
apt-get update -qq
apt-get install -y -qq ca-certificates curl unzip >/dev/null
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null

echo "== kubectl (kubernetes.io/docs/tasks/tools/install-kubectl-linux)"
K8S_VERSION="$(curl -fsSL https://dl.k8s.io/release/stable.txt)"
curl -fsSLO "https://dl.k8s.io/release/${K8S_VERSION}/bin/linux/amd64/kubectl"
curl -fsSLO "https://dl.k8s.io/release/${K8S_VERSION}/bin/linux/amd64/kubectl.sha256"
echo "$(cat kubectl.sha256)  kubectl" | sha256sum --check --quiet
install -m 0755 kubectl /usr/local/bin/kubectl

echo "== kind ${KIND_VERSION} (kind.sigs.k8s.io)"
curl -fsSLo kind-linux-amd64 "https://github.com/kubernetes-sigs/kind/releases/download/${KIND_VERSION}/kind-linux-amd64"
curl -fsSLo kind.sha256sum "https://github.com/kubernetes-sigs/kind/releases/download/${KIND_VERSION}/kind-linux-amd64.sha256sum"
sha256sum --check --quiet kind.sha256sum
install -m 0755 kind-linux-amd64 /usr/local/bin/kind

echo "== helm ${HELM_VERSION} (get.helm.sh)"
curl -fsSLO "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz"
curl -fsSLO "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz.sha256sum"
sha256sum --check --quiet "helm-${HELM_VERSION}-linux-amd64.tar.gz.sha256sum"
tar -xzf "helm-${HELM_VERSION}-linux-amd64.tar.gz"
install -m 0755 linux-amd64/helm /usr/local/bin/helm

echo "== terraform ${TERRAFORM_VERSION} (releases.hashicorp.com)"
curl -fsSLO "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip"
curl -fsSLO "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_SHA256SUMS"
grep "terraform_${TERRAFORM_VERSION}_linux_amd64.zip" "terraform_${TERRAFORM_VERSION}_SHA256SUMS" | sha256sum --check --quiet
unzip -q -o "terraform_${TERRAFORM_VERSION}_linux_amd64.zip" terraform
install -m 0755 terraform /usr/local/bin/terraform

cd / && rm -rf "$work"
echo "== versions"
docker --version
docker compose version
kubectl version --client | head -1
kind version
helm version --short
terraform version | head -1
