# Keep Agent UI behind a stable Presentation Contract

The Agent conversation UI consumes a versioned BioinfoFlow Presentation Contract
and a client-side Conversation View rather than Harness snapshots, events, or
provider payloads. Each Harness is adapted on the server into the same product
language, so replacing a Harness cannot require replacing the Composer or
Transcript renderer; unknown blocks degrade safely instead of crashing the
Conversation.
