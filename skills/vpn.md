# Skill: VPN Connectivity Issues

## Triggers
vpn, virtual private network, can't connect, disconnecting, drops, tunnel

## Diagnosis Steps
1. Ask what VPN client they use (Cisco AnyConnect, GlobalProtect, OpenVPN, other)
2. Ask what error message they see if any
3. Ask if it ever worked or is this first time

## Fixes by Symptom

### Won't connect at all
- Check internet is working first (can they browse a website?)
- Restart the VPN client completely
- Try connecting on a different network (hotspot test)
- Check VPN server status with IT

### Keeps disconnecting
- Check for Windows power settings putting network adapter to sleep
  - Device Manager > Network Adapters > right-click > Properties > Power Management > uncheck "Allow computer to turn off this device"
- Check for MTU issues: run `ping -f -l 1400 8.8.8.8` — if it fails, MTU is the issue
- Update VPN client to latest version

### Connected but can't access resources
- DNS may not be routing through VPN — run `nslookup internal-resource` and check which DNS server responds
- Split tunnel may be misconfigured — escalate to IT

## Escalation Triggers
- VPN certificate errors
- Account locked out of VPN
- All users affected (not just one person)

## Ticket Template
VPN issue — [client name] — [symptom] — [resolution or escalation reason]
