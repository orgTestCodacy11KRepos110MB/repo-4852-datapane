import { Block, BlockFigure, Elem } from "./leaf-blocks";
import { markRaw } from "vue";
import VRangeField from "../../components/controls/RangeField.vue";
import VStringField from "../../components/controls/StringField.vue";
import VTagsField from "../../components/controls/TagsField.vue";
import VSwitchField from "../../components/controls/SwitchField.vue";
import VMultiSelectField from "../../components/controls/MultiSelectField.vue";
import VFileField from "../../components/controls/FileField.vue";
import VDateTimeField from "../../components/controls/DateTimeField.vue";
import VSelectField from "../../components/controls/SelectField.vue";
import moment from "moment";

export abstract class ControlsField extends Block {
    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure); // TODO -- `figure` is unused, should use new base class?
        const { helpText, name, required, initialValue } = elem.attributes;
        this.componentProps = {
            ...this.componentProps,
            helpText,
            name,
            required: required ? JSON.parse(required) : undefined,
            initialValue,
        };
    }
}

export class RangeField extends ControlsField {
    public component = markRaw(VRangeField);
    public name = "RangeField";

    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
        const { min, max, step, initialValue } = elem.attributes;
        this.componentProps = {
            ...this.componentProps,
            min: +min,
            max: +max,
            step: +step,
            initialValue: +initialValue,
        };
    }
}

export class StringField extends ControlsField {
    public component = markRaw(VStringField);
    public name = "StringField";

    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
        this.componentProps = { ...this.componentProps };
    }
}

export class TagsField extends ControlsField {
    public component = markRaw(VTagsField);
    public name = "TagsField";

    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
        const { initialValue } = elem.attributes;
        this.componentProps = {
            ...this.componentProps,
            initialValue: initialValue ? JSON.parse(initialValue) : undefined,
        };
    }
}

export class MultiSelectField extends ControlsField {
    public component = markRaw(VMultiSelectField);
    public name = "MultiSelectField";

    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
        const { initialValue, choices } = elem.attributes;
        this.componentProps = {
            ...this.componentProps,
            choices: JSON.parse(choices),
            initialValue: initialValue ? JSON.parse(initialValue) : undefined,
        };
    }
}

export class FileField extends ControlsField {
    public component = markRaw(VFileField);
    public name = "FileField";

    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
    }
}

export class TemporalField extends ControlsField {
    public component = markRaw(VDateTimeField);

    public constructor(elem: Elem, figure: BlockFigure, opts?: any) {
        super(elem, figure);
        const { initialValue } = elem.attributes;
        const { timeFormat, type } = opts;
        this.componentProps = {
            ...this.componentProps,
            // `moment(undefined)` resolves to current date
            initialValue: moment(initialValue).format(timeFormat),
            type,
        };
    }
}

export class SelectField extends ControlsField {
    public component = markRaw(VSelectField);

    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
        const { choices } = elem.attributes;
        this.componentProps = {
            ...this.componentProps,
            choices: JSON.parse(choices),
        };
    }
}

export class SwitchField extends ControlsField {
    public component = markRaw(VSwitchField);
    public name = "SwitchField";

    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
        const { initialValue } = elem.attributes;
        this.componentProps = {
            ...this.componentProps,
            initialValue: initialValue ? JSON.parse(initialValue) : false,
        };
    }
}
