from __future__ import annotations

import secrets
import typing as t

from lxml import etree

from .base import BaseElement, BlockId, DataBlock, E

if t.TYPE_CHECKING:
    from datapane.processors import BuilderState


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
