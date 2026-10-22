"""Four output entities; fixed suggested IDs used by the example dashboard."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_UPDATE

SENSORS = (
    ("dni", "Szambo dni do odbioru", "mdi:calendar-clock", "dni", None),
    ("data", "Szambo przewidywana data odbioru", "mdi:calendar", None, SensorDeviceClass.TIMESTAMP),
    ("tempo", "Szambo tempo napelniania", "mdi:water-plus", "p.p./dobę", None),
    ("wiarygodnosc", "Szambo wiarygodnosc prognozy", "mdi:shield-check", None, None),
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    async_add_entities([ForecastSensor(hass.data[DOMAIN], *description) for description in SENSORS])


class ForecastSensor(SensorEntity):
    _attr_should_poll = False

    def __init__(self, runtime, key, name, icon, unit, device_class):
        self.runtime, self.key = runtime, key
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{key}"
        self._attr_icon = icon
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self.async_write_ha_state))

    @property
    def native_value(self):
        result = self.runtime.result
        if self.key == "dni":
            return round(result.days, 1) if result.days is not None else None
        if self.key == "data":
            return result.date
        if self.key == "tempo":
            return round(result.rate, 2) if result.rate is not None else None
        return result.confidence

    @property
    def extra_state_attributes(self):
        if self.key != "wiarygodnosc":
            return None
        result = self.runtime.result
        return {
            "powod": result.reason,
            "dni_biezacego_cyklu": result.current_days,
            "pelne_cykle_historyczne": result.complete_cycles,
            "tempo_biezace": result.current_rate,
            "tempo_historyczne": result.historical_rate,
            "waga_biezacego_cyklu": result.current_weight,
            "odrzucone_godziny": result.rejected_hours,
            "rozpoznane_odbiory": result.detected_emptyings,
            "historia": self.runtime.diagnostics,
        }
