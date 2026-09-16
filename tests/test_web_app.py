from pathlib import Path

from clickvos.web_app import build_demo
import gradio as gr


def test_gradio_demo_builds_with_expected_title() -> None:
    demo = build_demo(Path("configs/default.json"))
    assert isinstance(demo, gr.Blocks)
    config = demo.get_config_file()
    assert config["title"] == "ClickVOS Traffic"
    labels = {component.get("props", {}).get("label") for component in config["components"]}
    assert {"交通视频", "目标类别", "分割预览", "运行结果与异常"} <= labels
