import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.zeroconf import ZeroconfServiceInfo
from homeassistant.data_entry_flow import FlowResult
from homeassistant.core import callback
from homeassistant.helpers import selector
from ducopy import DucoPy
from .const import DOMAIN
import requests
import asyncio

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({
    vol.Required("base_url"): selector.TextSelector(
        selector.TextSelectorConfig(type='url')  # Using URL text selector
    )
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
                # Optional: Perform additional URL validation if needed
                parsed_url = requests.utils.urlparse(base_url)
                if parsed_url.scheme not in ('https'):  # connectivity board only supports https
                    raise ValueError('Invalid URL scheme')
                # Attempt to connect to the device
                await asyncio.get_running_loop().run_in_executor(
                    None, lambda: requests.get(f"{base_url.rstrip('/')}/info", verify=False)
                )
                return self.async_create_entry(title="Ducobox Connectivity Board", data=user_input)
            except (ValueError, requests.RequestException):
                errors["base_url"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=CONFIG_SCHEMA, errors=errors
        )

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> FlowResult:
        """Handle discovery via mDNS."""
        _LOGGER.debug(f"Discovery info: {discovery_info}")

        valid_names = ['duco_', 'duco ']

        if not any(discovery_info.name.lower().startswith(x) for x in valid_names):
            return self.async_abort(reason="not_duco_air_device")

        # Extract information from mDNS discovery
        # Use the IP address directly to avoid '.local' issues
        host = discovery_info.addresses[0]
        unique_id = discovery_info.name.split(" ")[1].strip("[]")

        _LOGGER.debug(f"Extracted host: {host}, unique_id: {unique_id}")

        # Check if the device has already been configured
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        try:
            base_url = f"https://{host}/info"
            duco_client = DucoPy(base_url=base_url, verify=False)
            _LOGGER.debug(f"DucoPy initialized with base URL: {base_url}")
        except Exception as ex:
            _LOGGER.error("Could not connect to Ducobox: %s", ex)
            return self.async_abort(reason="cannot_connect")
        
        try:
            communication_board_info = await asyncio.get_running_loop().run_in_executor(
                None, duco_client.get_info
            )
            _LOGGER.debug(f"Communication board info: {communication_board_info}")
            duco_client.close()
        except Exception as ex:
            _LOGGER.error("Could not get Ducobox info: %s", ex)
            return self.async_abort(reason="unable_to_get_info")

        # Store discovery data in context
        self.context["discovery"] = {
            "host": host,
            "unique_id": unique_id,
            "communication_board_info": communication_board_info
        }

        # Ask user for confirmation
        return await self.async_step_confirm()

    async def async_step_confirm(self, user_input=None) -> FlowResult:
        """Ask user to confirm adding the discovered device."""
        discovery = self.context["discovery"]
        communication_board_type = discovery["communication_board_info"].get("General", {}).get("Board", {}).get("CommSubTypeName", {}).get("Val", "")
        communication_board_mac = discovery["communication_board_info"].get("General", {}).get("Lan", {}).get("Mac", {}).get("Val", "")
        
        if communication_board_type == "CONNECTIVITY":
            product = {
                "title": "Connectivity board",
                "data": {
                    "base_url": f"https://{discovery['host']}",
                    "unique_id": communication_board_mac,
                },
            }
            self.context["title_placeholders"] = {"name": f"Connectivity board ({communication_board_mac})"}

        if user_input is not None:
            return self.async_create_entry(
                title=product["title"],
                data=product["data"],
            )

        self._set_confirm_only()
        # Show confirmation form to the user
        return self.async_show_form(
            step_id="confirm",
            
            description_placeholders={
                "host": discovery["host"],
                "unique_id": discovery["unique_id"],
            },
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