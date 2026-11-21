# Step 1 of 2: the local Kubernetes cluster (kind). The namespace is a separate root (../namespace) because the
# Kubernetes provider must not be configured from a cluster created in the same apply (provider docs, "Stacking
# with managed Kubernetes cluster resources").
terraform {
  required_version = "~> 1.17"

  required_providers {
    kind = {
      source  = "tehcyx/kind"
      version = "~> 0.13.0"
    }
  }
}

provider "kind" {}

resource "kind_cluster" "this" {
  name            = "rag"
  node_image      = "kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5"
  wait_for_ready  = true
  kubeconfig_path = abspath("${path.module}/kubeconfig") # holds the client key: ignored by git
}

output "kubeconfig_path" {
  value = kind_cluster.this.kubeconfig_path
}

output "context_name" {
  value = kind_cluster.this.context_name
}
