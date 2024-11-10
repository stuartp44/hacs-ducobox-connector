import logging
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from .const import DOMAIN
from ducopy import DucoPy

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Ducobox Connectivity Board integration."""
    _LOGGER.debug("Setting up Ducobox Connectivity Board integration")
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Ducobox from a config entry."""
    base_url = entry.data["base_url"]

    try:
        duco_client = DucoPy(base_url=base_url, verify=False)
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN] = duco_client
    except Exception as ex:
        _LOGGER.error("Could not connect to Ducobox: %s", ex)
        raise ConfigEntryNotReady from ex

    await hass.config_entries.async_forward_entry_setup(entry, "sensor")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
