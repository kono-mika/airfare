INVENTED TEST DATA. Nothing in this folder is real.

This is a complete AirFare data folder as AirFare 1.4.1 writes it (no version.json, so it counts as
schema 1). tests/test_migrate.py copies it and checks that updating to a newer AirFare keeps every route
id, price record, lowest-price lookup, dashboard tab, alert reference and analyst conversation.

Everything here was made up for the tests: the route names and the airport codes (ZZAA, ZZBB, ZZCC and
ZZDD are not airports), the dates, the prices, the exchange rates, the session ids, the conversation and
the links (example.com). The API keys are empty.
