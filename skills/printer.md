# Skill: Printer Issues

## Triggers
printer, printing, print, scanner, scan, paper, ink, toner, queue, spooler

## Diagnosis Steps
1. Ask if printer shows as offline or online in Windows
2. Ask if it's a network printer or USB connected
3. Ask if anyone else can print to same printer

## Fixes by Symptom

### Printer shows offline
- Right-click printer > See what's printing > Printer menu > uncheck Use Printer Offline
- Restart Print Spooler: services.msc > Print Spooler > Restart
- Remove and re-add the printer

### Print jobs stuck in queue
- Open print queue > cancel all documents
- If won't clear: stop Print Spooler service, delete files in `C:\Windows\System32\spool\PRINTERS\`, restart Print Spooler

### Network printer not found
- Check printer IP hasn't changed (print a config page from printer itself)
- Re-add using TCP/IP port with correct IP address
- Check firewall isn't blocking ports 9100, 515, 631

### Poor print quality
- Run printer's built-in cleaning cycle
- Check ink/toner levels
- Align print heads if inkjet

## Escalation Triggers
- Hardware fault codes on printer display
- Network printer unreachable from all machines
- Firmware update needed

## Ticket Template
Printer issue — [printer name/model] — [symptom] — [resolution or escalation]
