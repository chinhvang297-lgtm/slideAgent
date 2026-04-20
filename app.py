"""PPTAgent Streamlit Web UI."""

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import streamlit as st

st.set_page_config(
    page_title="PPTAgent - AI Presentation Generator",
    page_icon="📊",
    layout="centered",
)

st.title("PPTAgent")
st.caption("Intelligent Presentation Auto-Generation System")

# Sidebar settings
with st.sidebar:
    st.header("Settings")
    model = st.selectbox(
        "Qwen Model",
        ["qwen-plus", "qwen-turbo", "qwen-max"],
        index=0,
    )
    api_key_input = st.text_input(
        "DashScope API Key",
        value=os.getenv("DASHSCOPE_API_KEY", ""),
        type="password",
        help="Leave empty to use DASHSCOPE_API_KEY env var",
    )
    max_slides = st.slider("Max Slides", min_value=5, max_value=30, value=15)

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("Template")
    template_file = st.file_uploader(
        "Upload PPTX template",
        type=["pptx"],
        key="template",
    )

with col2:
    st.subheader("Content")
    content_file = st.file_uploader(
        "Upload content file",
        type=["pdf", "md", "txt"],
        key="content",
        help="Supports PDF, Markdown (.md), and plain text (.txt)",
    )

st.divider()

generate_btn = st.button(
    "Generate Presentation",
    type="primary",
    disabled=(template_file is None or content_file is None),
    use_container_width=True,
)

if generate_btn:
    if not api_key_input and not os.getenv("DASHSCOPE_API_KEY"):
        st.error("Please provide a DashScope API key in the sidebar or set DASHSCOPE_API_KEY environment variable.")
        st.stop()

    # Override API key if provided in UI
    if api_key_input:
        os.environ["DASHSCOPE_API_KEY"] = api_key_input

    progress_bar = st.progress(0, text="Initializing...")
    status = st.empty()
    log_container = st.expander("Progress log", expanded=True)
    log_lines: list[str] = []

    def update_log(msg: str) -> None:
        log_lines.append(msg)
        with log_container:
            st.text("\n".join(log_lines[-20:]))

    stage_progress = {"1": 0.15, "2": 0.30, "3": 0.80, "4": 0.95}
    current_progress = [0.0]

    def progress_callback(msg: str) -> None:
        update_log(msg)
        for stage, pct in stage_progress.items():
            if f"Stage {stage}" in msg:
                current_progress[0] = pct
                progress_bar.progress(pct, text=msg)
                return
        current_progress[0] = min(current_progress[0] + 0.02, 0.94)
        progress_bar.progress(current_progress[0], text=msg)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Save uploaded files
        template_path = tmpdir / template_file.name
        template_path.write_bytes(template_file.read())

        content_path = tmpdir / content_file.name
        content_path.write_bytes(content_file.read())

        output_path = tmpdir / f"{content_path.stem}_generated.pptx"

        # Override config settings
        from ppt_agent.config import config
        config.MODEL = model
        config.MAX_SLIDES = max_slides
        config.OUTPUT_DIR = tmpdir / "output"
        config.TEMP_DIR = tmpdir / "temp"
        config.ensure_dirs()

        try:
            from ppt_agent.pipeline import run_pipeline

            status.info("Running pipeline...")
            result = run_pipeline(
                template_path=template_path,
                content_path=content_path,
                output_path=output_path,
                progress_callback=progress_callback,
            )
        except Exception as e:
            progress_bar.progress(1.0, text="Failed")
            st.error(f"Pipeline error: {e}")
            st.stop()

        progress_bar.progress(1.0, text="Done!")

        if result.success:
            status.success(result.summary())

            # Validation warnings
            if result.validation_report and result.validation_report.issues:
                report = result.validation_report
                st.warning(
                    f"Auto-fixed {report.warning_count} validation warnings. "
                    "Review the output for any remaining issues."
                )

            # Download button
            output_bytes = output_path.read_bytes()
            st.download_button(
                label="Download Presentation (.pptx)",
                data=output_bytes,
                file_name=f"{content_path.stem}_generated.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                type="primary",
                use_container_width=True,
            )
        else:
            status.error(f"Generation failed: {result.error}")

st.divider()
st.caption(
    "PPTAgent uses Claude AI to intelligently transform your content into a polished presentation. "
    "Upload a PPTX template and a PDF/Markdown document to get started."
)
