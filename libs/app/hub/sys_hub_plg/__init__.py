"""Trusted built-in, headless-capable Hub collector modules.

Add a single <name>.py defining HUB_PROVIDER_KEY and hub_collect(context).
The collector returns HubProviderSnapshot for a centrally supported dataset;
it never receives DB connections or executes SQL. Schema migrations and
writers are centrally reviewed/verified; see docs/sysapps-hub.md.
"""
