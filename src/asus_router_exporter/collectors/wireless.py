"""
Wireless metrics collector.

Collects:
- WPS enabled status
- Smart Connect enabled status
- Band information (2.4G, 5G, 5G-2, 6G)
- Band modes, auth modes, crypto settings
"""

from __future__ import annotations

import logging
from typing import Any

from prometheus_client import CollectorRegistry, Gauge, Info

from ..client import models as client_models
from ..core.protocols import ConfigProviderProtocol, RouterClientProtocol
from .base import BaseCollector

logger = logging.getLogger(__name__)


class WirelessCollector(BaseCollector):
    """
    Collector for wireless metrics.

    Metrics:
    - asus_router_wireless_wps_enabled
    - asus_router_wireless_smart_connect_enabled
    - asus_router_wireless_band (Info)
    - asus_router_wireless_band_mode (one-hot)
    - asus_router_wireless_auth_mode (one-hot)
    - asus_router_wireless_crypto (one-hot)
    - asus_router_wireless_ssid_hidden
    """

    name = "wireless"

    def __init__(
        self,
        registry: CollectorRegistry,
        config: ConfigProviderProtocol,
    ):
        # Track active wireless bands to detect and remove stale metrics
        self._active_bands: set[str] = set()
        super().__init__(registry, config)

    def _create_metrics(self) -> None:
        """Create wireless metrics."""
        self._wps_enabled = Gauge(
            "asus_router_wireless_wps_enabled",
            "Wireless WPS enabled (0/1)",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._wps_enabled)

        self._smart_connect = Gauge(
            "asus_router_wireless_smart_connect_enabled",
            "Wireless Smart Connect enabled",
            ["product_id"],
            registry=self._registry,
        )
        self._register_metric(self._smart_connect)

        self._band_info = Info(
            "asus_router_wireless_band",
            "Wireless Band info",
            ["product_id", "wl_unit"],
            registry=self._registry,
        )
        self._register_metric(self._band_info)

        self._band_mode = Gauge(
            "asus_router_wireless_band_mode",
            "Wireless Band mode (one-hot)",
            ["product_id", "wl_unit", "wl_mode"],
            registry=self._registry,
        )
        self._register_metric(self._band_mode)

        self._auth_mode = Gauge(
            "asus_router_wireless_auth_mode",
            "Wireless Auth mode (one-hot)",
            ["product_id", "wl_unit", "wl_auth_mode"],
            registry=self._registry,
        )
        self._register_metric(self._auth_mode)

        self._crypto = Gauge(
            "asus_router_wireless_crypto",
            "Wireless Crypto (one-hot)",
            ["product_id", "wl_unit", "wl_crypto"],
            registry=self._registry,
        )
        self._register_metric(self._crypto)

        self._ssid_hidden = Gauge(
            "asus_router_wireless_ssid_hidden",
            "Wireless SSID hidden (0/1)",
            ["product_id", "wl_unit"],
            registry=self._registry,
        )
        self._register_metric(self._ssid_hidden)

    def _collect_metrics(self, router_client: RouterClientProtocol, router_info: Any) -> None:
        """Collect wireless metrics from router."""
        product_id = getattr(router_info, "product_id", "unknown")

        try:
            wireless_info = router_client.get_wireless_info()
        except Exception:
            logger.warning("[%s] Wireless collection failed", product_id, exc_info=True)
            return

        # WPS enabled
        wps_enabled = getattr(wireless_info, "wps_enabled", False)
        self._wps_enabled.labels(product_id=product_id).set(1 if wps_enabled else 0)

        # Smart Connect enabled
        smart_connect = getattr(wireless_info, "smart_connect_enabled", False)
        self._smart_connect.labels(product_id=product_id).set(1 if smart_connect else 0)

        # Collect band-specific metrics and track which bands are active
        current_bands: set[str] = set()
        bands = [
            ("0", getattr(wireless_info, "band_2G_info", None)),
            ("1", getattr(wireless_info, "band_5G_info", None)),
            ("2", getattr(wireless_info, "band_5G_2_info", None)),
            ("3", getattr(wireless_info, "band_6G_info", None)),
        ]
        for wl_unit, band_info in bands:
            if band_info is not None:
                current_bands.add(wl_unit)
                self._collect_band_metrics(product_id, wl_unit, band_info)

        # Remove stale band metrics
        self._remove_stale_band_metrics(product_id, self._active_bands, current_bands)
        self._active_bands = current_bands

        logger.debug("[%s] Wireless metrics collected", product_id)

    def _collect_band_metrics(self, product_id: str, wl_unit: str, band_info: Any) -> None:
        """Collect metrics for a single wireless band."""
        if band_info is None:
            return

        # Band info
        self._band_info.labels(product_id=product_id, wl_unit=wl_unit).info(
            {
                "wl_ssid": getattr(band_info, "ssid", ""),
                "wl_mac": getattr(band_info, "mac", ""),
            }
        )

        # SSID hidden
        hidden = getattr(band_info, "hidde_ssid", False)
        self._ssid_hidden.labels(product_id=product_id, wl_unit=wl_unit).set(1 if hidden else 0)

        # Band mode (one-hot)
        mode = getattr(band_info, "mode", None)
        if mode:
            self._set_onehot_enum(self._band_mode, product_id, wl_unit, mode, "wl_mode", "WifiMode", lambda e: e.name)

        # Auth mode (one-hot)
        auth_mode = getattr(band_info, "auth_mode", None)
        if auth_mode:
            self._set_onehot_enum(
                self._auth_mode, product_id, wl_unit, auth_mode, "wl_auth_mode", "WifiAuthMode", lambda e: e.value
            )

        # Crypto (one-hot)
        crypto = getattr(band_info, "crypto", None)
        if crypto:
            self._set_onehot_enum(
                self._crypto, product_id, wl_unit, crypto, "wl_crypto", "WifiCrypto", lambda e: e.value
            )

    def _set_onehot_enum(
        self,
        gauge: Gauge,
        product_id: str,
        wl_unit: str,
        current_value: Any,
        label_name: str,
        enum_name: str,
        get_label_value: Any,
    ) -> None:
        """Set one-hot encoding for an enum value."""
        enum_class = getattr(client_models, enum_name, None)
        if enum_class:
            for enum_val in enum_class:
                value = 1 if enum_val == current_value else 0
                gauge.labels(product_id=product_id, wl_unit=wl_unit, **{label_name: get_label_value(enum_val)}).set(
                    value
                )
        else:
            gauge.labels(product_id=product_id, wl_unit=wl_unit, **{label_name: str(current_value)}).set(1)

    def _remove_stale_band_metrics(
        self, product_id: str, previous_bands: set[str], current_bands: set[str]
    ) -> None:
        """Remove metrics for wireless bands that are no longer available.

        When wireless bands become unavailable (e.g., radio disabled, configuration
        change), their metrics would remain with stale values. This method removes
        those metrics to prevent confusion in dashboards and alerting.

        Uses prometheus_client's remove() method which is thread-safe and the proper API
        for removing specific label combinations.
        """
        stale_bands = previous_bands - current_bands
        for wl_unit in stale_bands:
            # Use prometheus_client's remove() API which is thread-safe
            # Remove band info metric
            try:
                self._band_info.remove(product_id, wl_unit)
            except KeyError:
                pass  # Label combination doesn't exist

            # Remove ssid_hidden metric
            try:
                self._ssid_hidden.remove(product_id, wl_unit)
            except KeyError:
                pass  # Label combination doesn't exist

            # Remove one-hot metrics (iterate over all enum values)
            for mode in client_models.WifiMode:
                try:
                    self._band_mode.remove(product_id, wl_unit, mode.name)
                except KeyError:
                    pass

            for auth_mode in client_models.WifiAuthMode:
                try:
                    self._auth_mode.remove(product_id, wl_unit, auth_mode.value)
                except KeyError:
                    pass

            for crypto in client_models.WifiCrypto:
                try:
                    self._crypto.remove(product_id, wl_unit, crypto.value)
                except KeyError:
                    pass

            logger.debug("[%s] Removed stale metrics for wireless band %s", product_id, wl_unit)

    def cleanup(self) -> None:
        """Clean up collector and reset state."""
        super().cleanup()
        self._active_bands.clear()
