#!/usr/bin/env bash
#
# End-to-end fleet driver for the Josh-vs-Mesa benchmark using only the AWS CLI
# and ssh. Launches N EC2 instances, bootstraps each, runs all four configs
# once at REPLICATES, pulls the per-host CSVs back, and tears the fleet down.
#
#   ./deploy/fleet.sh up        # launch + tag instances, write deploy/fleet.txt
#   ./deploy/fleet.sh run       # clone+setup+launch benchmark on every host
#   ./deploy/fleet.sh status    # poll progress
#   ./deploy/fleet.sh collect   # scp results_*.csv -> deploy/results/
#   ./deploy/fleet.sh merge     # concat into deploy/results/all_results.csv
#   ./deploy/fleet.sh down      # terminate everything tagged (STOPS BILLING)
#
# Credentials come from your environment / ~/.aws (run `aws configure` first).
# NEVER hard-code keys here -- this repo is public.
#
# Config via env (defaults shown):
set -euo pipefail

REGION="${REGION:-us-east-1}"
INSTANCE_TYPE="${INSTANCE_TYPE:-m7i.2xlarge}"
COUNT="${COUNT:-10}"
VOLUME_GB="${VOLUME_GB:-512}"
KEY_NAME="${KEY_NAME:-josh-wallclock}"          # EC2 key pair NAME
PEM="${PEM:-$HOME/josh-wallclock.pem}"          # local private key file
SSH_USER="${SSH_USER:-ubuntu}"
REPO_URL="${REPO_URL:-}"                         # public git URL (required for run)
REPLICATES="${REPLICATES:-100}"
TAG="${TAG:-josh-bench}"
SG_NAME="${SG_NAME:-josh-bench-sg}"

HERE="$(cd "$(dirname "$0")" && pwd)"
FLEET="$HERE/fleet.txt"
RESULTS="$HERE/results"
SSH_OPTS=(-o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 -i "$PEM")

aws_() { aws --region "$REGION" "$@"; }

cmd_up() {
  echo "==> Resolving latest Ubuntu 24.04 AMI in $REGION"
  local ami vpc sg myip
  ami=$(aws_ ssm get-parameters \
    --names /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
    --query 'Parameters[0].Value' --output text)
  echo "    AMI=$ami"

  vpc=$(aws_ ec2 describe-vpcs --filters Name=isDefault,Values=true \
    --query 'Vpcs[0].VpcId' --output text)
  echo "==> Default VPC=$vpc"

  sg=$(aws_ ec2 describe-security-groups \
    --filters Name=group-name,Values="$SG_NAME" Name=vpc-id,Values="$vpc" \
    --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo None)
  if [ "$sg" = "None" ] || [ -z "$sg" ]; then
    sg=$(aws_ ec2 create-security-group --group-name "$SG_NAME" \
      --description "josh benchmark ssh" --vpc-id "$vpc" \
      --query GroupId --output text)
    echo "==> Created SG $sg"
  fi
  myip=$(curl -fsS https://checkip.amazonaws.com)
  aws_ ec2 authorize-security-group-ingress --group-id "$sg" \
    --protocol tcp --port 22 --cidr "${myip}/32" 2>/dev/null \
    && echo "==> Allowed SSH from ${myip}/32" || echo "    (SSH rule already present)"

  echo "==> Launching $COUNT x $INSTANCE_TYPE (${VOLUME_GB}GB gp3)"
  local ids
  ids=$(aws_ ec2 run-instances \
    --image-id "$ami" --instance-type "$INSTANCE_TYPE" --count "$COUNT" \
    --key-name "$KEY_NAME" --security-group-ids "$sg" \
    --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=$VOLUME_GB,VolumeType=gp3}" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$TAG}]" \
    --query 'Instances[].InstanceId' --output text)
  echo "    instances: $ids"

  echo "==> Waiting for running state..."
  aws_ ec2 wait instance-running --instance-ids $ids

  aws_ ec2 describe-instances \
    --filters "Name=tag:Name,Values=$TAG" Name=instance-state-name,Values=running \
    --query 'Reservations[].Instances[].[InstanceId,PublicIpAddress]' --output text > "$FLEET"
  echo "==> Wrote $FLEET:"
  cat "$FLEET"
}

