# Step 2 of 2: the namespace the Helm release goes into. Terraform stops here: the release and its rollback
# belong to Helm, so a `helm rollback` never disagrees with Terraform state.
terraform {
  required_version = "~> 1.17"

  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 3.5"
    }
  }
}

variable "kubeconfig_path" {
  type        = string
  description = "terraform -chdir=../cluster output -raw kubeconfig_path"
}

variable "context_name" {
  type        = string
  description = "terraform -chdir=../cluster output -raw context_name"
}

provider "kubernetes" {
  config_path    = var.kubeconfig_path
  config_context = var.context_name
}

resource "kubernetes_namespace_v1" "rag" {
  metadata {
    name = "rag"
  }
}

output "namespace" {
  value = kubernetes_namespace_v1.rag.metadata[0].name
}
