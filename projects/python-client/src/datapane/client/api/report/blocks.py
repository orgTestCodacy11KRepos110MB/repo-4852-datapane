"""
Datapane Blocks API

Describes the collection of `Block` objects that can be combined together to make a `datapane.client.api.report.core.Report`.
"""
from __future__ import annotations

import dataclasses as dc
import enum
import re
import secrets
import typing as t
from abc import ABC
from base64 import b64encode
from collections import deque
from functools import reduce
from pathlib import Path

import pandas as pd
from dominate.dom_tag import dom_tag
from glom import glom
from lxml import etree
from lxml.builder import ElementMaker
from lxml.etree import Element
from pandas.io.formats.style import Styler

from datapane.client import DPError
from datapane.common import MIME, PKL_MIMETYPE, NPath, SSDict, guess_type, log, utf_read_text
from datapane.common.report import conv_attrib, get_embed_url, is_valid_id, mk_attribs

from ..common import DPTmpFile
from ..dp_object import save_df

if t.TYPE_CHECKING:
    from .processors import BuilderState, FileStore


E = ElementMaker()  # XML Tag Factory

# only these types will be documented by default
__all__ = [
    "Attachment",
    "BaseElement",
    "Group",
    "Select",
    "Toggle",
    "SelectType",
    "Empty",
    "Interactive",
    "Table",
    "DataTable",
    "DataBlock",
    "Divider",
    "Plot",
    "BigNumber",
    "Text",
    "Code",
    "Embed",
    "HTML",
    "Media",
    "Formula",
    "Media",
    "View",
]

__pdoc__ = {
    "Media.caption": False,
    "Media.file": False,
    "Attachment.caption": False,
    "Attachment.file": False,
    "Plot.file": False,
    "DataTable.file": False,
}


BlockId = str
Block = t.Union["Group", "Select", "DataBlock", "Empty", "Interactive"]
BlockOrPrimitive = t.Union[Block, t.Any]  # TODO - expand
BlockList = t.List[Block]


class BlockListIterator:
    """
    Wrapper around the default list iterator that supports depth-first recursion for list-of-lists
    """

    # TODO - needs testing
    def __init__(self, _iter):
        # manually mock the stack of list iterators
        self.nested: list = [_iter]

    def __next__(self) -> Block:
        try:
            b: Block = self.nested[-1].__next__()
        except StopIteration as e:
            try:
                self.nested.pop()
                b = self.__next__()
            except IndexError:
                raise e

        if isinstance(b, LayoutBlock):
            # add new iter for next call
            self.nested.append(b.blocks.__iter__())

        return b

    def __iter__(self):
        return self


class View:
    blocks: BlockList
    fragment: bool = False

    def __init__(
        self,
        *arg_blocks: BlockOrPrimitive,
        blocks: t.List[BlockOrPrimitive] = None,
    ):
        blocks = blocks or list(arg_blocks)
        if len(blocks) == 0:
            raise DPError("Can't create View with 0 objects")
        self.blocks = [wrap_block(b) for b in blocks]

    @classmethod
    def empty(cls) -> View:
        return View(blocks=[Empty()])

    # TODO - add these to BaseElement...
    # TODO - should this be an Element type (similar to Page??)#
    # TODO - add special X/DP wrapper?
    def __add__(self, other: View) -> View:
        x = self.blocks + other.blocks
        return View(blocks=x)

    def __and__(self, other: View) -> View:
        x = self.blocks + other.blocks
        return View(blocks=x)

    def __or__(self, other: View) -> View:
        x = Group(blocks=self.blocks) if len(self.blocks) > 1 else self.blocks[0]
        y = Group(blocks=other.blocks) if len(other.blocks) > 1 else other.blocks[0]
        z = Group(x, y, columns=2)
        return View(z)

    def __iter__(self):
        return BlockListIterator(self.blocks.__iter__())

    def accept(self, visitor):
        dispatch_to: str = visitor.dispatch_to
        f = getattr(self, dispatch_to)
        return f(visitor)

    def _to_xml(self, s: BuilderState) -> t.Tuple[Element, FileStore]:
        # kick-off the recursive pass of the node-tree
        _s = reduce(lambda _s, b: b._to_xml(_s), self.blocks, s)

        # create top-level structure
        view_doc: Element = E.View(
            # E.Internal(),
            *_s.elements,
            **mk_attribs(version="1", fragment=self.fragment),
        )

        return view_doc, _s.store


