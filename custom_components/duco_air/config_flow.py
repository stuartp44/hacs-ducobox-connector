import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN
import requests
import asyncio

CONFIG_SCHEMA = vol.Schema({
    vol.Required("base_url"): str
})

class DucoboxConnectivityBoardConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Ducobox Connectivity Board."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step for config flow."""
        errors = {}

        if user_input is not None:
            base_url = user_input["base_url"]
            try:
                await asyncio.get_running_loop().run_in_executor(
                    None, lambda: requests.get(f"{base_url.rstrip('/')}/info", verify=False)
                )
                return self.async_create_entry(title="Ducobox Connectivity Board", data=user_input)
            except requests.RequestException:
                errors["base_url"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=CONFIG_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DucoboxOptionsFlowHandler(config_entry)


class DucoboxOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Ducobox Connectivity Board."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(step_id="init", data_schema=vol.Schema({}))
