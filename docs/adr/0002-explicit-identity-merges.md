# Identity merges are explicit

Skoleintra treats source IDs for Children and Groups as authoritative and does not auto-merge records when a familiar name appears with a new ID. We chose explicit CLI-driven merges with a canonical surviving identity and audit trail because silent heuristics would risk corrupting the archive, while deliberate merges preserve history without replaying notifications.
