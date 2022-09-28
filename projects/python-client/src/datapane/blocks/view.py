from __future__ import annotations

import typing as t
from functools import reduce

from lxml.etree import Element

from datapane.client.ipython_utils import cells_to_blocks
from datapane.client import DPClientError
from datapane.common.viewxml_utils import mk_attribs
from . import BlockList

from .base import BlockOrPrimitive, E, wrap_block
from .misc_blocks import Empty
from .layout import BlockListIterator, Group

if t.TYPE_CHECKING:
    from datapane.processors import BuilderState, FileStore


Block = t.Union["Group", "Select", "DataBlock", "Empty", "Interactive"]


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
            raise DPClientError("Can't create View with 0 objects")
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

    @classmethod
    def from_notebook(cls, opt_out: bool = True) -> View:
        blocks = cells_to_blocks(opt_out=opt_out)

        return cls(blocks=blocks)

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


