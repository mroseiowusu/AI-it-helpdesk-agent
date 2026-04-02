# Skill: Slow Computer / High CPU or Memory

## Triggers
slow, sluggish, freezing, hanging, spinning, unresponsive, high cpu, ram, memory, takes forever

## Diagnosis Steps
1. Ask how long it has been slow (always slow, or started recently?)
2. Ask if slow all the time or only when doing specific things
3. Check SSH diagnostic data if available — look at top processes and memory

## Fixes by Symptom

### High CPU
- Identify the culprit process from diagnostics (top_processes section)
- Common offenders: antivirus scan, Windows Update, browser with many tabs
- For Windows: `taskkill /IM processname.exe /F` to kill a runaway process
- Check if Windows Update is running: Services > Windows Update > check status

### High Memory
- Check for memory leaks in long-running apps — restart them
- On Windows: increase virtual memory (System > Advanced > Performance Settings > Virtual Memory)
- Clear browser cache and close unused tabs

### Slow at startup
- Disable startup programs: Task Manager > Startup tab > disable non-essential items
- Check disk health: `chkdsk C: /f` (Windows) or `diskutil verifyDisk disk0` (Mac)

### Slow after Windows Update
- Roll back recent update: Settings > Update & Security > View Update History > Uninstall Updates

## Escalation Triggers
- Hardware diagnostics suggest failing drive or RAM
- CPU temperature extremely high (hardware issue)
- Problem persists after all software fixes

## Ticket Template
Slow computer — [employee name] — [root cause from diagnostics] — [steps taken]
