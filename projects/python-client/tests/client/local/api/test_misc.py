"""Tests for the API that can run locally (due to design or mocked out)"""
from pathlib import Path

import pytest
from glom import glom

import datapane as dp
import datapane.blocks.asset
import datapane.blocks.layout
import datapane.blocks.text
from datapane.client import api
from datapane.client.utils import DPClientError

from ....client.e2e.common import gen_df, gen_plot
from .test_reports import element_to_str


def test_params_loading(datadir: Path):
    """Test that the API allows loading params from the datapane file"""
    config_fn = datadir / "datapane.yaml"
    initial_vals = dict(p1="a", p3=3)

    assert len(dp.Params) == 0

    # load some values
    api._reset_runtime(initial_vals)
    assert len(dp.Params) == 2
    assert dp.Params["p1"] == initial_vals["p1"]

    # clear and load again
    api._reset_runtime({})
    assert len(dp.Params) == 0
    api._reset_runtime(initial_vals)

    # load from file
    dp.Params.load_defaults(config_fn=config_fn)
    # ensure values are merged
    assert len(dp.Params) == 3
    assert dp.Params["p1"] == "hello"
    assert dp.Params["p2"] == 4
    assert dp.Params["p3"] == initial_vals["p3"]


def test_markdown_format(datadir: Path):
    text = """
# My wicked markdown

{{plot}}

As above we do ...

{{select}}

Here's the dataset used...

{{}}
"""

    table_asset = gen_df()
    plot_asset = datapane.blocks.asset.Plot(data=gen_plot(), caption="Plot Asset")
    select_asset = datapane.blocks.layout.Select(datapane.blocks.inline_text.Text("Hello"), "World")

    # missing context
    with pytest.raises(DPClientError):
        datapane.blocks.inline_text.Text(text).format(table_asset, plot=plot_asset, select1=select_asset)
    with pytest.raises(DPClientError):
        datapane.blocks.inline_text.Text(text).format(plot=plot_asset, select=select_asset)

    # test string
    group = datapane.blocks.inline_text.Text(text).format(table_asset, plot=plot_asset, select=select_asset)
    assert isinstance(group, datapane.blocks.layout.Group)
    assert glom(group, ("blocks", ["_tag"])) == ["Text", "Plot", "Text", "Select", "Text", "Table"]

    # test file
    group = datapane.blocks.inline_text.Text(file=datadir / "report.md").format(table_asset, plot=plot_asset, select=select_asset)
    assert isinstance(group, datapane.blocks.layout.Group)
    assert glom(group, ("blocks", ["_tag"])) == ["Text", "Plot", "Text", "Select", "Text", "Table"]
    assert "file-input" in element_to_str(group)
    assert "file-input" in glom(group, "blocks.0.content")
