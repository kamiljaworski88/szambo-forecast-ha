"""Configure sensors in HA, preserve old YAML installations through import."""

from datetime import date

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er, selector

from .const import DEFAULT_DISTANCE, DEFAULT_LEVEL, DOMAIN


def schema(defaults, *, initial):
    fields = {
        vol.Required("level_entity", default=defaults.get("level_entity", DEFAULT_LEVEL)):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
        vol.Required("distance_entity", default=defaults.get("distance_entity", DEFAULT_DISTANCE)):
            selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor")),
    }
    if initial:
        fields[vol.Required("threshold", default=defaults.get("threshold", 90))] = selector.NumberSelector(
            selector.NumberSelectorConfig(min=1, max=100, step=1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="%"))
    helper = vol.Optional("threshold_entity", **({"default": defaults["threshold_entity"]} if defaults.get("threshold_entity") else {}))
    fields.update({
        helper: selector.EntitySelector(selector.EntitySelectorConfig(domain=["input_number", "number"])),
        vol.Required("history_start", default=defaults.get("history_start", "2000-01-01")): selector.DateSelector(),
        vol.Required("emptying_drop", default=defaults.get("emptying_drop", 15)):
            selector.NumberSelector(selector.NumberSelectorConfig(min=10, max=50, step=1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="p.p.")),
    })
    return vol.Schema(fields)


def validate(hass, data):
    errors = {}
    for field in ("level_entity", "distance_entity", "threshold_entity"):
        entity = data.get(field)
        if entity and hass.states.get(entity) is None:
            errors[field] = "entity_missing"
    if data["level_entity"] == data["distance_entity"]:
        errors["base"] = "same_entity"
    helper = data.get("threshold_entity")
    if helper:
        item = er.async_get(hass).async_get(helper)
        if item and item.platform == DOMAIN:
            errors["threshold_entity"] = "own_threshold"
    try:
        start = date.fromisoformat(data["history_start"])
        from homeassistant.util import dt as dt_util
        if start > dt_util.now().date():
            errors["history_start"] = "future_date"
    except (TypeError, ValueError):
        errors["history_start"] = "invalid_date"
    return errors


class ForecastConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ForecastOptionsFlow()

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors = {}
        if user_input is not None:
            errors = validate(self.hass, user_input)
            if not errors:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                data = {**user_input, "threshold_entity": user_input.get("threshold_entity")}
                return self.async_create_entry(title="Prognoza szamba", data=data)
        return self.async_show_form(step_id="user", data_schema=schema(user_input or {}, initial=True), errors=errors)

    async def async_step_import(self, imported):
        await self.async_set_unique_id(DOMAIN)
        existing = self._async_current_entries()
        if existing and existing[0].source == config_entries.SOURCE_IMPORT:
            self._abort_if_unique_id_configured(updates=imported)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Prognoza szamba", data=imported)


class ForecastOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        errors = {}
        defaults = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            errors = validate(self.hass, user_input)
            defaults.update(user_input)
            if not errors:
                return self.async_create_entry(title="", data={**user_input, "threshold_entity": user_input.get("threshold_entity")})
        return self.async_show_form(step_id="init", data_schema=schema(defaults, initial=False), errors=errors)
