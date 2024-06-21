"""Config flow for kocom_wallpad integration."""

import socket
from typing import Any, cast


from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from .util import EntryData, typed_data
from .const import (
    CONF_ELEVATOR,
    CONF_FAN,
    CONF_GAS,
    CONF_LIGHT,
    CONF_ROOM_NAME,
    CONF_THERMO,
    DOMAIN,
)


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
            data = self._parse_user_input(user_input)
            errors, description_placeholders = self._validate_input(data)

            try:
                await _test_connection(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"

            if not errors:
                if entry_id := self.context.get("entry_id"):
                    entry = self.hass.config_entries.async_get_entry(entry_id)
                    assert entry
                    return self.async_update_reload_and_abort(entry, data=data)

                return self.async_create_entry(
                    title=f"EW11_{data[CONF_HOST]}",
                    data=data,
                )

        return self.async_show_form(
            step_id="user",  # reuse same translate when triggered by reconfigure
            data_schema=schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    def _parse_user_input(self, user_input: dict[str, Any]) -> EntryData:
        data = cast(EntryData, user_input.copy())
        if light_str := user_input.get(CONF_LIGHT):
            data[CONF_LIGHT] = {
                k: int(v) for k, v in (kv.split(":") for kv in light_str.split(","))
            }
        else:
            data[CONF_LIGHT] = {}

        if thermo_str := user_input.get(CONF_THERMO):
            data[CONF_THERMO] = {room: True for room in thermo_str.split(",")}
        else:
            data[CONF_THERMO] = {}

        if room_name := user_input.get(CONF_ROOM_NAME):
            data[CONF_ROOM_NAME] = dict(
                pair.split(":") for pair in room_name.split(",")
            )
        else:
            data[CONF_ROOM_NAME] = {
                "0": "거실",
                "1": "안방",
                "2": "방1",
                "3": "방2",
            }

        return data

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration."""
        return await self.async_step_user(user_input)

    def _validate_input(self, parsed_user_input: EntryData):
        this_entry_id = self.context.get("entry_id")
        errors, description_placeholders = {}, {}

        for entry in self._async_current_entries(include_ignore=False):
            if entry.entry_id == this_entry_id:
                continue

            data = typed_data(entry)

            # other entry already configured with the same host
            if data[CONF_HOST] == parsed_user_input[CONF_HOST]:
                errors[CONF_HOST] = "duplicated_host"

            # other entry already configured with the same light room
            this = set(parsed_user_input[CONF_LIGHT].keys())
            other = set(data[CONF_LIGHT].keys())
            if this.intersection(other):
                errors[CONF_LIGHT] = "duplicated_room"

            # other entry already configured with the same thermo room
            this = set(parsed_user_input[CONF_THERMO].keys())
            other = set(data[CONF_THERMO].keys())
            if this.intersection(other):
                errors[CONF_THERMO] = "duplicated_room"

            # other entry selected fan
            if parsed_user_input[CONF_FAN] and data[CONF_FAN]:
                errors[CONF_FAN] = "selected_by_other_entry"

            # other entry selected gas
            if parsed_user_input[CONF_GAS] and data[CONF_GAS]:
                errors[CONF_GAS] = "selected_by_other_entry"

            # other entry selected elevator
            if parsed_user_input[CONF_ELEVATOR] and data[CONF_ELEVATOR]:
                errors[CONF_ELEVATOR] = "selected_by_other_entry"
        return errors, description_placeholders

    def _schema_with_prev_data(self) -> vol.Schema:
        current_entry = self.hass.config_entries.async_get_entry(
            self.context.get("entry_id", "")
        )

        def get_prev(key: str, default: Any):
            return current_entry.data.get(key, default) if current_entry else default

        schema_ew11 = {
            vol.Required(
                CONF_HOST,
                default=get_prev(CONF_HOST, ""),
            ): cv.string,
            vol.Required(CONF_PORT, default=get_prev(CONF_PORT, 8899)): cv.port,
        }

        conf_light_default = ""
        light: dict[str, int] = get_prev(CONF_LIGHT, {})
        if light:
            conf_light_default = ",".join(f"{k}:{v}" for k, v in light.items())

        conf_thermo_default = ""
        thermo: dict[str, bool] = get_prev(CONF_THERMO, {})
        if thermo:
            conf_thermo_default = ",".join(k for k in thermo)

        schema_device = {
            vol.Optional(CONF_LIGHT, default=conf_light_default): cv.string,  # type: ignore
            vol.Optional(CONF_THERMO, default=conf_thermo_default): cv.string,  # type: ignore
            vol.Optional(CONF_FAN, default=get_prev(CONF_FAN, False)): cv.boolean,
            vol.Optional(CONF_GAS, default=get_prev(CONF_GAS, False)): cv.boolean,
            vol.Optional(
                CONF_ELEVATOR, default=get_prev(CONF_ELEVATOR, False)
            ): cv.boolean,
            vol.Optional(
                CONF_ROOM_NAME, default=get_prev(CONF_ROOM_NAME, "")
            ): cv.string,
        }

        return vol.Schema(schema_ew11).extend(schema_device)


async def _test_connection(hass: HomeAssistant, input: dict[str, Any]) -> None:
    def test_connection(host, port):
        try:
            sock = socket.create_connection(address=(host, port), timeout=5)
        except TimeoutError as err:
            raise CannotConnect from err
        else:
            sock.close()

    await hass.async_add_executor_job(
        test_connection, input[CONF_HOST], input[CONF_PORT]
    )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""