class BaseElement(ABC):
    """Base Block class - subclassed by all Block types

    ..note:: The class is not used directly.
    """

    _attributes: t.Dict[str, str]
    _tag: str
    _block_name: str
    name: t.Optional[BlockId] = None

    def __init__(self, name: BlockId = None, **kwargs):
        """
        Args:
            name: A unique name to reference the block, used when referencing blocks via the report editor and when embedding
        """
        self._block_name = self._tag.lower()
        self._attributes = dict()
        self._add_attributes(**kwargs)
        self._set_name(name)

        self._truncate_strings(kwargs, "caption", 512)
        self._truncate_strings(kwargs, "label", 256)

    def _truncate_strings(self, kwargs: dict, key: str, max_length: int):
        if key in kwargs:
            x: str = kwargs[key]
            if x and len(x) > max_length:
                kwargs[key] = f"{x[:max_length-3]}..."
                log.warning(f"{key} currently '{x}'")
                log.warning(f"{key} must be less than {max_length} characters, truncating")
                # raise DPError(f"{key} must be less than {max_length} characters, '{x}'")

    def _set_name(self, name: BlockId = None):
        if name:
            # validate name
            if not is_valid_id(name):
                raise DPError(f"Invalid name '{name}' for block")
            self.name = name
            self._attributes.update(name=name)

    def _add_attributes(self, **kwargs):
        self._attributes.update(mk_attribs(**kwargs))

    def _to_xml(self, s: BuilderState) -> BuilderState:
        """Base implementation - just created an empty tag including all the intitial attributes"""
        _E = getattr(E, self._tag)
        return s.add_element(self, _E(**self._attributes))


class SelectType(enum.Enum):
    DROPDOWN = "dropdown"
    TABS = "tabs"


def wrap_block(b: BlockOrPrimitive) -> Block:
    # if isinstance(b, Page):
    #     raise DPError("Page objects can only be at the top-level")
    if not isinstance(b, BaseElement):
        # import here as a very slow module due to nested imports
        from ..files import convert

        return convert(b)
    return t.cast(Block, b)


class LayoutBlock(BaseElement):
    """
    Abstract Block that supports nested blocks
     - represents a subtree in the document
    """

    blocks: BlockList = None

    def __init__(self, *arg_blocks: BlockOrPrimitive, blocks: t.List[BlockOrPrimitive] = None, **kwargs):
        self.blocks = blocks or list(arg_blocks)
        # NOTE - removed to support empty groups
        # if len(self.blocks) == 0:
        #     raise DPError("Can't create container with 0 objects")
        self.blocks = [wrap_block(b) for b in self.blocks]

        super().__init__(**kwargs)

    def __iter__(self):
        return BlockListIterator(self.blocks.__iter__())

    def _to_xml(self, s: BuilderState) -> BuilderState:
        """
        Recurse into the elements and pull them out
        NOTE - this works depth-first to create all sub-elements before the current,
        resulting in simpler implementation
        NOTE - this results in a document-order created list of attachments for AssetBlocks,
        as they are leaf nodes
        """
        # TODO - move out into accept on the node??
        _s1: BuilderState = dc.replace(s, elements=[])
        _s2: BuilderState = reduce(lambda _s, x: x._to_xml(_s), self.blocks, _s1)
        _s3: BuilderState = dc.replace(_s2, elements=s.elements)

        # build the element
        _E = getattr(E, self._tag)
        _s3.add_element(self, _E(*_s2.elements, **self._attributes))
        return _s3


