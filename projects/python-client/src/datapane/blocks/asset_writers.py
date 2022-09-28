"""
# TODO - optimise import handling here
"""
from __future__ import annotations

import json
import pickle
import typing as t
from collections import namedtuple
from contextlib import suppress
from io import TextIOWrapper
from pathlib import Path

import pandas as pd
from altair.utils import SchemaBase
from multimethod import multimethod
from packaging import version as v
from packaging.specifiers import SpecifierSet
from pandas.io.formats.style import Styler

from datapane.client import DPClientError, log
from datapane.common.df_processor import to_df
from datapane.common import ArrowFormat

from .base import DataBlock


AssetMeta = namedtuple("AssetMeta", "ext mime")
TABLE_CELLS_LIMIT: int = 500
# NOTE - need to update this and keep in sync with JS
BOKEH_V_SPECIFIER = SpecifierSet("~=2.4.2")
PLOTLY_V_SPECIFIER = SpecifierSet(">=4.0.0")
FOLIUM_V_SPECIFIER = SpecifierSet(">=0.12.0")


def _check_version(name: str, _v: v.Version, ss: SpecifierSet):
    if _v not in ss:
        log.warning(
            f"{name} version {_v} is not supported, these plots may not display correctly, please install version {ss}"
        )


class DPTextIOWrapper(TextIOWrapper):
    """Custom IO Wrapper that detaches before closing - see https://bugs.python.org/issue21363"""

    def __init__(self, f, *a, **kw):
        super().__init__(f, encoding="utf-8", *a, **kw)

    def __del__(self):
        # don't close the underlying stream
        self.flush()
        with suppress(Exception):
            self.detach()


class AssetWriterP(t.Protocol):
    """Implement these in any class to support asset writing
    for a particular AssetBlock"""

    def get_meta(self, x: t.Any) -> AssetMeta:
        ...

    def write_file(self, x: t.Any, f: t.IO) -> None:
        ...


class AttachmentWriter:
    # pickle
    @multimethod
    def get_meta(self, x: t.Any) -> AssetMeta:
        return AssetMeta(ext=".pkl", mime="application/vnd.pickle+binary")

    @multimethod
    def get_meta(self, x: str) -> AssetMeta:
        return AssetMeta(ext=".json", mime="application/json")

    @multimethod
    def write_file(self, x: t.Any, f) -> None:
        pickle.dump(x, f)

    @multimethod
    def write_file(self, x: str, f) -> None:
        out: str = json.dumps(json.loads(x))
        f.write(out.encode())


class DataTableWriter:
    @multimethod
    def get_metaa(self, x: pd.DataFrame) -> AssetMeta:
        return AssetMeta(mime=ArrowFormat.content_type, ext=ArrowFormat.ext)

    @multimethod
    def write_file(self, x: pd.DataFrame, f) -> None:
        # create a copy of the df to process
        df = to_df(x)
        if df.size == 0:
            raise DPClientError("Empty DataFrame provided")
        # process_df called in Arrow.save_file
        ArrowFormat.save_file(f, df)


class HTMLTableWriter:
    @multimethod
    def get_meta(self, x: t.Union[pd.DataFrame, Styler]) -> AssetMeta:
        return AssetMeta(mime="application/vnd.datapane.table+html", ext=".tbl.html")

    @multimethod
    def write_file(self, x: pd.DataFrame, f) -> None:
        self._check(x)
        out = x.to_html().encode()
        f.write(out)

    @multimethod
    def write_file(self, x: Styler, f) -> None:
        self._check(x.data)
        out = x.render().encode()
        f.write(out)

    def _check(self, df: pd.DataFrame) -> None:
        n_cells = df.shape[0] * df.shape[1]
        if n_cells > TABLE_CELLS_LIMIT:
            raise ValueError(
                f"Dataframe over limit of {TABLE_CELLS_LIMIT} cells for dp.Table, consider using dp.DataTable instead or aggregating the df first"
            )


# Optional Plotting library import handling
# Matplotlib
try:
    from matplotlib.figure import Axes, Figure
    from numpy import ndarray

    HAVE_MATPLOTLIB = True
except ImportError:
    log.debug("No matplotlib found")
    HAVE_MATPLOTLIB = False

# Folium
try:
    import folium
    from folium import Map

    _check_version("Folium", v.Version(folium.__version__), FOLIUM_V_SPECIFIER)
    HAVE_FOLIUM = True
except ImportError:
    HAVE_FOLIUM = False
    log.debug("No folium found")

# Plotapi
try:
    from plotapi import Visualisation

    HAVE_PLOTAPI = True
except ImportError:
    HAVE_PLOTAPI = False
    log.debug("No plotapi found")

# Bokeh
try:
    import bokeh
    from bokeh.layouts import LayoutDOM as BLayout
    from bokeh.plotting.figure import Figure as BFigure

    _check_version("Bokeh", v.Version(bokeh.__version__), BOKEH_V_SPECIFIER)
    HAVE_BOKEH = True
