import { ReportProps } from "./types";
import { defineStore } from "pinia";
import convert from "xml-js";
import { reactive, ref } from "vue";
import * as b from "./blocks/index";
import * as maps from "./test-maps";
import { isLayoutBlock } from "./blocks/index";

export type EmptyObject = Record<string, never>;

const XML_FIXTURE = `
<View>
    <Formula id="f1">e = mc^2</Formula>
    <Interactive method="append" target="root" id="c1">
        <Controls>
            <String name="string_field" required="true"/>
            <Range initialValue="4" min="0" max="10" step="1" name="range_field"/>
            <Tags initialValue='["foo", "bar"]' name="tags_field" required="true"/>
            <MultiSelect initialValue='["foo"]' name="multi_field" choices='["foo", "bar"]' required="true"/>
            <Switch initialValue="true" name="switch_field"/>
            <File name="file_field" required="true"/>
            <Date name="date_field" initialValue="2022-11-16T11:04:51Z" required="true"/>
            <Time name="time_field" initialValue="2022-11-16T11:04:51Z" required="true"/>
            <DateTime name="datetime_field" initialValue="2022-11-16T11:04:51Z" required="true"/>
            <SelectField name="select_field" initialValue="bar" choices='["foo", "bar"]'/>
        </Controls>
    </Interactive>
    <Text label="txt" id="t1">Hello, world!</Text>
</View>
`;

// const XML_FIXTURE = `
// <View>
//     <Group columns="1">
//         <Text label="txt" id="t1">Hello, world!</Text>
//         <Text label="txt" id="t1">Hello, world!</Text>
//     </Group>
// </View>
// `;

const XML_RESPONSE = (parameters: any) => `
<View fragment="true">
    <BigNumber caption="bn0" label="bn0" id="f1" heading="${parameters.string_field}" value="${parameters.range_field}" prev_value="30"/>
</View>
`;

const mkBlockMap = (
    isLightProse: boolean,
    webUrl: string,
    isOrg: boolean
): BlockTest[] => {
    /**
     * class_: The deserialized class that maps to a JSON `elem`
     * test: Function that returns true if the JSON should deserialize into the associated `class_`
     * opts: Additional metadata to be passed into the class
     */
    return [
        {
            class_: b.TextBlock,
            test: maps.jsonIsMarkdown,
            opts: { isLightProse },
        },
        { class_: b.BokehBlock, test: maps.jsonIsBokeh },
        {
            class_: b.DataTableBlock,
            test: maps.jsonIsArrowTable,
            opts: { webUrl },
        },
        { class_: b.CodeBlock, test: maps.jsonIsCode },
        { class_: b.VegaBlock, test: maps.jsonIsVega },
        { class_: b.PlotlyBlock, test: maps.jsonIsPlotly },
        { class_: b.TableBlock, test: maps.jsonIsHTMLTable },
        {
            class_: b.HTMLBlock,
            test: maps.jsonIsHTML,
            opts: { isOrg },
        },
        { class_: b.SVGBlock, test: maps.jsonIsSvg },
        { class_: b.FormulaBlock, test: maps.jsonIsFormula },
        { class_: b.MediaBlock, test: maps.jsonIsMedia },
        { class_: b.EmbedBlock, test: maps.jsonIsEmbed },
        { class_: b.FoliumBlock, test: maps.jsonIsIFrameHTML },
        { class_: b.PlotapiBlock, test: maps.jsonIsPlotapi },
        { class_: b.BigNumberBlock, test: maps.jsonIsBigNumber },
        { class_: b.Interactive, test: maps.jsonIsInteractive },
        { class_: b.StringField, test: maps.jsonIsStringField },
        { class_: b.RangeField, test: maps.jsonIsRangeField },
        { class_: b.TagsField, test: maps.jsonIsTagsField },
        { class_: b.SwitchField, test: maps.jsonIsSwitchField },
        { class_: b.MultiSelectField, test: maps.jsonIsMultiSelectField },
        { class_: b.FileField, test: maps.jsonIsFileField },
        { class_: b.SelectField, test: maps.jsonIsSelectField },
        {
            class_: b.TemporalField,
            test: maps.jsonIsDateTimeField,
            opts: { timeFormat: "YYYY-MM-DDTHH:mm:ss", type: "datetime-local" },
        },
        {
            class_: b.TemporalField,
            test: maps.jsonIsDateField,
            opts: { timeFormat: "YYYY-MM-DD", type: "date" },
        },
        {
            class_: b.TemporalField,
            test: maps.jsonIsTimeField,
            opts: { timeFormat: "HH:mm:ss", type: "time" },
        },
        { class_: b.Group, test: maps.jsonIsGroup },
        { class_: b.View, test: maps.jsonIsView },
        { class_: b.Select, test: maps.jsonIsSelect },
        { class_: b.Toggle, test: maps.jsonIsToggle },
        { class_: b.FileBlock, test: () => true },
    ];
};

