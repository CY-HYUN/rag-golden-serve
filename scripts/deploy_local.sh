#!/usr/bin/env bash
# Stage 3 on one machine: Terraform owns the kind cluster and the namespace, Helm owns the release.
#
#   bash scripts/deploy_local.sh cluster            # terraform apply: cluster, then namespace
#   bash scripts/deploy_local.sh release <tag>      # build the image as <tag>, load it, helm upgrade --install
#   bash scripts/deploy_local.sh ask                # one /ask through the cluster; prints the deployed version
#   bash scripts/deploy_local.sh destroy            # terraform destroy: namespace, then cluster
#
# <tag> is the commit the image is built from: $(git rev-parse --short HEAD), with nothing uncommitted.
set -euo pipefail
cd "$(dirname "$0")/.."
TF=deploy/terraform
export KUBECONFIG="$PWD/$TF/cluster/kubeconfig"

# the namespace root reads its two variables from the environment
namespace_env() {
  export TF_VAR_kubeconfig_path="$KUBECONFIG"
  TF_VAR_context_name="$(terraform -chdir=$TF/cluster output -raw context_name)"
  export TF_VAR_context_name
}

case "${1:-}" in
  cluster)
    terraform -chdir=$TF/cluster init -input=false -no-color >/dev/null
    terraform -chdir=$TF/cluster apply -input=false -no-color -auto-approve
    terraform -chdir=$TF/namespace init -input=false -no-color >/dev/null
    namespace_env
    terraform -chdir=$TF/namespace apply -input=false -no-color -auto-approve
    kubectl get nodes
    kubectl get namespace rag
    ;;
  release)
    tag="${2:?usage: deploy_local.sh release <tag>}"
    # one manifest, no attestation: kind cannot load an image index from Docker's containerd image store
    docker build --provenance=false --build-arg "GIT_SHA=$tag" -t "rag-golden-serve:$tag" .
    kind load docker-image "rag-golden-serve:$tag" --name rag
    helm upgrade --install rag deploy/helm/rag-golden-serve -n rag \
      --set-string "image.tag=$tag" --description "image $tag" --wait --timeout 15m
    helm history rag -n rag
    ;;
  ask)
    kubectl -n rag port-forward svc/rag 8080:80 >/dev/null 2>&1 &
    forward=$!
    trap 'kill $forward' EXIT
    for _ in $(seq 1 30); do curl -fsS localhost:8080/healthz && break; sleep 1; done
    echo
    curl -fsS localhost:8080/ask -H 'Content-Type: application/json' \
      -d '{"question":"Which optimizer was used to train the model?"}'
    echo
    ;;
  destroy)
    namespace_env
    terraform -chdir=$TF/namespace destroy -input=false -no-color -auto-approve
    # this plan prints the cluster's client key and kubeconfig: keep only its last line when recording a run
    terraform -chdir=$TF/cluster destroy -input=false -no-color -auto-approve
    ;;
  *)
    sed -n '2,10p' "$0"
    exit 2
    ;;
esac