# class Page(LayoutBlock):
#     """
#     All `datapane.client.api.report.core.Report`s consist of a list of Pages.
#     A Page itself is a Block, but is only allowed at the top-level and cannot be nested.
#
#     Page objects take a list of blocks which make up the Page.
#
#     ..note:: You can pass ordinary Blocks to a page, e.g. Plots or DataTables.
#       Additionally, if a Python object is passed, e.g. a Dataframe, Datapane will attempt to convert it automatically.
#     """
#
#     # NOTE - technically a higher-level layoutblock but we keep here to maximise reuse
#     _tag = "Page"
#
#     def __init__(
#         self,
#         *arg_blocks: BlockOrPrimitive,
#         blocks: t.List[BlockOrPrimitive] = None,
#         title: str = None,
#         name: BlockId = None,
#     ):
#         """
#         Args:
#             *arg_blocks: Blocks to add to Page
#             blocks: Allows providing the report blocks as a single list
#             title: The page title (optional)
#             name: A unique id for the Page to aid querying (optional)
#
#         ..tip:: Page can be passed using either arg parameters or the `blocks` kwarg, e.g.
#           `dp.Page(group, select)` or `dp.Group(blocks=[group, select])`
#         """
#         super().__init__(*arg_blocks, blocks=blocks, label=title, name=name)
#         # error checking
#         if len(self.blocks) < 1:
#             raise DPError("Can't create Page with no objects")
#         if any(isinstance(b, Page) for b in self.blocks):
#             raise DPError("Page objects can only be at the top-level")


class Select(LayoutBlock):
    """
    Selects act as a container that holds a list of nested Blocks objects, such
    as Tables, Plots, etc.. - but only one may be __visible__, or "selected", at once.

    The user can choose which nested object to view dynamically using either tabs or a dropdown.

    ..note:: Select expects a list of Blocks, e.g. a Plot or Table, but also including Select or Groups themselves,
      but if a Python object is passed, e.g. a Dataframe, Datapane will attempt to convert it automatically.

    """

    _tag = "Select"

    def __init__(
        self,
        *arg_blocks: BlockOrPrimitive,
        blocks: t.List[BlockOrPrimitive] = None,
        type: t.Optional[SelectType] = None,
        name: BlockId = None,
        label: str = None,
        title: str = None,
    ):
        """
        Args:
            *arg_blocks: Page to add to report
            blocks: Allows providing the report blocks as a single list
            type: An instance of SelectType that indicates if the select should use tabs or a dropdown
            name: A unique id for the blocks to aid querying (optional)
            label: A label used when displaying the block (optional)

        ..tip:: Select can be passed using either arg parameters or the `blocks` kwarg, e.g.
          `dp.Select(table, plot, type=dp.SelectType.TABS)` or `dp.Group(blocks=[table, plot])`
        """
        _type = glom(type, "value", default=None)
        label = label or title
        super().__init__(*arg_blocks, blocks=blocks, name=name, label=label, type=_type)
        if len(self.blocks) < 2:
            raise DPError("Can't create Select with less than 2 objects")


class Group(LayoutBlock):
    """
    Groups act as a container that holds a list of nested Blocks objects, such
    as Tables, Plots, etc.. - they may even hold Group themselves recursively.

    Group are used to provide a grouping for blocks can have layout options applied to them

    ..note:: Group expects a list of Blocks, e.g. a Plot or Table, but also including Select or Groups themselves,
      but if a Python object is passed, e.g. a Dataframe, Datapane will attempt to convert it automatically.
    """

    _tag = "Group"

    def __init__(
        self,
        *arg_blocks: BlockOrPrimitive,
        blocks: t.List[BlockOrPrimitive] = None,
        name: BlockId = None,
        label: str = None,
        columns: int = 1,
    ):
        """
        Args:
            *arg_blocks: Group to add to report
            blocks: Allows providing the report blocks as a single list
            name: A unique id for the blocks to aid querying (optional)
            label: A label used when displaying the block (optional)
            columns: Display the contained blocks, e.g. Plots, using _n_ columns (default = 1), setting to 0 auto-wraps the columns

        ..tip:: Group can be passed using either arg parameters or the `blocks` kwarg, e.g.
          `dp.Group(plot, table, columns=2)` or `dp.Group(blocks=[plot, table], columns=2)`
        """

        # columns = columns or len(self.blocks)
        super().__init__(*arg_blocks, blocks=blocks, name=name, label=label, columns=columns)


