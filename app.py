import streamlit as st
import pandas as pd
import io
import os
import tempfile
import hashlib
import plotly.express as px
from run import extract_run, export_amp, export_melt, export_cq

# -------------------- 页面配置 --------------------
st.set_page_config(page_title="qPCR LC96P Parser", layout="wide")

# -------------------- 工具函数 --------------------
def to_excel(df: pd.DataFrame) -> bytes:
    """将 DataFrame 转为 Excel 二进制流"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=True, sheet_name="quant")
        workbook = writer.book
        worksheet = writer.sheets["quant"]
        worksheet.set_column("A:ZZ", None, workbook.add_format({"num_format": "0.000"}))
    return output.getvalue()


def show_amp_table(amp_table, placeholder):
    """美化版扩增曲线绘图"""
    st.subheader("📈 Amplification Curves")

    # 将数据展开为长格式：Cycle、Well、Fluorescence
    df = amp_table.reset_index().melt(
        id_vars="index", var_name="Well", value_name="Fluorescence"
    )
    df.rename(columns={"index": "Cycle"}, inplace=True)

    # 折线图：每个孔一条曲线
    fig = px.line(
        df,
        x="Cycle",
        y="Fluorescence",
        color="Well",
        line_group="Well",
        hover_name="Well",
        title="Amplification Curve per Well",
    )

    # 美化样式
    fig.update_traces(line=dict(width=1.3), opacity=0.65)
    fig.update_layout(
        height=550,
        template="plotly_white",
        title=dict(x=0.5, xanchor="center"),
        xaxis_title="Cycle",
        yaxis_title="Fluorescence",
        legend_title="Well ID",
        margin=dict(l=40, r=20, t=60, b=40),
    )

    placeholder.plotly_chart(fig, use_container_width=True)


def show_melt_table(melt_table, placeholder):
    """美化版熔解曲线绘图"""
    st.subheader("🔥 Melt Curve")

    df = melt_table.reset_index().melt(
        id_vars="index", var_name="Well", value_name="Fluorescence"
    )
    df.rename(columns={"index": "Temperature"}, inplace=True)

    fig = px.line(
        df,
        x="Temperature",
        y="Fluorescence",
        color="Well",
        line_group="Well",
        hover_name="Well",
        title="Melt Curve per Well",
    )

    fig.update_traces(line=dict(width=1.3), opacity=0.6)
    fig.update_layout(
        height=550,
        template="plotly_white",
        title=dict(x=0.5, xanchor="center"),
        xaxis_title="Temperature (°C)",
        yaxis_title="Fluorescence",
        legend_title="Well ID",
        margin=dict(l=40, r=20, t=60, b=40),
    )

    placeholder.plotly_chart(fig, use_container_width=True)


def show_result_table(result_table, placeholder):
    """展示 Cq 结果表并提供下载"""
    st.subheader("📊 Quantification Results (Cq Table)")
    st.dataframe(result_table, use_container_width=True)

    excel_data = to_excel(result_table)
    st.download_button(
        label="💾 Download Excel file",
        data=excel_data,
        file_name="qPCR_results.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# -------------------- 主程序 --------------------
st.title("💡 qPCR LC96P File Parser")
st.write("上传 `.lc96p` 文件以解析并生成 Amplification、Melt、Cq 数据。")

uploaded_file = st.file_uploader("选择 LC96P 文件", type=["lc96p"])

if uploaded_file is not None:
    # 基于文件内容生成唯一 key（防止重复解析）
    file_bytes = uploaded_file.getvalue()
    file_key = hashlib.md5(file_bytes).hexdigest()

    # 写入临时文件
    with tempfile.NamedTemporaryFile(delete=False, suffix=".lc96p") as temp_file:
        temp_file.write(file_bytes)
        temp_file_path = temp_file.name

    # UI 占位符
    loading_placeholder = st.empty()
    amp_placeholder = st.empty()
    melt_placeholder = st.empty()
    cq_placeholder = st.empty()

    try:
        result_table = None

        if st.session_state.get("file_key") != file_key:
            try:
                with loading_placeholder.container():
                    with st.spinner("🔄 正在解析 LC96P 文件..."):
                        run = extract_run(temp_file_path)

                with loading_placeholder.container():
                    with st.spinner("📤 导出放大曲线数据 (amp table)..."):
                        amp_table = export_amp(run)
                        show_amp_table(amp_table, amp_placeholder)

                with loading_placeholder.container():
                    with st.spinner("📤 导出熔解曲线数据 (melt table)..."):
                        melt_table = export_melt(run)
                        show_melt_table(melt_table, melt_placeholder)

                with loading_placeholder.container():
                    with st.spinner("📤 导出定量结果 (Cq table)..."):
                        result_table = export_cq(run)
                        show_result_table(result_table, cq_placeholder)

            except Exception as e:
                st.error(f"❌ 解析 LC96P 文件时发生错误：{e}")
                st.stop()

            # 所有表生成成功后更新缓存
            if all(v is not None for v in [amp_table, melt_table, result_table]):
                st.session_state.file_key = file_key
                st.session_state.amp_table = amp_table
                st.session_state.melt_table = melt_table
                st.session_state.result_table = result_table
            else:
                st.warning("⚠️ 部分表格未成功生成，请检查输入文件。")
        else:
            # 文件未变化 → 直接展示缓存数据
            show_amp_table(st.session_state.amp_table, amp_placeholder)
            show_melt_table(st.session_state.melt_table, melt_placeholder)
            show_result_table(st.session_state.result_table, cq_placeholder)

    finally:
        try:
            os.remove(temp_file_path)
        except Exception:
            pass
