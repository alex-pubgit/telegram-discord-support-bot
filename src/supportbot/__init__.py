"""Support bot for Telegram and Discord communities.

The package is split into a transport-agnostic core (`brain`, `kb`, `answer`,
`guardrails`, `storage`) and thin adapters (`adapters`, `simulator`) that only
translate platform events into messages and execute the returned actions.
"""

__version__ = "0.1.0"
