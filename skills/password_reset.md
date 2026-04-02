# Skill: Password Reset / Account Lockout

## Triggers
password, locked out, can't login, account, reset, forgot, expired, lockout

## Diagnosis Steps
1. Ask which system they're locked out of (Windows login, email, VPN, specific app)
2. Ask if they get a specific error message
3. Ask if they have MFA/authenticator app available

## Fixes by Symptom

### Windows account locked out
- If domain joined: IT admin must unlock in Active Directory Users and Computers
- If local account: boot to recovery and reset via command prompt — escalate to IT
- Check lockout policy: failed attempts before lockout (typically 5-10)

### Microsoft 365 / Email password
- Self-service reset at: https://passwordreset.microsoftonline.com
- Needs recovery email or phone number set up
- If self-service not available, admin must reset in M365 admin center

### VPN account locked
- Usually tied to Active Directory — same as Windows account
- Check if VPN has separate account — escalate to network team

### Password expired
- Windows will prompt at login — change before it fully expires
- If already expired, may need admin to reset and force change at next login

## Escalation Triggers
- Suspected security breach or unauthorized access
- MFA device lost or unavailable
- Admin account locked out

## Ticket Template
Account lockout — [system] — [employee name] — [resolution method]
