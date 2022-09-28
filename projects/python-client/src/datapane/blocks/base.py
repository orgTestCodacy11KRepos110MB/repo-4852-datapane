"""
Datapane Blocks API

Describes the collection of `Block` objects that can be combined together to make a `datapane.client.api.report.core.Report`.
"""
from __future__ import annotations

import typing as t
from abc import ABC

from lxml.builder import ElementMaker

from datapane.client import DPClientError, log
from datapane.client.ipython_utils import block_to_iframe
from datapane.common.viewxml_utils import is_valid_id, mk_attribs

if t.TYPE_CHECKING:
    from datapane.processors import BuilderState
    from .view import Block

E = ElementMaker()  # XML Tag Factory

# only these types will be documented by default
# __all__ = [
#     "BaseElement",
#     "SelectType",
#     "View",
# ]
#
# __pdoc__ = {
#     "Media.caption": False,
#     "Media.file": False,
#     "Attachment.caption": False,
#     "Attachment.file": False,
#     "Plot.file": False,
#     "DataTable.file": False,
# }


BlockId = str


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
                raise DPClientError(f"Invalid name '{name}' for block")
            self.name = name
            self._attributes.update(name=name)

    def _add_attributes(self, **kwargs):
        self._attributes.update(mk_attribs(**kwargs))

    def _ipython_display_(self):
        """Display the block as a side effect within a Jupyter notebook"""
        from IPython.display import HTML, display

        block_html_string = block_to_iframe(self)

        display(HTML(block_html_string))

    def _to_xml(self, s: BuilderState) -> BuilderState:
        """Base implementation - just created an empty tag including all the initial attributes"""
        _E = getattr(E, self._tag)
        return s.add_element(self, _E(**self._attributes))


class DataBlock(BaseElement):
    """Abstract block that represents a leaf-node in the tree, e.g. a Plot or Table

    ..note:: This class is not used directly.
    """

    pass


BlockOrPrimitive = t.Union["Block", t.Any]  # TODO - expand
BlockList = t.List["Block"]


def wrap_block(b: BlockOrPrimitive) -> Block:
    from .asset_writers import convert_to_block

    # if isinstance(b, Page):
    #     raise DPError("Page objects can only be at the top-level")
    if not isinstance(b, BaseElement):
        # import here as a very slow module due to nested imports
        # from ..files import convert

        return convert_to_block(b)
    return t.cast(Block, b)
