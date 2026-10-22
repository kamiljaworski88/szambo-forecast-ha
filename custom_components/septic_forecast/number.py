"""One persisted threshold control when no external helper is selected."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_UPDATE


async def async_setup_entry(hass, entry, async_add_entities):
    if not entry.runtime_data.config.get("threshold_entity"):
        async_add_entities([ForecastThreshold(entry.runtime_data)])


class ForecastThreshold(NumberEntity):
    _attr_name = "Szambo prognoza prog"
    _attr_unique_id = f"{DOMAIN}_threshold"
    _attr_icon = "mdi:water-percent-alert"
    _attr_native_unit_of_measurement = "%"
    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_should_poll = False

    def __init__(self, runtime):
        self.runtime = runtime

    async def async_added_to_hass(self):
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self.async_write_ha_state))

    @property
    def native_value(self):
        return self.runtime.threshold

    async def async_set_native_value(self, value):
        await self.runtime.async_set_threshold(value)
