"""Config flow for kocom_wallpad integration."""

from __future__ import annotations
import logging
from typing import Any


from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    ConfigEntry,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from .ew11 import Ew11Socket

from .const import CONF_ELEVATOR, CONF_FAN, CONF_GAS, CONF_LIGHT, CONF_THERMO, DOMAIN

_LOGGER = logging.getLogger(__name__)


class KocomWallpadConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for kocom_wallpad."""

    VERSION = 0
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        schema = self._schema_with_prev_data()
        errors = {}
        description_placeholders = {}
        if user_input is not None:
            self._update_user_input(user_input)
            errors, description_placeholders = self._validate_input(user_input)

            try:
                await _test_connection(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"

            if not errors:
                return self.async_create_entry(
                    title=f"EW11_{len(self._async_current_entries())}",
                    data=user_input,
                )

        return self.async_show_form(
            data_schema=schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    def _update_user_input(self, user_input: dict[str, Any]):
        # no int() for key: because when HA reloads, it will be string
        if light_str := user_input.get(CONF_LIGHT):
            user_input[CONF_LIGHT] = {
                k: int(v) for k, v in (kv.split(":") for kv in light_str.split(","))
            }
        else:
            user_input[CONF_LIGHT] = {}

        if thermo_str := user_input.get(CONF_THERMO):
            user_input[CONF_THERMO] = {room: True for room in thermo_str.split(",")}
        else:
            _LOGGER.debug("thermo_str is empty")
            user_input[CONF_THERMO] = {}

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration."""
        schema = self._schema_with_prev_data()
        errors = {}
        description_placeholders = {}
        if user_input is not None:
            self._update_user_input(user_input)
            errors, description_placeholders = self._validate_input(user_input)

            try:
                await _test_connection(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"

            if not errors:
                entry = self.hass.config_entries.async_get_entry(
                    self.context["entry_id"]
                )
                assert entry
                return self.async_update_reload_and_abort(entry, data=user_input)

        return self.async_show_form(
            data_schema=schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    def _validate_input(self, user_input: dict[str, Any]):
        this_entry_id = self.context.get("entry_id")
        errors = {}
        description_placeholders = {}
        for entry in self._async_current_entries():
            if entry.entry_id != this_entry_id:
                # other entry already configured with the same host
                if entry.data[CONF_HOST] == user_input[CONF_HOST]:
                    errors["base"] = "already_configured"

                # other entry already configured with the same light room
                this_light_rooms = set(user_input[CONF_LIGHT].keys())
                other_light_rooms = set(x for x in entry.data[CONF_LIGHT].keys())
                if duplicated_light := this_light_rooms.intersection(other_light_rooms):
                    errors[CONF_LIGHT] = "light_duplicated"
                    duplicated_room = ",".join(duplicated_light)
                    description_placeholders["dup_room_light"] = duplicated_room

                # other entry already configured with the same thermo room
                this_thermo_rooms = set(user_input[CONF_THERMO].keys())
                other_thermo_rooms = set(entry.data[CONF_THERMO].keys())
                if duplicated_thermo := this_thermo_rooms.intersection(
                    other_thermo_rooms
                ):
                    errors[CONF_THERMO] = "thermo_duplicated"
                    deuplicated_room = ",".join(duplicated_thermo)
                    description_placeholders["dup_room_thermo"] = deuplicated_room

                # other entry selected fan
                if user_input[CONF_FAN] and entry.data[CONF_FAN]:
                    errors[CONF_FAN] = "only_one_allowed"

                # other entry selected gas
                if user_input[CONF_GAS] and entry.data[CONF_GAS]:
                    errors[CONF_GAS] = "only_one_allowed"

                # other entry selected elevator
                if user_input[CONF_ELEVATOR] and entry.data[CONF_ELEVATOR]:
                    errors[CONF_ELEVATOR] = "only_one_allowed"
        return errors, description_placeholders

    def _schema_with_prev_data(self) -> vol.Schema:
        current_entry = self.hass.config_entries.async_get_entry(
            self.context.get("entry_id", "")
        )

        def get_prev(key: str, default: Any):
            if current_entry:
                return current_entry.data.get(key, default)
            else:
                return default

        schema_ew11 = vol.Schema(
            {
                vol.Required(
                    CONF_HOST,
                    default=get_prev(CONF_HOST, ""),
                ): cv.string,
                vol.Required(CONF_PORT, default=get_prev(CONF_PORT, 8899)): cv.port,
            }
        )

        light_str = ""
        if light := get_prev(CONF_LIGHT, ""):
            light_str = ",".join(f"{k}:{v}" for k, v in light.items() if v != 0)

        thermo_str = ""
        if thermo := get_prev(CONF_THERMO, {}):
            thermo_str = ",".join(k for k in thermo.keys())

        schema_device = {
            vol.Optional(CONF_LIGHT, default=light_str): cv.string,  # type: ignore
            vol.Optional(CONF_THERMO, default=thermo_str): cv.string,  # type: ignore
            vol.Optional(CONF_FAN, default=get_prev(CONF_FAN, False)): cv.boolean,
            vol.Optional(CONF_GAS, default=get_prev(CONF_GAS, False)): cv.boolean,
            vol.Optional(
                CONF_ELEVATOR, default=get_prev(CONF_ELEVATOR, False)
            ): cv.boolean,
        }

        return schema_ew11.extend(schema_device)


async def _test_connection(hass: HomeAssistant, input: dict[str, Any]):
    """Validate the user input allows us to connect."""

    def test_connection(host, port):
        try:
            sock = Ew11Socket(host, port)
        except OSError as err:
            raise CannotConnect from err
        else:
            sock.close()

    await hass.async_add_executor_job(
        test_connection, input[CONF_HOST], input[CONF_PORT]
    )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
