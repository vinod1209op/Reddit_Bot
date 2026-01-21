# ADR 0001: Human-in-the-Loop Approval

## Status
Accepted

## Context
The system can draft replies but must avoid autonomous posting in sensitive domains.

## Decision
Every reply requires explicit human approval before posting. Default mode is dry-run.

## Consequences
- Slower throughput but safer operation.
- Clear auditability of who approved a reply.