class Toggle(LayoutBlock):
    """
    Toggles act as a container that holds a list of nested Block objects, whose visbility can be toggled on or off by the report viewer
    """

    _tag = "Toggle"

    def __init__(
        self,
        *arg_blocks: BlockOrPrimitive,
        blocks: t.List[BlockOrPrimitive] = None,
        name: BlockId = None,
        label: str = None,
    ):
        """
        Args:
            *arg_blocks: Group to add to report
            blocks: Allows providing the report blocks as a single list
            name: A unique id for the blocks to aid querying (optional)
            label: A label used when displaying the block (optional)
        """
        super().__init__(*arg_blocks, blocks=blocks, name=name, label=label)
        self._wrap_blocks()

    def _wrap_blocks(self) -> None:
        """Wrap the list of blocks in a top-level block element if needed"""
        if len(self.blocks) > 1:
            # only wrap if not all blocks are a Group object
            self.blocks = [Group(blocks=self.blocks)]


################################################################################
# Low-level blocks
class Empty(BaseElement):
    """
    An empty block that can be patched later

    Args:
        name: A unique name for the block to reference when updating the report
    """

    _tag = "Empty"

    def __init__(self, name: BlockId = None):
        if name is None:
            name = f"id-{secrets.token_urlsafe(8)}"
        super().__init__(name=name)


class Controls:
    title: str = "Test Controls panel"

    def _to_xml(self) -> etree.Element:
        # TODO - create the params here...
        return E.Controls(title=self.title)


class Interactive(BaseElement):
    """
    An interactive block that allows for dynamic views based on functions
    """

    _tag = "Interactive"
    controls: Controls

    def __init__(self, function: t.Callable, target: BlockId, controls: Controls, name: BlockId = None):
        self.controls = controls
        # basic attributes
        super().__init__(name=name, target=target, title="Test Interactive Block", trigger="submit", swap="replace")

    def _to_xml(self, s: BuilderState) -> BuilderState:
        # add additional attributes
        self._attributes.update(
            function="foo",
        )

        e = E.Interactive(self.controls._to_xml(), **self._attributes)
        return s.add_element(self, e)


class DataBlock(BaseElement):
    """Abstract block that represents a leaf-node in the tree, e.g. a Plot or Table

    ..note:: This class is not used directly.
    """

    pass


class EmbeddedTextBlock(DataBlock):
    """
    Abstract Block for embedded text formats that are stored directly in the
    document (rather than external references)
    """

    content: str

    def __init__(self, content: str, name: BlockId = None, **kwargs):
        super().__init__(name, **kwargs)
        self.content = content.strip()

    def _to_xml(self, s: BuilderState) -> BuilderState:
        # NOTE - do we use etree.CDATA wrapper?
        _E = getattr(E, self._tag)
        return s.add_element(self, _E(etree.CDATA(self.content), **self._attributes))


class Text(EmbeddedTextBlock):
    """
    Markdown objects store Markdown text that can be displayed as formatted text when viewing your report.

    ..note:: This object is also available as `dp.Text`, and any strings provided directly to the Report/Group object are converted automatically to Markdown blocks

    ..tip:: You can also insert a dataframe in a Markdown block as a table by using `df.to_markdown()`, or use dp.Table or dp.DataTable for dedicated dataframe tables.
    """

    _tag = "Text"

    def __init__(self, text: str = None, file: NPath = None, name: BlockId = None, label: str = None):
        """
        Args:
            text: The markdown formatted text, use triple-quotes, (`\"\"\"# My Title\"\"\"`) to create multi-line markdown text
            file: Path to a file containing markdown text
            name: A unique name for the block to reference when adding text or embedding (optional)
            label: A label used when displaying the block (optional)

        ..note:: File encodings are auto-detected, if this fails please read the file manually with an explicit encoding and use the text parameter on dp.Attachment
        """
        if text:
            text = text.strip()

        assert text or file
        content = text or utf_read_text(Path(file).expanduser())
        super().__init__(content=content, name=name, label=label)

    def format(self, *args: BlockOrPrimitive, **kwargs: BlockOrPrimitive) -> Group:
        """
        Format the markdown text template, using the supplied context to insert blocks into `{{}}` markers in the template.

        `{}` markers can be empty, hence positional, or have a name, e.g. `{{plot}}`, which is used to lookup the value from the keyword context.

        Args:
            *args: positional template context arguments
            **kwargs: keyword template context arguments

        ..tip:: Either Python objects, e.g. dataframes, and plots, or Datapane blocks as context

        Returns:
            A datapane Group object containing the list of text and embedded objects
        """

        splits = re.split(r"\{\{(\w*)\}\}", self.content)
        deque_args = deque(args)
        blocks = []

        for (i, x) in enumerate(splits):
            is_block = bool(i % 2)

            if is_block:
                try:
                    if x:
                        blocks.append(wrap_block(kwargs[x]))
                    else:
                        blocks.append(wrap_block(deque_args.popleft()))
                except (IndexError, KeyError):
                    raise DPError(f"Unknown/missing object '{x}' referenced in Markdown format")

            else:
                x = x.strip()
                if x:
                    blocks.append(Text(x))

        return Group(blocks=blocks)


