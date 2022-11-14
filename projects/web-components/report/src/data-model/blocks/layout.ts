import { useControlStore, useLayoutStore } from "../layout-store";
import { markRaw } from "vue";
import VGroup from "../../components/layout/Group.vue";
import VSelect from "../../components/layout/SelectBlock.vue";
import VToggle from "../../components/layout/Toggle.vue";
import { Block, BlockFigure, View } from "./leaf-blocks";
import VInteractive from "../../components/controls/Interactive.vue";
import { ControlsField } from "./interactive";

export abstract class LayoutBlock<T extends Block = Block> extends Block {
    public children: T[];
    public store: any;

    public constructor(elem: any, figure: BlockFigure) {
        super(elem, figure);
        const { children } = elem.attributes;
        this.children = children;
        this.store = useLayoutStore(this.children)();
        this.componentProps = { ...this.componentProps, store: this.store };
    }
}

export class Group extends LayoutBlock {
    public component = markRaw(VGroup);
    public name = "Group";
    public columns: number;

    public constructor(elem: any, figure: BlockFigure) {
        super(elem, figure);
        this.columns = +elem.attributes.columns;
        this.componentProps = { ...this.componentProps, columns: this.columns };
    }
}

export class Select extends LayoutBlock {
    public component = markRaw(VSelect);
    public name = "Select";
    public type: string;
    public layout: string;

    public constructor(elem: any, figure: BlockFigure) {
        super(elem, figure);
        const { label, type, layout } = elem.attributes;
        this.label = label;
        this.type = type;
        this.layout = layout;
        this.componentProps = { ...this.componentProps, type };
    }
}

export class Toggle extends LayoutBlock {
    public component = markRaw(VToggle);
    public name = "Toggle";

    public constructor(elem: any, figure: BlockFigure) {
        super(elem, figure);
        const { children, label } = elem.attributes;
        this.children = children;
        this.label = label;
        this.componentProps = { ...this.componentProps, label };
    }
}

export class Interactive extends LayoutBlock<ControlsField> {
    public component = markRaw(VInteractive);
    public name = "Interactive";

    public constructor(elem: any, figure: BlockFigure) {
        super(elem, figure);
        const { target, method } = elem.attributes;
        this.store = useControlStore(this.children, target, method)();
        this.componentProps = {
            ...this.componentProps,
            target,
            method,
            store: this.store,
        };
    }
}

export const isView = (obj: any): obj is View => obj.name === "View";

export const isGroup = (obj: any): obj is Group => obj.name === "Group";

export const isSelect = (obj: any): obj is Select => obj.name === "Select";

export const isToggle = (obj: any): obj is Toggle => obj.name === "Toggle";

export const isInteractive = (obj: any): obj is Toggle =>
    obj.name === "Interactive";

export const isLayoutBlock = (obj: any): obj is LayoutBlock =>
    isView(obj) ||
    isSelect(obj) ||
    isToggle(obj) ||
    isView(obj) ||
    isGroup(obj) ||
    isInteractive(obj);
