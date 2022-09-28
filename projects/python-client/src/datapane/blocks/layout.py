from __future__ import annotations

import dataclasses as dc
import enum
import typing as t
from functools import reduce

from glom import glom

from datapane.client import DPClientError

from .base import BaseElement, BlockList, BlockId, BlockOrPrimitive, E, wrap_block

if t.TYPE_CHECKING:
    from datapane.processors import BuilderState
    from .view import Block


class SelectType(enum.Enum):
    DROPDOWN = "dropdown"
    TABS = "tabs"


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
            raise DPClientError("Can't create Select with less than 2 objects")


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