class Code(EmbeddedTextBlock):
    """
    Code objects store source code that can be displayed as formatted text when viewing your report.
    """

    _tag = "Code"

    def __init__(
        self, code: str, language: str = "python", caption: str = None, name: BlockId = None, label: str = None
    ):
        """
        Args:
            code: The source code
            language: The language of the code, most common languages are supported (optional - defaults to Python)
            caption: A caption to display below the Code (optional)
            name: A unique name for the block to reference when adding text or embedding (optional)
            label: A label used when displaying the block (optional)
        """
        super().__init__(content=code, language=language, caption=caption, name=name, label=label)


class HTML(EmbeddedTextBlock):
    """
    HTML blocks can be used to embed an arbitrary HTML fragment in a report.
    """

    _tag = "HTML"

    def __init__(self, html: t.Union[str, dom_tag], name: BlockId = None, label: str = None):
        """
        Args:
            html: The HTML fragment to embed - can be a string or a [dominate](https://github.com/Knio/dominate/) tag
            name: A unique name for the block to reference when adding text or embedding (optional)
            label: A label used when displaying the block (optional)
        """
        super().__init__(content=str(html), name=name, label=label)


class Formula(EmbeddedTextBlock):
    """
    Formula blocks can be used to embed LaTeX in a report.
    """

    _tag = "Formula"

    def __init__(self, formula: str, caption: str = None, name: BlockId = None, label: str = None):
        r"""
        Args:
            formula: The formula to embed, using LaTeX format (use raw strings)
            caption: A caption to display below the Formula (optional)
            name: A unique name for the block to reference when adding text or embedding (optional)
            label: A label used when displaying the block (optional)

            ..note:: LaTeX commonly uses special characters, hence prefix your formulas with `r` to make them
            raw strings, e.g. r"\frac{1}{\sqrt{x^2 + 1}}"
        """
        super().__init__(content=formula, caption=caption, name=name, label=label)


class Embed(EmbeddedTextBlock):
    """
    Embed blocks allow HTML from OEmbed providers (e.g. Youtube, Twitter, Vimeo) to be embedded in a report.
    """

    _tag = "Embed"

    def __init__(self, url: str, width: int = 960, height: int = 540, name: BlockId = None, label: str = None):
        """
        Args:
            url: The URL of the resource to be embedded
            width: The width of the embedded object (optional)
            height: The height of the embedded object (optional)
            name: A unique name for the block to reference when adding text or embedding (optional)
            label: A label used when displaying the block (optional)
        """

        result = get_embed_url(url, width=width, height=height)

        # if "html" not in result:
        #     raise DPError(f"Can't embed result from provider for URL '{url}'")
        super().__init__(
            content=result.html, name=name, label=label, url=url, title=result.title, provider_name=result.provider
        )


NumberValue = t.Union[str, int, float]


