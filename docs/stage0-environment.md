# Stage 0: the environment, as it was built

Built 2026-11-21. Everything this project installs lives inside one WSL2 distribution, so undoing it is one command.

## Why WSL2 with Docker Engine, not Docker Desktop

- The laptop already had WSL 2.3.24 with virtualization on and no distribution. Importing a distribution needs no
  administrator rights and no reboot.
- The tools then run on Linux, the same as a GitHub Actions runner, so the commands of stage 3b are the commands used
  locally.
- The distribution's disk is a single file on a drive with space, not on the system drive.

## What was run

On Windows (PowerShell), with the official Ubuntu 24.04 WSL image downloaded from
`cloud-images.ubuntu.com/wsl/releases/24.04/current/` and its SHA-256 compared with the published `SHA256SUMS`:

```powershell
wsl --import Ubuntu-24.04 <folder on a data drive> ubuntu-noble-wsl-amd64-24.04lts.rootfs.tar.gz --version 2
```

Inside the distribution, as root:

```bash
printf '[boot]\nsystemd=true\n' > /etc/wsl.conf      # then, on Windows: wsl --terminate Ubuntu-24.04
bash scripts/stage0_install.sh                        # Docker Engine, kubectl, kind, helm, terraform, each hash-checked
```

## The one thing that failed: kind on cgroup v1

`kind create cluster` stopped at `kubeadm init`. `docker info` showed `Cgroup Version: 1`: the WSL kernel 5.15 mounts
cgroup v1 by default, kind printed "cgroup v1 is deprecated in Kubernetes", and the Kubernetes 1.37 node did not start.
The fix is one line in `.wslconfig` in the Windows user folder, then `wsl --shutdown`:

```ini
[wsl2]
kernelCommandLine = cgroup_no_v1=all
```

After that `stat -fc %T /sys/fs/cgroup` prints `cgroup2fs`, Docker reports `Cgroup Driver: systemd`,
`Cgroup Version: 2`, and the cluster starts.

## Versions

| tool | version |
|---|---|
| Ubuntu | 24.04 LTS, kernel 5.15.153.1-microsoft-standard-WSL2 |
| Docker Engine | 29.10.0 (Compose v5.8.0) |
| kubectl | v1.37.2 |
| kind | v0.33.0 (node image Kubernetes v1.37.0) |
| Helm | v4.3.1 |
| Terraform | v1.17.2 |

## Checks that the environment works

- `docker run --rm hello-world` printed "Hello from Docker!".
- A kind cluster ran a 3-replica Deployment through a good image update, an update with a typo in the tag (the three
  old Pods kept running, one new Pod sat in `ErrImagePull`), and `kubectl rollout undo`.
- A Pod asking for `nvidia.com/gpu: 1` stayed `Pending` with "Insufficient nvidia.com/gpu": this machine has no GPU.
- A Helm release went install, upgrade (2 replicas), rollback: `helm history` showed revisions 1, 2 and 3
  ("Rollback to 1").

## Local CPU model server

The design gave vLLM's CPU image a 30-minute trial with llama.cpp's server as the fallback. The fallback is what the
local stack uses.

- **vLLM CPU image** (`vllm/vllm-openai-cpu:latest-x86_64`, vLLM 0.34.0, 7.69 GB): did not become a server here.
  The first start stopped with "Available memory on node 0 (14.14/19.4 GiB) on kv cache allocation is less than
  requested memory for kv (15.61/17.84 GiB)". With `VLLM_CPU_KVCACHE_SPACE=4` it logged "Explicitly set (4.0/19.4) GiB
  for KV cache" and then spent 15 minutes in start-up at one busy core without opening port 8000; nobody waited longer.
  The log also showed "Failed to create oneDNN linear, fallback to torch linear" on this AVX2-only CPU.
- **llama.cpp server** (`ghcr.io/ggml-org/llama.cpp:server`, 1.16 GB) with the official
  `Qwen/Qwen2.5-0.5B-Instruct-GGUF` file `qwen2.5-0.5b-instruct-q4_k_m.gguf`: `/health` answered 200 about 15 seconds
  after `docker run`, one request to `/v1/chat/completions` returned in 0.63 s (35 prompt tokens, 10 completion
  tokens), the container held 409 MiB, and `--metrics` exposes Prometheus metrics such as
  `llamacpp:tokens_predicted_total`.

```bash
docker run -d --name llamacpp -p 8001:8080 ghcr.io/ggml-org/llama.cpp:server \
  --hf-repo Qwen/Qwen2.5-0.5B-Instruct-GGUF --hf-file qwen2.5-0.5b-instruct-q4_k_m.gguf \
  --host 0.0.0.0 --port 8080 --ctx-size 4096 --metrics
curl -s localhost:8001/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"qwen","messages":[{"role":"user","content":"Say hello in five words."}],"max_tokens":32}'
```

vLLM stays the engine of stage 1, on a GPU. These two numbers are one request on a laptop CPU and are not a benchmark.

## Disk

| | before | after |
|---|---|---|
| system drive, free | 26.49 GB | 26.24 GB |
| data drive, free | 207.05 GB | 190.56 GB |

The distribution's disk file grew to about 16 GB (the 7.69 GB vLLM image was pulled and removed; the file does not
shrink by itself). During the vLLM trial the system drive dropped to 24.07 GB free: the 19 GB default VM pushed
Windows into its page file, and WSL kept a swap file in the user's temp folder. Two more lines in `.wslconfig` stop
both:

```ini
memory=12GB
swapFile=<a path on the data drive>
```

## Undo

```powershell
wsl --unregister Ubuntu-24.04      # removes the distribution with Docker, the images and every tool in it
# then delete .wslconfig from the Windows user folder and run: wsl --shutdown
```
