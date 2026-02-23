# Telegram Commands (Control Plane)

Core:
/cm_new <objective text>
/cm_status
/cm_reviews

Review gates:
/cm_approve T-0002
/cm_change T-0002 <notes>
/cm_block T-0002 <notes>

Ops:
/cm_requeue T-0002
/cm_unlock T-0002

Notes:
- Only TELEGRAM_ALLOWED_USER_ID is honored.
- Status returns runs/<current-run>/status.md (truncated).
- Marketing Head will proactively message when tasks enter awaiting_review and include /approve /change /block command hints.
- Namespace is controlled by TELEGRAM_COMMAND_NAMESPACE (default: cm). Legacy unprefixed commands are still accepted.
