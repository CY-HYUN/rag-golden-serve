# Stages 3a and 3c: a local cluster from Terraform, a release rolled forward and back with Helm

Run 2026-11-21 on the laptop of stage 0 (WSL2 Ubuntu 24.04, Docker Engine 29.10, kind 0.33.0, Helm 4.3.1, Terraform
1.17.2). The command outputs are in [`bench/results/2026-11-21_deploy/`](../bench/results/2026-11-21_deploy/).

## Who owns what

| | owner | why |
|---|---|---|
| the kind cluster | Terraform, root `deploy/terraform/cluster` | |
| the namespace `rag` | Terraform, root `deploy/terraform/namespace` | a second root, applied after the first: the Kubernetes provider must not be configured from a cluster created in the same apply (provider docs, "Stacking with managed Kubernetes cluster resources") |
| the release (service and model server) | Helm, chart `deploy/helm/rag-golden-serve` | a `helm rollback` then never disagrees with Terraform state |

## Result

| step | command | outcome | time |
|---|---|---|---|
| cluster and namespace | `bash scripts/deploy_local.sh cluster` | `Apply complete! Resources: 1 added` twice; node `Ready`, Kubernetes v1.37.0 | cluster 1 min 30 s, namespace 2 s |
| first release, image `7346611` | `helm upgrade --install ... --wait` | revision 1 `deployed`; `/healthz` reports version `7346611` | 2 min 41 s, most of it the node pulling the model server image and the pod downloading the model file |
| one question through the cluster | `bash scripts/deploy_local.sh ask` | an answer from the model server running in the cluster, with five sources | 29 s |
| new version, image `d7b5925` | `bash scripts/deploy_local.sh release d7b5925` | revision 2 `deployed`; `/healthz` reports version `d7b5925` | 35 s for build, load and upgrade together |
| rollback | `helm rollback rag 1 --wait` | revision 3, "Rollback to 1"; `/healthz` reports version `7346611` again | 10 s |
| teardown | `bash scripts/deploy_local.sh destroy` | `Destroy complete! Resources: 1 destroyed` twice; `kind get clusters` empty | namespace 13 s, cluster 4 s |

```
REVISION  STATUS      DESCRIPTION
1         superseded  image 7346611
2         superseded  image d7b5925
3         deployed    Rollback to 1
```

The image is 373 MB (`docker images`), 92.7 MB as stored on the node, and holds no torch.

## How a version is told apart

The image is tagged with the commit it was built from, the build writes that commit into the image, and `/healthz`
returns it. The rollout and the rollback are therefore read from outside the cluster, as the version the service
reports, not from Helm's own status line.

The two commits used here differ in documentation and tests only: the service code inside the two images is the
same, and the only thing that changes is the version each one reports. The first image was built from
`git archive 7346611` plus the pinned submodule files, the second from the working tree at `d7b5925`.

## What the first run needed

- `docker build --provenance=false`. Docker 29 stores images in containerd and adds an attestation manifest by
  default; kind's documented failure with that store ("content digest not found") did not occur with the attestation
  switched off. Without the flag it was not tried.
- A start-up budget for the model server (`model.startupSeconds`, 600 by default): its image is pulled inside the
  node and the model file is downloaded when the pod starts.

## Limits

- One replica of each Deployment, on a one-node cluster. Whether requests fail while a rollout is in progress was
  not measured.
- The model server keeps no volume: every new model pod downloads the model file again.
- The resource requests and limits in `values.yaml` were enough for one question; they were not load-tested.
- `terraform destroy` on the cluster root prints the cluster's client key and kubeconfig in its plan. The recorded
  destroy output keeps the summary lines only, and the kubeconfig file and the state files are ignored by git.
- The Kubernetes provider needs the kubeconfig the first root writes, so the two roots cannot be applied in one
  `terraform apply`.

## Reproduce

```
bash scripts/deploy_local.sh cluster
bash scripts/deploy_local.sh release $(git rev-parse --short HEAD)
bash scripts/deploy_local.sh ask
bash scripts/deploy_local.sh destroy
```
