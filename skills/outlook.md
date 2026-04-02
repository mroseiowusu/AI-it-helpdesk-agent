# Skill: Outlook / Email Not Working

## Triggers
outlook, email, mail, inbox, sending, receiving, calendar, teams, office

## Diagnosis Steps
1. Ask what exactly isn't working (not opening, not sending, not receiving, calendar issues)
2. Ask if Outlook is desktop app or web (OWA)
3. Ask when it last worked

## Fixes by Symptom

### Outlook won't open
- Run as administrator and see if it opens
- Start in safe mode: hold Ctrl while clicking Outlook icon
- Repair Office: Control Panel > Programs > Microsoft Office > Change > Quick Repair
- Delete Outlook profile and recreate: Control Panel > Mail > Show Profiles > Remove > Add

### Not sending or receiving
- Check if in offline mode: Send/Receive tab > Work Offline (should NOT be highlighted)
- Test with Outlook web app — if OWA works, issue is with desktop client
- Check autodiscover: run `Test-OutlookConnectivity` in Exchange PowerShell if available
- Update password if recently changed: File > Account Settings > update password

### Calendar not syncing
- Remove and re-add the calendar account
- Check shared calendar permissions with organizer
- Clear Outlook cache: close Outlook, delete contents of `%localappdata%\Microsoft\Outlook`

### OST file corruption
- Close Outlook
- Run `scanpst.exe` (Inbox Repair Tool) on the OST file
- Location: `C:\Users\[user]\AppData\Local\Microsoft\Outlook\`

## Escalation Triggers
- Exchange server errors (error codes 0x800CCC0E etc.)
- Multiple users affected simultaneously
- Mailbox over quota

## Ticket Template
Outlook issue — [symptom] — [desktop or web] — [resolution or escalation]
