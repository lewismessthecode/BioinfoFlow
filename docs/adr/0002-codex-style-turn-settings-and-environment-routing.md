# Snapshot mutable Conversation settings when a Run starts

Model, permission, and environment scope remain mutable Conversation settings,
while every started Run persists an immutable Turn Execution Config. Queued input
uses the latest confirmed settings when it actually starts, matching Codex; tool
calls select an authorized environment explicitly through a shared Workspace
Router rather than mutating an implicit current host or duplicating remote tool
families.