type BlockTest = {
    class_: typeof b.Block;
    test: (elem: b.Elem) => boolean;
    opts?: any;
};

const getAttributes = (elem: b.Elem): any =>
    /**
     * Ensure the attributes object is never undefined
     * -- xml-js removes the attributes property when a tag has none.
     **/
    elem.attributes || {};

const getElementByName = (elem: b.Elem, name: string): any => {
    if (!elem.elements) return null;
    return elem.elements.find((elem: any) => elem.name === name);
};

const swapChildren = (
    el: b.LayoutBlock,
    deserialized: b.View,
    target: string
): true | undefined => {
    for (const [idx, child] of el.children.entries()) {
        if (child.id === target) {
            el.store.swap(idx, ...deserialized.children);
            return true;
        }
    }
};

const isSingleBlockEmbed = (
    report: b.View,
    mode: "EMBED" | "VIEW"
): boolean => {
    /**
     * Returns `true` if the report consists of a single block, and is in embed (iframe) mode.
     * Single blocks embedded in an iframe require style changes to ensure they fit the iframe dimensions
     */
    const checkAllGroupsSingle = (node: b.Block): boolean => {
        /* Check there's a single route down to one leaf node */
        if (isLayoutBlock(node) && node.children.length === 1) {
            // Node is a layout block with a single child
            return checkAllGroupsSingle(node.children[0]);
        } else if (isLayoutBlock(node)) {
            // Node is a layout block with multiple children
            return false;
        } else {
            // Node is a Select or leaf
            return true;
        }
    };

    return mode === "EMBED" && checkAllGroupsSingle(report);
};

export const useRootStore = defineStore("root", () => {
    const counts = reactive({
        Figure: 0,
        Table: 0,
        Plot: 0,
    });

    const blockMap = reactive<BlockTest[]>([]);
    const report = reactive<b.View | EmptyObject>({});
    const singleBlockEmbed = ref<boolean>();

    const deserializeBlock = (elem: b.Elem): b.Block => {
        /**
         * Deserialize leaf block node into relevant `Block` class
         */
        const captionType = "Figure"; // TODO
        const { caption } = getAttributes(elem);
        const count = caption ? updateFigureCount(captionType) : undefined;
        const figure = { caption, count };

        const blockTest: BlockTest | undefined = blockMap.find((b) =>
            b.test(elem)
        );

        if (blockTest) {
            const { class_, opts } = blockTest;
            return new class_(elem, figure, opts);
        } else {
            throw `Couldn't deserialize from JSON ${elem}`;
        }
    };

    const setReportProps = (reportProps: ReportProps) => {
        blockMap.push(
            ...mkBlockMap(
                reportProps.report.output_is_light_prose,
                reportProps.report.web_url,
                reportProps.isOrg
            )
        );
        Object.assign(report, xmlToReport(XML_FIXTURE));
        // Can cast to `View` as we just assigned the response to `Report`
        singleBlockEmbed.value = isSingleBlockEmbed(
            report as b.View,
            reportProps.mode
        );
    };

    const deserialize = (elem: b.Elem): b.Block => {
        if (!elem.attributes) {
            elem.attributes = {};
        }

        if (b.isInteractive(elem)) {
            // Skip inner `Controls` block
            // Can assert not-null as layout block JSON always contains `elements`
            // TODO - adjust types so we can remove not-null assertion
            elem.elements = elem.elements![0].elements;
        }

        if (b.isLayoutBlock(elem)) {
            elem.attributes.children = elem.elements!.map((e) =>
                deserialize(e)
            );
        }
        return deserializeBlock(elem);
    };

    const update = (target: string, method: string, parameters: any) => {
        if (!b.isView(report)) {
            throw "Report object not yet initialized" + JSON.stringify(report);
        }
        const deserialized: b.View = xmlToReport(XML_RESPONSE(parameters)); // TODO - fixture
        const stack: b.LayoutBlock[] = [report];

        while (stack.length) {
            const el = stack.pop();

            if (!el) return;

            if (!b.isLayoutBlock(el)) continue;

            if (
                (method === "append" || method === "prepend") &&
                el.id === target
            ) {
                return void el.store[method](...deserialized.children);
            } else {
                if (method === "swap") {
                    const didSwap = swapChildren(el, deserialized, target);
                    if (didSwap) return;
                }
                stack.push(...el.children.filter(b.isLayoutBlock));
            }
        }
    };

    const xmlToReport = (xml: string): b.View => {
        /**
         * Convert an XML string document to a deserialized tree of `Block` objects
         */
        const json: any = convert.xml2js(xml, { compact: false });
        const root = getElementByName(json, "View");
        return deserialize(root) as b.View;
    };

    function updateFigureCount(captionType: b.CaptionType): number {
        return ++counts[captionType];
    }

    return { report, counts, update, singleBlockEmbed, setReportProps };
});
