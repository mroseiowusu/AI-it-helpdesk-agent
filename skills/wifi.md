# Skill: Wi-Fi Connectivity Issues

## Triggers
wifi, wi-fi, wireless, internet, network, no connection, limited connectivity, keeps dropping

## Diagnosis Steps
1. Ask if no internet at all or just slow
2. Ask if other devices on same network work fine
3. Ask if issue is with all websites or specific ones

## Fixes by Symptom

### Can't connect at all
- Forget the network and reconnect: Settings > Network > Wi-Fi > Manage Known Networks
- Reset network stack: run as admin:
  - `netsh winsock reset`
  - `netsh int ip reset`
  - `ipconfig /flushdns`
  - Restart computer
- Update Wi-Fi driver: Device Manager > Network Adapters > right-click > Update driver

### Connected but no internet
- Check IP address: `ipconfig` — if 169.x.x.x it's a DHCP issue
- Release and renew: `ipconfig /release` then `ipconfig /renew`
- Try a different DNS: set DNS to 8.8.8.8 and 8.8.4.4 temporarily

### Keeps dropping
- Check power management on Wi-Fi adapter (same as VPN guide)
- Move closer to access point to rule out signal strength
- Check for interference: other devices, microwaves, neighboring networks

### Slow Wi-Fi
- Run speed test on wired connection — if fast, issue is Wi-Fi not internet
- Check which band they're on (2.4GHz vs 5GHz) — 5GHz is faster but shorter range
- Check for bandwidth hogs: check other devices and streaming

## Escalation Triggers
- All users on same floor/area affected
- Access point hardware failure suspected
- Network infrastructure changes needed

## Ticket Template
Wi-Fi issue — [symptom] — [building/floor] — [resolution or escalation]
