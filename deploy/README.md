# Distributed benchmark deployment
Execute a cluster-based benchmarking suite.

## Purpose
End-to-end driver for running the Josh-vs-Mesa benchmark across an AWS EC2 fleet using only the AWS CLI and `ssh`. It launches a fleet, assigns **one config per host** round-robin (e.g. 40 hosts or 10 machines per config, so configs never compete for cores), runs each at a chosen replicate count, pulls the per-host CSVs back, and tears the fleet down.

## Files

- `fleet.sh` — the orchestrator (see its header for every env knob).
- `fleet.txt` — written by `up`: the `instance-id  public-ip` of each host.
- `results/` — populated by `collect`/`merge` with the per-host CSVs and the
  merged `all_results.csv`.

## Prerequisites

Credentials come from your environment / `~/.aws` (run `aws configure` first). **Never hard-code keys** as this repo is public. You also need an EC2 key pair and its local `.pem` file (`KEY_NAME` / `PEM`), and a public `REPO_URL` for the hosts to clone.

## Usage

```sh
export REGION=us-east-2
export REPO_URL=https://github.com/SchmidtDSE/josh-wall-clock.git
./fleet.sh up        # launch + tag instances, write deploy/fleet.txt
./fleet.sh run       # clone + setup + launch one config per host
./fleet.sh status    # poll until every host reports DONE
./fleet.sh collect   # scp results_*.csv -> deploy/results/
./fleet.sh merge     # concat into deploy/results/all_results.csv
./fleet.sh down      # terminate everything tagged (STOPS BILLING)
```

Fleet shape is configurable via env: `REGION`, `INSTANCE_TYPE`, `COUNT`,
`VOLUME_GB`, `KEY_NAME`, `PEM`, `SSH_USER`, `REPLICATES`, `TAG`, `SG_NAME`, and
`CONFIGS_OVERRIDE` (space-separated config list for a dry run). Defaults are 40 ×
`m7i.2xlarge` (512 GB gp3) in `us-east-1` at 100 replicates.

> **Always run `down` when finished** — running instances bill until terminated.
> The security group is left in place; delete it manually if desired.
