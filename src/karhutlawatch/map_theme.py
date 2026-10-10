"""Keep Python-rendered map overlays in sync with browser theme changes."""

import streamlit as st


_THEME_SYNC = st.components.v2.component(
    "map_theme_sync",
    js="""
export default function ({ data, parentElement, setTriggerValue }) {
    // Streamlit calls this renderer again when its active theme changes.
    const host = parentElement.host ?? parentElement;
    const theme = getComputedStyle(host).colorScheme;
    if ((theme === "light" || theme === "dark") && theme !== data) {
        setTriggerValue("theme_changed", theme);
    }
}
""",
)


def sync_map_theme() -> None:
    """Request a rerun only when the browser and Python themes differ."""
    _THEME_SYNC(
        key="map_theme_sync",
        data=st.context.theme.type,
        on_theme_changed_change=lambda: None,
    )