_each_host() {  # _each_host <bash-function-name>
  local fn="$1"
  [ -f "$FLEET" ] || { echo "No $FLEET -- run 'up' first." >&2; exit 1; }
  while read -r id ip; do
    [ -n "$ip" ] && "$fn" "$id" "$ip" &
  done < "$FLEET"
  wait
}

_run_one() {
  local id="$1" ip="$2"
  [ -n "$REPO_URL" ] || { echo "Set REPO_URL." >&2; exit 1; }
  echo "[$ip] bootstrapping + launching"
  ssh "${SSH_OPTS[@]}" "$SSH_USER@$ip" bash -s <<EOF
set -e
if [ -d josh-wall-profile/.git ]; then cd josh-wall-profile && git pull --ff-only;
else git clone $REPO_URL josh-wall-profile; fi
cd ~/josh-wall-profile
export PATH=\$HOME/.local/bin:\$PATH
bash setup.sh
rm -f run_all.done
setsid bash -c 'bash run_all.sh $REPLICATES > run_all.log 2>&1; touch run_all.done' >/dev/null 2>&1 &
echo "[$ip] launched"
EOF
}

_status_one() {
  local id="$1" ip="$2"
  local state tail
  state=$(ssh "${SSH_OPTS[@]}" "$SSH_USER@$ip" \
    'test -f ~/josh-wall-profile/run_all.done && echo DONE || echo RUNNING' 2>/dev/null || echo UNREACHABLE)
  tail=$(ssh "${SSH_OPTS[@]}" "$SSH_USER@$ip" \
    'tail -n 1 ~/josh-wall-profile/run_all.log 2>/dev/null' 2>/dev/null || true)
  printf '[%s] %s  %s\n' "$ip" "$state" "$tail"
}

_collect_one() {
  local id="$1" ip="$2"
  mkdir -p "$RESULTS"
  scp "${SSH_OPTS[@]}" "$SSH_USER@$ip:josh-wall-profile/results_*.csv" "$RESULTS/" 2>/dev/null \
    && echo "[$ip] collected" || echo "[$ip] no results yet"
}

cmd_run()     { _each_host _run_one; }
cmd_status()  { _each_host _status_one; }
cmd_collect() { _each_host _collect_one; }

cmd_merge() {
  local files out
  files=$(ls "$RESULTS"/results_*.csv 2>/dev/null || true)
  [ -n "$files" ] || { echo "No results to merge -- run 'collect'." >&2; exit 1; }
  out="$RESULTS/all_results.csv"
  local first=1
  : > "$out"
  for f in $files; do
    if [ "$first" = 1 ]; then cat "$f" >> "$out"; first=0; else tail -n +2 "$f" >> "$out"; fi
  done
  echo "Merged into $out"; cat "$out"
}

cmd_down() {
  local ids
  ids=$(aws_ ec2 describe-instances \
    --filters "Name=tag:Name,Values=$TAG" \
      Name=instance-state-name,Values=pending,running,stopping,stopped \
    --query 'Reservations[].Instances[].InstanceId' --output text)
  [ -n "$ids" ] || { echo "Nothing tagged $TAG to terminate."; return; }
  echo "==> Terminating: $ids"
  aws_ ec2 terminate-instances --instance-ids $ids >/dev/null
  aws_ ec2 wait instance-terminated --instance-ids $ids
  echo "==> Terminated. (Security group $SG_NAME left in place; delete manually if desired.)"
}

case "${1:-}" in
  up) cmd_up ;;
  run) cmd_run ;;
  status) cmd_status ;;
  collect) cmd_collect ;;
  merge) cmd_merge ;;
  down) cmd_down ;;
  *) echo "Usage: $0 {up|run|status|collect|merge|down}" >&2; exit 1 ;;
esac
