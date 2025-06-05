#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import io
import logging
import os
import subprocess
import sys
import tempfile

import pandas as pd
import numpy as np  # 使用 np.nan 替代 np.NaN

from rdmlpython.rdml import Rdml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    force=True,
)


def reshape_result(result_table):
    # 确保没有出现 np.NaN，而是 np.nan
    df = result_table.loc[
        :, ["well", "Cq (mean eff) - no plateau - stat efficiency"]
    ]

    df_plate = (
        df.join(df["well"].str.extract(r"(?P<letter>[A-Z])(?P<digit>\d+)"))
        .assign(digit=lambda x: x.digit.astype(int))
        .pivot(
            index="letter",
            columns="digit",
            values="Cq (mean eff) - no plateau - stat efficiency",
        )
    )

    # 如果 df_plate 是空的或无效的，抛出错误
    if df_plate.empty:
        logging.error("Resulting df_plate is empty!")
        sys.exit(1)
    
    return df_plate


def extract_run(input_file):
    # Run LinRegPCR from commandline
    cli_linRegPCR = Rdml(input_file)
    if cli_linRegPCR.version() == "1.0":
        cli_linRegPCR.migrate_version_1_0_to_1_1()
    cli_expList = cli_linRegPCR.experiments()
    if len(cli_expList) < 1:
        logging.error("No experiments found!")
        sys.exit(0)
    cli_exp = cli_expList[0]
    logging.info(
        'No experiment given (use option -e). Using "'
        + cli_expList[0]["id"]
        + '"'
    )

    cli_runList = cli_exp.runs()
    if len(cli_runList) < 1:
        logging.error("No runs found!")
        sys.exit(0)
    logging.info(
        'No run given (use option -r). Using "' + cli_runList[0]["id"] + '"'
    )
    run = cli_runList[0]
    return run


def export_amp(run):
    # dMode: amp for amplification data, melt for meltcurve data
    # is str
    logging.info("Exporting amplification data...")
    amp_table = (
        pd.read_csv(io.StringIO(run.export_table("amp")), sep="\t")
        .set_index("Well")
        .iloc[:, 6:]
    ).T
    amp_table.index = amp_table.index.astype(int)
    return amp_table


def export_melt(run):
    logging.info("Exporting meltcurve data...")
    melt_table = (
        pd.read_csv(io.StringIO(run.export_table("melt")), sep="\t")
        .set_index("Well")
        .iloc[:, 6:]
    ).T
    melt_table.index = melt_table.index.astype(float)
    return melt_table


def export_cq(run):
    logging.info("Running LinRegPCR...")
    cli_result = run.linRegPCR(
        pcrEfficiencyExl=0.05,
        updateRDML=False,
        excludeNoPlateau=True,
        excludeEfficiency="mean",
        excludeInstableBaseline=True,
        commaConv=False,
        ignoreExclusion=False,
        saveRaw=False,
        saveBaslineCorr=False,
        saveResultsList=False,
        saveResultsCSV=True,
        timeRun=True,
        verbose=False,
    )
    if "noRawData" in cli_result:
        logging.error(cli_result["noRawData"])

    result_table = reshape_result(
        pd.read_csv(io.StringIO(cli_result["resultsCSV"]), sep="\t")
    )

    return result_table


# create 3 files for each input
def convert_file(input_file, rdml_file, excel_file):
    with tempfile.NamedTemporaryFile(
        mode="w+", suffix=".tsv", delete=True
    ) as tsv_temp:
        tsv_file = tsv_temp.name
        script_path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)),
            "rdmlpython",
            "rdml.py",
        )

        # 打印路径和环境，确保正确调用
        logging.info(f"脚本路径: {script_path}")
        logging.info(f"当前 Python 解释器: {sys.executable}")

        subprocess.call(
            [
                sys.executable,
                script_path,
                "-lrp",
                input_file,
                "--pcrEfficiencyExl",
                "0.05",
                "--excludeNoPlateau",
                "--excludeEfficiency",
                "mean",
                "--timeRun",
                "-o",
                rdml_file,
                "--saveResults",
                tsv_file,
            ]
        )

        df = pd.read_csv(tsv_file, sep="\t").loc[
            :, ["well", "Cq (mean eff) - no plateau - stat efficiency"]
        ]

    df_plate = (
        df.join(df["well"].str.extract(r"(?P<letter>[A-Z])(?P<digit>\d+)"))
        .assign(digit=lambda x: x.digit.astype(int))
        .pivot(
            index="letter",
            columns="digit",
            values="Cq (mean eff) - no plateau - stat efficiency",
        )
    )

    # 如果 df_plate 是空的或无效的，抛出错误
    if df_plate.empty:
        logging.error("Resulting df_plate is empty!")
        sys.exit(1)

    df_plate.to_excel(excel_file, sheet_name="quant", engine="xlsxwriter")
    return df_plate


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: run.py input_file.lc96p")
    
    input_file = sys.argv[1]
    
    # 确保返回的对象有效
    run = extract_run(input_file)
    
    # 检查所有表格的有效性
    amp_table = export_amp(run)
    melt_table = export_melt(run)
    result_table = export_cq(run)
    
    # 打印表格内容进行检查
    logging.info(f"Amplification Table: {amp_table}")
    logging.info(f"Melt Curve Table: {melt_table}")
    logging.info(f"Result Table: {result_table}")
    
    rdml_file = input_file.rsplit(".", 1)[0] + ".rdml"
    excel_file = input_file.rsplit(".", 1)[0] + ".xlsx"
    
    convert_file(input_file, rdml_file, excel_file)
