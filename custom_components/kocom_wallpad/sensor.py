"""Kocom Wallpad Air Quality Sensors."""

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .hub import Hub, AirQuality
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Kocom Wallpad air quality sensors from a config entry."""
    hub: Hub = hass.data[DOMAIN][entry.entry_id]

    if air_quality := hub.air_quality:
        entities = [
            KocomPM10Sensor(air_quality),
            KocomPM25Sensor(air_quality),
            KocomCO2Sensor(air_quality),
            KocomVOCSensor(air_quality),
            KocomTemperatureSensor(air_quality),
            KocomHumiditySensor(air_quality),
        ]
        async_add_entities(entities)


class KocomAirQualitySensorBase(SensorEntity):
    """Base class for Kocom air quality sensors."""

    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, air_quality: AirQuality) -> None:
        """Initialize the sensor."""
        self.air_quality = air_quality

    async def async_added_to_hass(self) -> None:
        """Register callback when entity is added to hass."""
        self.air_quality.register_callback(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callback when entity is removed from hass."""
        self.air_quality.remove_callback(self.async_write_ha_state)


class KocomPM10Sensor(KocomAirQualitySensorBase):
    """PM10 sensor entity."""

    _attr_device_class = SensorDeviceClass.PM10
    _attr_native_unit_of_measurement = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER

    def __init__(self, air_quality: AirQuality) -> None:
        """Initialize the PM10 sensor."""
        super().__init__(air_quality)
        self._attr_unique_id = "air_quality_pm10"
        self._attr_name = "미세먼지"

    @property
    def native_value(self) -> int:
        """Return the PM10 value."""
        return self.air_quality.pm10


class KocomPM25Sensor(KocomAirQualitySensorBase):
    """PM2.5 sensor entity."""

    _attr_device_class = SensorDeviceClass.PM25
    _attr_native_unit_of_measurement = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER

    def __init__(self, air_quality: AirQuality) -> None:
        """Initialize the PM2.5 sensor."""
        super().__init__(air_quality)
        self._attr_unique_id = "air_quality_pm25"
        self._attr_name = "초미세먼지"

    @property
    def native_value(self) -> int:
        """Return the PM2.5 value."""
        return self.air_quality.pm25


class KocomCO2Sensor(KocomAirQualitySensorBase):
    """CO2 sensor entity."""

    _attr_device_class = SensorDeviceClass.CO2
    _attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION

    def __init__(self, air_quality: AirQuality) -> None:
        """Initialize the CO2 sensor."""
        super().__init__(air_quality)
        self._attr_unique_id = "air_quality_co2"
        self._attr_name = "이산화탄소"

    @property
    def native_value(self) -> int:
        """Return the CO2 value."""
        return self.air_quality.co2


class KocomVOCSensor(KocomAirQualitySensorBase):
    """VOC sensor entity."""

    _attr_device_class = SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS
    _attr_native_unit_of_measurement = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER

    def __init__(self, air_quality: AirQuality) -> None:
        """Initialize the VOC sensor."""
        super().__init__(air_quality)
        self._attr_unique_id = "air_quality_voc"
        self._attr_name = "휘발성유기화합물"

    @property
    def native_value(self) -> int:
        """Return the VOC value."""
        return self.air_quality.voc


class KocomTemperatureSensor(KocomAirQualitySensorBase):
    """Temperature sensor entity."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, air_quality: AirQuality) -> None:
        """Initialize the temperature sensor."""
        super().__init__(air_quality)
        self._attr_unique_id = "air_quality_temperature"
        self._attr_name = "온도"

    @property
    def native_value(self) -> int:
        """Return the temperature value."""
        return self.air_quality.temperature


class KocomHumiditySensor(KocomAirQualitySensorBase):
    """Humidity sensor entity."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, air_quality: AirQuality) -> None:
        """Initialize the humidity sensor."""
        super().__init__(air_quality)
        self._attr_unique_id = "air_quality_humidity"
        self._attr_name = "습도"

    @property
    def native_value(self) -> int:
        """Return the humidity value."""
        return self.air_quality.humidity
