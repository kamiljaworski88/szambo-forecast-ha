"""Constants; existing source entities are never modified."""

DOMAIN = "septic_forecast"
DEFAULT_LEVEL = "sensor.procent_szamba"
DEFAULT_DISTANCE = "sensor.czujnik_szamba_distance_sensor"
DEFAULT_THRESHOLD = "input_number.szambo_prognoza_prog"
MANAGED_THRESHOLD = "number.szambo_prognoza_prog"
SIGNAL_UPDATE = f"{DOMAIN}_update"