class BigNumber(DataBlock):
    """
    BigNumber blocks display a numerical value with a heading, alongside optional contextual information about the previous value.
    """

    _tag = "BigNumber"

    def __init__(
        self,
        heading: str,
        value: NumberValue,
        change: t.Optional[NumberValue] = None,
        prev_value: t.Optional[NumberValue] = None,
        is_positive_intent: t.Optional[bool] = None,
        is_upward_change: t.Optional[bool] = None,
        name: BlockId = None,
        label: str = None,
    ):
        """
        Args:
            heading: A title that gives context to the displayed number
            value: The value of the number
            prev_value: The previous value to display as comparison (optional)
            change: The amount changed between the value and previous value (optional)
            is_positive_intent: Displays the change on a green background if `True`, and red otherwise. Follows `is_upward_change` if not set (optional)
            is_upward_change: Whether the change is upward or downward (required when `change` is set)
            name: A unique name for the block to reference when adding text or embedding (optional)
            label: A label used when displaying the block (optional)
        """
        if change:
            if is_upward_change is None:
                # We can't reliably infer the direction of change from the change string
                raise ValueError('Argument "is_upward_change" is required when "change" is set')
            if is_positive_intent is None:
                # Set the intent to be the direction of change if not specified (up = green, down = red)
                is_positive_intent = is_upward_change

        super().__init__(
            heading=heading,
            value=value,
            change=change,
            prev_value=prev_value,
            is_positive_intent=bool(is_positive_intent),
            is_upward_change=bool(is_upward_change),
            name=name,
            label=label,
        )


class AssetBlock(DataBlock):
    """
    AssetBlock objects form basis of all File-related blocks (abstract class, not exported)
    """

    # TODO - we may need to support file here as well to handle media, etc.
    file: Path = None
    data: t.Optional[t.Any] = None
    caption: t.Optional[str] = None

    def __init__(
        self,
        data: t.Optional[t.Any] = None,
        file: t.Optional[Path] = None,
        caption: str = None,
        name: BlockId = None,
        label: str = None,
        **kwargs,
    ):
        # storing objects for delayed upload
        super().__init__(name=name, label=label, **kwargs)
        self.data = data
        self.file = file
        self.caption = caption or ""

    def _to_xml(self, s: BuilderState) -> BuilderState:
        # import here as a very slow module due to nested imports
        from .. import files

        if self.data is not None:
            fe = files.add_to_store(self.data, s.store)
        elif self.file is not None:
            fe = s.store.load_file(self.file)
        else:
            raise DPError("No asset to add")

        # NOTE: we inline the file attributes here rather than as a later transformation pass atm for simplicity
        _E = getattr(E, self._tag)

        self._add_attributes()
        e: etree._Element = _E(
            type=fe.mime,
            size=conv_attrib(fe.size),
            hash=fe.hash,
            **self._attributes,
            src=f"attachment://{s.store_count}",
        )

        if self.caption:
            e.set("caption", self.caption)
        return s.add_element(self, e)


class Media(AssetBlock):
    """
    Media blocks are used to attach a file to the report that can be viewed or streamed by report viewers

    ..note:: Supported video, audio and image formats depends on the browser used to view the report. MP3, MP4, and all common image formats are generally supported by modern browsers
    """

    _tag = "Media"

    def __init__(
        self,
        file: NPath,
        name: BlockId = None,
        label: str = None,
        caption: t.Optional[str] = None,
    ):
        """
        Args:
            file: Path to a file to attach to the report (e.g. a JPEG image)
            name: A unique name for the block to reference when adding text or embedding (optional)
            caption: A caption to display below the file (optional)
            label: A label used when displaying the block (optional)
        """
        file = Path(file).expanduser()
        data = file.read_bytes()
        super().__init__(data=data, name=name, caption=caption, label=label)


