#!/usr/bin/env bash
# Host-level egress firewall for the sandbox Docker network.
#
# Run ONCE on the Vultr VM after `docker compose up` (and after reboots). It
# blocks every container on the sandbox network from reaching private ranges,
# the cloud metadata endpoint and the host, while leaving public internet
# egress open (the sandbox must reach the target URL). Traffic WITHIN the
# sandbox subnet stays allowed so the orchestrator can drive the sandbox.
#
# Defence-in-depth on top of the SSRF checks inside the sandbox runner. Note:
# no secret ever lives in the sandbox, so the remaining api-over-sandbox-net
# path exposes nothing worth stealing.
#
# Usage: sudo ./scripts/sandbox-firewall.sh [sandbox-network-name]
set -euo pipefail

NET_NAME="${1:-phishprobe-sandbox-net}"

SUBNET="$(docker network inspect "$NET_NAME" -f '{{(index .IPAM.Config 0).Subnet}}')"
GATEWAY="$(docker network inspect "$NET_NAME" -f '{{(index .IPAM.Config 0).Gateway}}')"
NET_ID="$(docker network inspect "$NET_NAME" -f '{{.Id}}')"
BRIDGE="br-${NET_ID:0:12}"

echo "Sandbox network: $NET_NAME  subnet=$SUBNET  gateway=$GATEWAY  bridge=$BRIDGE"

ins() {  # insert at top only if not already present
  iptables -C DOCKER-USER "$@" 2>/dev/null || iptables -I DOCKER-USER "$@"
}

# Insert DROP rules first; the intra-subnet RETURN is inserted LAST so it ends
# up ABOVE the DROPs (iptables -I prepends) and is matched first.
ins -i "$BRIDGE" -d "$GATEWAY" -j DROP          # host via bridge gateway
ins -s "$SUBNET" -d 192.168.0.0/16 -j DROP      # private
ins -s "$SUBNET" -d 172.16.0.0/12 -j DROP       # private (other docker nets)
ins -s "$SUBNET" -d 10.0.0.0/8 -j DROP          # private
ins -s "$SUBNET" -d 169.254.0.0/16 -j DROP      # link-local + cloud metadata

# Allow traffic that stays inside the sandbox subnet (orchestrator <-> sandbox).
ins -s "$SUBNET" -d "$SUBNET" -j RETURN

echo "Applied. DOCKER-USER chain:"
iptables -L DOCKER-USER -n --line-numbers | sed 's/^/  /'
