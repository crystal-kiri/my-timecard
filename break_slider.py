import os
import streamlit.components.v1 as components

_COMPONENT_DIR = os.path.join(os.path.dirname(__file__), "components", "break_slider")

_break_slider = components.declare_component(
    "break_slider",
    path=_COMPONENT_DIR,
)

def break_slider(
    label="今日の休憩時間",
    min_value=0,
    max_value=60,
    step=5,
    value=60,
    text_color="#454444",
    key=None,
):
    result = _break_slider(
        label=label,
        min=min_value,
        max=max_value,
        step=step,
        value=value,
        textColor=text_color,
        default=value,
        key=key,
    )
    return value if result is None else int(result)
