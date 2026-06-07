# Pre-flight Check

Run before any cluster operations. All hard checks must pass before Stage 2.

## Checks

### 1. Tailscale VPN

```bash
ping -c1 -W2 100.109.84.43
```

The cluster network (`172.30.160.0/24`) is only reachable via the Tailscale subnet
router at `100.109.84.43`. If unreachable:

> "Tailscale VPN not reachable. Connect Tailscale and retry."

Abort. Do not proceed.

### 2. SSH Access (key-auth probe)

```bash
ssh -o BatchMode=yes -o ConnectTimeout=5 dn@172.30.160.228 echo OK
```

Tests `amd-mi355x-des2-1` (always key-auth). If this fails:

> "SSH to des2-1 failed. Check that your key is deployed and Tailscale is routing."

Abort. Do not proceed.

### 3. tmux Installed

```bash
tmux -V
```

tmux is required to hold the salloc allocation across disconnects. If not found:

> "tmux not found. Install tmux: `apt-get install tmux` or `brew install tmux`."

Abort. Do not proceed.

### 4. SSHPASS for Password Nodes

```bash
[[ -n "${SSHPASS}" ]]
```

If `SSHPASS` is not set, password nodes cannot be surveyed. This is a soft failure:

> "SSHPASS env var not set. Password nodes will be marked UNREACHABLE in the map.
> Set it with: export SSHPASS='<password>'"

Continue — do not abort. Mark password nodes as `UNREACHABLE` in the allocation map
and note the gap in the report.

## Load Node Map

Read the cluster node map from:
```
~/.claude/projects/-home-dn-research-KV-Compacting/memory/cluster_node_map.md
```

Parse the node table. For each node extract: `hostname`, `ip`, `auth_type`,
`sshpass_required`, `partition`, `last_known_status`.

If the file is missing or unparseable, abort:
> "cluster_node_map.md not found or unreadable. Cannot survey cluster."

## Pre-flight Output

```text
PREFLIGHT: PASS | FAIL
tailscale: ok | unreachable
ssh_probe: ok | failed
tmux: ok | missing
sshpass: set | unset (password nodes will be skipped)
nodes_loaded: <N>
```