class Attachment(AssetBlock):
    """
    Attachment blocks are used to attach a file to the report that can be downloaded by report viewers

    Any type of file may be attached, for instance, images (png / jpg), PDFs, JSON data, Excel files, etc.

    ..tip:: To attach streamable / viewable video, audio or images, use the `dp.Media` block instead
    """

    _tag = "Attachment"

    def __init__(
        self,
        data: t.Optional[t.Any] = None,
        file: t.Optional[NPath] = None,
        filename: t.Optional[str] = None,
        caption: t.Optional[str] = None,
        name: BlockId = None,
        label: str = None,
    ):
        """
        Args:
            data: A python object to attach to the report (e.g. a dictionary)
            file: Path to a file to attach to the report (e.g. a csv file)
            filename: Name to be used when downloading the file (optional)
            caption: A caption to display below the file (optional)
            name: A unique name for the block to reference when adding text or embedding (optional)
            label: A label used when displaying the block (optional)

        ..note:: either `data` or `file` must be provided
        """
        if file:
            # TODO - fix this
            file = Path(file).expanduser()
            data = file.read_bytes()
            filename = filename or file.name
        else:
            data = data
            # out_fn = self._save_obj(data)
            # file = out_fn.file
            filename = filename or "test.data"

        super().__init__(data=data, filename=filename, name=name, caption=caption, label=label)


class Plot(AssetBlock):
    """
    Plot blocks store a Python-based plot object, including ones created by Altair, Plotly, Matplotlib, Bokeh, Folium, and PlotAPI,
    for interactive display in your report when viewed in the browser.
    """

    _tag = "Plot"

    def __init__(
        self,
        data: t.Any,
        caption: t.Optional[str] = None,
        responsive: bool = True,
        scale: float = 1.0,
        name: BlockId = None,
        label: str = None,
    ):
        """
        Args:
            data: The `plot` object to attach
            caption: A caption to display below the plot (optional)
            responsive: Whether the plot should automatically be resized to fit, set to False if your plot looks odd (optional, default: True)
            scale: Set the scaling factor for the plt (optional, default = 1.0)
            name: A unique name for the block to reference when adding text or embedding (optional)
            label: A label used when displaying the block (optional)
        """
        # out_fn = self._save_obj(data)
        # if out_fn.mime == PKL_MIMETYPE:
        #     raise DPError("Can't embed object as a plot")

        super().__init__(data=data, caption=caption, responsive=responsive, scale=scale, name=name, label=label)


class Table(AssetBlock):
    """
    Table blocks store the contents of a dataframe as a HTML `table` whose style can be customised using
    pandas' `Styler` API.
    """

    # NOTE - Tables are stored as HTML fragment files rather than inline within the Report document

    _tag = "Table"

    def __init__(
        self,
        data: t.Union[pd.DataFrame, Styler],
        caption: t.Optional[str] = None,
        name: BlockId = None,
        label: str = None,
    ):
        """
        Args:
            data: The pandas `Styler` instance or dataframe to generate the table from
            caption: A caption to display below the table (optional)
            name: A unique name for the block to reference when adding text or embedding (optional)
            label: A label used when displaying the block (optional)
        """
        # out_fn = self._save_obj(data)
        super().__init__(data=data, caption=caption, name=name, label=label)


class DataTable(AssetBlock):
    """
    DataTable blocks store a dataframe that can be viewed, sorted, filtered by users viewing your report, similar to a spreadsheet,
    and can be downloaded by them as a CSV or Excel file.

    ..tip:: For smaller dataframes where you don't require sorting and filtering, also consider using the `Table` block
    ..note:: The DataTable component has advanced analysis features that requires a server and is not supported when saving locally, please upload such reports to a Datapane Server or use dp.Table

    """

    _tag = "DataTable"

    def __init__(
        self,
        df: pd.DataFrame,
        caption: t.Optional[str] = None,
        name: BlockId = None,
        label: str = None,
    ):
        """
        Args:
            df: The pandas dataframe to attach to the report
            caption: A caption to display below the plot (optional)
            name: A unique name for the block to reference when adding text or embedding (optional)
            label: A label used when displaying the block (optional)
        """
        fn = save_df(df)
        (rows, columns) = df.shape
        # TODO - support pyarrow schema for local reports
        self.file_attribs = mk_attribs(rows=rows, columns=columns, schema="[]")
        super().__init__(file=fn.file, caption=caption, name=name, label=label)


class Divider(EmbeddedTextBlock):
    """
    Divider blocks add a horizontal line to your report, normally used to break up report contents
    """

    _tag = "Text"

    def __init__(self):
        # `---` is processed as a horizontal divider by the FE markdown renderer
        super().__init__(content="---")
