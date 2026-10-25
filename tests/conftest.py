"""Shared pytest fixtures for ha-n8n unit tests."""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock

import pytest

# Minimal Home Assistant stubs so custom_components can import without HA Core.
# Full integration tests belong on HA ≥ 2026.9.3 with pytest-homeassistant-custom-component.


def _ensure_ha_stubs() -> None:
    if "homeassistant" in sys.modules:
        return

    ha = types.ModuleType("homeassistant")
    sys.modules["homeassistant"] = ha

    def _pkg(name: str) -> types.ModuleType:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
        return mod

    components = _pkg("homeassistant.components")
    http_mod = _pkg("homeassistant.components.http")

    class HomeAssistantView:  # noqa: D401 — stub
        """Stub HA HTTP view base."""

        requires_auth = True
        url: str | None = None
        name: str | None = None

    http_mod.HomeAssistantView = HomeAssistantView
    components.http = http_mod

    diagnostics = _pkg("homeassistant.components.diagnostics")

    def async_redact_data(data, to_redact):
        redact = set(to_redact)

        def _walk(obj):
            if isinstance(obj, dict):
                return {
                    k: ("**REDACTED**" if k in redact else _walk(v))
                    for k, v in obj.items()
                }
            if isinstance(obj, list):
                return [_walk(i) for i in obj]
            return obj

        return _walk(data)

    diagnostics.async_redact_data = async_redact_data

    persistent_notification = _pkg("homeassistant.components.persistent_notification")
    persistent_notification.async_create = MagicMock()

    config_entries = _pkg("homeassistant.config_entries")

    class ConfigEntry:
        pass

    class ConfigFlow:
        def __init_subclass__(cls, domain=None, **kwargs):
            return super().__init_subclass__(**kwargs)

        async def async_set_unique_id(self, unique_id):
            self.unique_id = unique_id

        def _abort_if_unique_id_configured(self):
            return None

        def async_create_entry(self, **kwargs):
            return kwargs

        def async_show_form(self, **kwargs):
            return kwargs

        def async_update_reload_and_abort(self, *args, **kwargs):
            return kwargs

    class OptionsFlow:
        @property
        def config_entry(self):
            return getattr(self, "_config_entry", None)

        def async_create_entry(self, **kwargs):
            return kwargs

        def async_show_form(self, **kwargs):
            return kwargs

    class ConfigFlowResult(dict):
        pass

    config_entries.ConfigEntry = ConfigEntry
    config_entries.ConfigFlow = ConfigFlow
    config_entries.OptionsFlow = OptionsFlow
    config_entries.ConfigFlowResult = ConfigFlowResult

    const = _pkg("homeassistant.const")
    const.CONF_URL = "url"
    const.Platform = types.SimpleNamespace(
        SWITCH="switch",
        BUTTON="button",
        BINARY_SENSOR="binary_sensor",
        SENSOR="sensor",
        EVENT="event",
    )
    # Also used via homeassistant.const.EntityCategory in platforms
    const.EntityCategory = types.SimpleNamespace(DIAGNOSTIC="diagnostic")

    core = _pkg("homeassistant.core")
    core.HomeAssistant = MagicMock
    core.ServiceCall = MagicMock
    core.callback = lambda f: f

    exceptions = _pkg("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        pass

    class ServiceValidationError(HomeAssistantError):
        pass

    class ConfigEntryAuthFailed(HomeAssistantError):
        pass

    exceptions.HomeAssistantError = HomeAssistantError
    exceptions.ServiceValidationError = ServiceValidationError
    exceptions.ConfigEntryAuthFailed = ConfigEntryAuthFailed

    helpers = _pkg("homeassistant.helpers")
    aiohttp_client = _pkg("homeassistant.helpers.aiohttp_client")
    aiohttp_client.async_get_clientsession = MagicMock()
    helpers.aiohttp_client = aiohttp_client

    config_validation = _pkg("homeassistant.helpers.config_validation")
    config_validation.string = str
    config_validation.boolean = bool
    helpers.config_validation = config_validation

    update_coordinator = _pkg("homeassistant.helpers.update_coordinator")

    class DataUpdateCoordinator:
        def __class_getitem__(cls, item):
            return cls

        def __init__(self, *args, **kwargs):
            self.data = None
            self.last_update_success = True

        async def async_config_entry_first_refresh(self):
            return None

        async def async_request_refresh(self):
            return None

        def async_add_listener(self, listener):
            return lambda: None

    class CoordinatorEntity:
        def __init__(self, coordinator):
            self.coordinator = coordinator
            self.hass = MagicMock()

        @property
        def available(self):
            return True

        async def async_added_to_hass(self):
            return None

        def async_on_remove(self, remove):
            return None

        def async_write_ha_state(self):
            return None

    class UpdateFailed(Exception):
        pass

    update_coordinator.DataUpdateCoordinator = DataUpdateCoordinator
    update_coordinator.CoordinatorEntity = CoordinatorEntity
    update_coordinator.UpdateFailed = UpdateFailed
    helpers.update_coordinator = update_coordinator

    device_registry = _pkg("homeassistant.helpers.device_registry")
    device_registry.DeviceInfo = dict
    helpers.device_registry = device_registry

    dispatcher = _pkg("homeassistant.helpers.dispatcher")
    dispatcher.async_dispatcher_send = MagicMock()
    dispatcher.async_dispatcher_connect = MagicMock(return_value=lambda: None)
    helpers.dispatcher = dispatcher

    entity_platform = _pkg("homeassistant.helpers.entity_platform")
    entity_platform.AddEntitiesCallback = object
    helpers.entity_platform = entity_platform

    util = _pkg("homeassistant.util")
    dt = _pkg("homeassistant.util.dt")

    class _DT:
        @staticmethod
        def utcnow():
            from datetime import datetime, timezone

            return datetime.now(timezone.utc)

    dt.utcnow = _DT.utcnow
    util.dt = dt

    # Platform stubs used only if imported by tests
    for name in ("switch", "button", "binary_sensor", "sensor", "event"):
        mod = _pkg(f"homeassistant.components.{name}")
        if name == "switch":
            mod.SwitchEntity = type("SwitchEntity", (), {})
        elif name == "button":
            mod.ButtonEntity = type("ButtonEntity", (), {})
        elif name == "binary_sensor":
            mod.BinarySensorEntity = type("BinarySensorEntity", (), {})
            mod.BinarySensorDeviceClass = types.SimpleNamespace(
                CONNECTIVITY="connectivity"
            )
        elif name == "sensor":

            class SensorEntity:
                pass

            class SensorEntityDescription:
                def __init__(self, **kwargs):
                    self.__dict__.update(kwargs)

            mod.SensorEntity = SensorEntity
            mod.SensorEntityDescription = SensorEntityDescription
        elif name == "event":
            mod.EventEntity = type("EventEntity", (), {})

    # EntityCategory is imported from homeassistant.const in platforms
    if not hasattr(const, "EntityCategory"):
        const.EntityCategory = types.SimpleNamespace(DIAGNOSTIC="diagnostic")

    repairs_mod = _pkg("homeassistant.components.repairs")

    class RepairsFlow:
        def async_show_form(self, **kwargs):
            return kwargs

        def async_create_entry(self, **kwargs):
            return kwargs

        def async_abort(self, **kwargs):
            return kwargs

    class ConfirmRepairFlow(RepairsFlow):
        pass

    repairs_mod.RepairsFlow = RepairsFlow
    repairs_mod.ConfirmRepairFlow = ConfirmRepairFlow

    data_entry_flow = _pkg("homeassistant.data_entry_flow")
    data_entry_flow.FlowResult = dict

    issue_registry = _pkg("homeassistant.helpers.issue_registry")
    issue_registry.async_create_issue = MagicMock()
    issue_registry.async_delete_issue = MagicMock()
    issue_registry.IssueSeverity = types.SimpleNamespace(
        WARNING="warning", ERROR="error"
    )
    helpers.issue_registry = issue_registry


_ensure_ha_stubs()


@pytest.fixture
def workflows_list_payload() -> dict:
    """Sanitized n8n workflows list fixture (no secrets)."""
    return {
        "data": [
            {
                "id": "wf1",
                "name": "Morning Lights",
                "active": True,
                "createdAt": "2026-01-01T00:00:00.000Z",
                "updatedAt": "2026-01-02T00:00:00.000Z",
                "tags": [{"id": "t1", "name": "home"}],
                "nodes": [
                    {
                        "type": "n8n-nodes-base.webhook",
                        "parameters": {"path": "morning-lights"},
                    }
                ],
            },
            {
                "id": "wf2",
                "name": "No Webhook",
                "active": False,
                "tags": [],
                "nodes": [{"type": "n8n-nodes-base.manualTrigger", "parameters": {}}],
            },
        ],
        "nextCursor": None,
    }