except ImportError:
    HAVE_BOKEH = False
    log.debug("No Bokeh Found")

# Plotly
try:
    import plotly
    from plotly.graph_objects import Figure as PFigure

    _check_version("Plotly", v.Version(plotly.__version__), PLOTLY_V_SPECIFIER)
    HAVE_PLOTLY = True
except ImportError:
    HAVE_PLOTLY = False
    log.debug("No Plotly Found")


class PlotWriter:
    obj_type: t.Any

    # Altair (always installed)
    @multimethod
    def get_meta(self, x: SchemaBase) -> AssetMeta:
        return AssetMeta(mime="application/vnd.vegalite.v4+json", ext=".vl.json")

    @multimethod
    def write_file(self, x: SchemaBase, f) -> None:
        json.dump(x.to_dict(), DPTextIOWrapper(f))

    if HAVE_FOLIUM:

        @multimethod
        def get_meta(self, x: Map) -> AssetMeta:
            return AssetMeta(mime="application/vnd.folium+html", ext=".fl.html")

        @multimethod
        def write_file(self, x: Map, f) -> None:
            html: str = x.get_root().render()
            f.write(html.encode())

    if HAVE_PLOTAPI:

        @multimethod
        def get_meta(self, x: Visualisation) -> AssetMeta:
            return AssetMeta(mime="application/vnd.plotapi+html", ext=".plotapi.html")

        @multimethod
        def write_file(self, x: Visualisation, f) -> None:
            html: str = x.to_string()
            f.write(html.encode())

    if HAVE_BOKEH:

        @multimethod
        def get_meta(self, x: t.Union[BFigure, BLayout]) -> AssetMeta:
            return AssetMeta(mime="application/vnd.bokeh.show+json", ext=".bokeh.json")

        @multimethod
        def write_file(self, x: t.Union[BFigure, BLayout], f: t.IO):
            from bokeh.embed import json_item

            json.dump(json_item(x), DPTextIOWrapper(f))

    if HAVE_PLOTLY:

        @multimethod
        def get_meta(self, x: PFigure) -> AssetMeta:
            return AssetMeta(mime="application/vnd.plotly.v1+json", ext=".pl.json")

        @multimethod
        def write_file(self, x: PFigure, f):
            json.dump(x.to_json(), DPTextIOWrapper(f))

    if HAVE_MATPLOTLIB:

        @multimethod
        def get_meta(self, x: t.Union[Axes, Figure, ndarray]) -> AssetMeta:
            return AssetMeta(mime="image/svg+xml", ext=".svg")

        @multimethod
        def write_file(self, x: Figure, f) -> None:
            x.savefig(DPTextIOWrapper(f))

        @multimethod
        def write_file(self, x: Axes, f) -> None:
            self.write_file(x.get_figure())

        @multimethod
        def write_file(self, x: ndarray, f) -> None:
            fig = x.flatten()[0].get_figure()
            self.write_file(fig)


#################################################################
# Block wrapping
def get_blocks():
    # HACK - around recursive imports - could move out into own module
    from datapane import blocks as b
    return b

@multimethod
def convert_to_block(x: object) -> DataBlock:
    raise DPClientError(
        f"{type(x)} not supported directly, please pass into in the appropriate dp object (including dp.Attachment if want to upload as a pickle)"
    )


@multimethod
def convert_to_block(x: t.Any) -> DataBlock:
    return get_blocks().Attachment(x)


@multimethod
def convert_to_block(x: str) -> DataBlock:
    return get_blocks().Text(x)


@multimethod
def convert_to_block(x: Path) -> DataBlock:
    return get_blocks().Attachment(file=x)


@multimethod
def convert_to_block(x: pd.DataFrame) -> DataBlock:
    n_cells = x.shape[0] * x.shape[1]
    return get_blocks().Table(x) if n_cells <= TABLE_CELLS_LIMIT else b.DataTable(x)


# Plots
@multimethod
def convert_to_block(x: SchemaBase) -> DataBlock:
    return get_blocks().Plot(x)


if HAVE_BOKEH:

    @multimethod
    def convert_to_block(x: t.Union[BFigure, BLayout]) -> DataBlock:
        return get_blocks().Plot(x)


if HAVE_PLOTLY:

    @multimethod
    def convert_to_block(x: PFigure) -> DataBlock:
        return get_blocks().Plot(x)


if HAVE_FOLIUM:

    @multimethod
    def convert_to_block(x: Map) -> DataBlock:
        return get_blocks().Plot(x)


if HAVE_PLOTAPI:

    @multimethod
    def convert_to_block(x: Visualisation) -> DataBlock:
        return get_blocks().Plot(x)


if HAVE_MATPLOTLIB:

    @multimethod
    def convert_to_block(x: t.Union[Figure, Axes, ndarray]) -> DataBlock:
        return get_blocks().Plot(x)
