import VTextBlock from "../../components/blocks/Text.vue";
import VHTMLBlock from "../../components/blocks/HTML.vue";
import VFileBlock from "../../components/blocks/File.vue";
import VEmbedBlock from "../../components/blocks/Embed.vue";
import VFoliumBlock from "../../components/blocks/Folium.connector.vue";
import VPlotapiBlock from "../../components/blocks/Plotapi.connector.vue";
import VFormulaBlock from "../../components/blocks/Formula.connector.vue";
import VCodeBlock from "../../components/blocks/Code.connector.vue";
import VBokehBlock from "../../components/blocks/Bokeh.connector.vue";
import VVegaBlock from "../../components/blocks/Vega.connector.vue";
import VPlotlyBlock from "../../components/blocks/Plotly.connector.vue";
import VTableBlock from "../../components/blocks/Table.connector.vue";
import VSVGBlock from "../../components/blocks/SVG.connector.vue";
import VMediaBlock from "../../components/blocks/Media.vue";
import VBigNumberBlock from "../../components/blocks/BigNumber.vue";
import VBigNumberBlockSimple from "../../components/blocks/BigNumberSimple.vue";
import { markRaw } from "vue";
import axios from "axios";
import { saveAs } from "file-saver";
import { useViewStore } from "../layout-store";
import { v4 as uuid4 } from "uuid";

// Represents a serialised JSON element prior to becoming a Page/Group/Select/Block
export type Elem = {
    name: string;
    attributes?: any;
    elements?: Elem[];
    text?: string;
    cdata?: string;
    type: "element";
};

type AssetResource = Promise<string | object>;

export type BlockFigureProps = {
    caption?: string;
    captionType: string;
    count?: number;
};

export type BlockFigure = Pick<BlockFigureProps, "count" | "caption">;

export type CaptionType = "Table" | "Figure" | "Plot";

/* Helper functions */

export const decodeBase64Asset = (src: string): string => {
    return window.atob(src.split("base64,")[1]);
};

const getInnerText = (elem: Elem): string => {
    /**
     * get the CDATA of a JSON-serialised element
     */
    if (!elem.elements || !elem.elements.length)
        throw new Error("Can't get inner text of a node without elements");
    const innerElem = elem.elements[0];
    return innerElem.text || innerElem.cdata || "";
};

const readGcsTextOrJsonFile = <T = string | object | null>(
    url: string
): Promise<T> => {
    /**
     * wrapper around `axios.get` to fetch data object of response only
     */
    return axios.get(url).then((res) => res.data);
};

const decodeBase64AssetUtf8 = (src: string) => {
    /**
     * decode b64'd UTF-8 string
     * see https://stackoverflow.com/a/64752311
     */
    const text = decodeBase64Asset(src);
    const { length } = text;
    const bytes = new Uint8Array(length);
    for (let i = 0; i < length; i++) {
        bytes[i] = text.charCodeAt(i);
    }
    const decoder = new TextDecoder(); // default is utf-8
    return decoder.decode(bytes);
};

/* Inline blocks */

export class Block {
    public refId = uuid4();
    public id?: string;
    public captionType = "Figure";
    public caption?: string;
    public label?: string;
    public count?: number;
    public componentProps: any;
    public component: any;

    public constructor(
        elem: Elem,
        figure: BlockFigure,
        /* eslint-disable-next-line @typescript-eslint/no-unused-vars */
        opts?: any
    ) {
        const { attributes } = elem;
        this.count = figure.count;
        this.caption = figure.caption;
        this.componentProps = {
            figure: { ...figure, captionType: this.captionType },
        };

        if (attributes) {
            this.id = attributes.id;
            this.label = attributes.label;
        }
    }
}

export class TextBlock extends Block {
    public component = markRaw(VTextBlock);
    public name = "TextBlock";

    public constructor(elem: Elem, figure: BlockFigure, opts?: any) {
        super(elem, figure);
        const content = getInnerText(elem);
        this.componentProps = {
            ...this.componentProps,
            content,
            isLightProse: opts.isLightProse,
        };
    }
}

export class CodeBlock extends Block {
    public component = markRaw(VCodeBlock);

    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
        const { language } = elem.attributes;
        const code = getInnerText(elem);
        this.componentProps = { ...this.componentProps, code, language };
    }
}

export class View extends Block {
    public id = "root";
    public name = "View";
    public children: Block[];
    public store: any;

    public constructor(elem: any, figure: BlockFigure) {
        super(elem, figure);
        const { children, layout, fragment } = elem.attributes;
        this.children = children;
        this.store = fragment
            ? undefined
            : useViewStore(this.children, layout)();
        this.componentProps = { ...this.componentProps, store: this.store };
    }
}

export class HTMLBlock extends Block {
    public component = markRaw(VHTMLBlock);

    public constructor(elem: Elem, figure: BlockFigure, opts?: any) {
        super(elem, figure);
        const html = getInnerText(elem);
        this.componentProps = {
            ...this.componentProps,
            html,
            sandbox: opts.isOrg ? undefined : "allow-scripts",
        };
    }
}

export class FormulaBlock extends Block {
    public component = markRaw(VFormulaBlock);

    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
        const content = getInnerText(elem);
        this.componentProps = {
            ...this.componentProps,
            content,
        };
    }
}

export class BigNumberBlock extends Block {
    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
        const { attributes } = elem;
        const useSimple = !attributes.prev_value && !attributes.change;
        this.component = markRaw(
            useSimple ? VBigNumberBlockSimple : VBigNumberBlock
        );
        this.componentProps = {
            ...this.componentProps,
            heading: attributes.heading,
            value: attributes.value,
        };
        if (!useSimple) {
            this.componentProps = {
                ...this.componentProps,
                isPositiveIntent: JSON.parse(
                    attributes.is_positive_intent || "false"
                ),
                isUpwardChange: JSON.parse(
                    attributes.is_upward_change || "false"
                ),
                prevValue: attributes.prev_value,
                change: attributes.change,
            };
        }
    }
}

/* Asset blocks */

export abstract class AssetBlock extends Block {
    /**
     * Blocks whose data should be fetched on load rather than in-lined in the XML CDATA
     */
    public src: string;
    public type: string;

    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
        const { attributes } = elem;
        this.src = attributes.src;
        this.type = attributes.type;
        this.componentProps = {
            ...this.componentProps,
            fetchAssetData: this.fetchAssetData.bind(this),
        };
    }

    protected fetchLocalAssetData(): string {
        return decodeBase64Asset(this.src);
    }

    protected async fetchAssetData(): AssetResource {
        return window.dpLocal
            ? this.fetchLocalAssetData()
            : this.fetchRemoteAssetData();
    }

    protected async fetchRemoteAssetData(): AssetResource {
        return await readGcsTextOrJsonFile(this.src);
    }
}

export class TableBlock extends AssetBlock {
    public component = markRaw(VTableBlock);
    public captionType = "Table";

    protected fetchLocalAssetData(): any {
        return decodeBase64AssetUtf8(this.src);
    }
}

export class FoliumBlock extends AssetBlock {
    public component = markRaw(VFoliumBlock);
    public captionType = "Plot";
}

export class PlotapiBlock extends AssetBlock {
    public component = markRaw(VPlotapiBlock);
    public captionType = "Plot";
}

export class EmbedBlock extends AssetBlock {
    public component = markRaw(VEmbedBlock);

    private _isIFrame?: boolean;
    private html: string;

    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
        this.html = getInnerText(elem);
        this.componentProps = {
            ...this.componentProps,
            html: this.html,
            isIframe: this.isIFrame,
        };
    }

    public get isIFrame(): boolean {
        /**
         * Returns `true` if the embed HTML is an iframe element
         */
        if (typeof this._isIFrame === "undefined") {
            const doc: Document = new DOMParser().parseFromString(
                this.html,
                "text/html"
            );
            const root: HTMLBodyElement | null = doc.documentElement.querySelector(
                "body"
            );
            this._isIFrame =
                !!root &&
                root.childElementCount === 1 &&
                root.children[0].tagName.toLowerCase() === "iframe";
        }
        return this._isIFrame;
    }
}

export class FileBlock extends AssetBlock {
    public component = markRaw(VFileBlock);

    private readonly filename: string;

    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
        const { attributes } = elem;
        this.filename = attributes.filename;
        this.componentProps = {
            ...this.componentProps,
            downloadFile: this.downloadFile.bind(this),
            filename: this.filename,
        };
    }

    protected async downloadFile(): Promise<void> {
        return saveAs(this.src, this.filename);
    }
}

export class MediaBlock extends AssetBlock {
    public component = markRaw(VMediaBlock);

    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
        this.componentProps = {
            ...this.componentProps,
            type: this.type,
            src: this.src,
        };
    }
}

export abstract class PlotAssetBlock extends AssetBlock {
    public captionType = "Plot";
    public responsive: boolean;

    public constructor(elem: Elem, figure: BlockFigure) {
        super(elem, figure);
        const { attributes } = elem;
        this.responsive = JSON.parse(attributes.responsive);
        this.componentProps = {
            ...this.componentProps,
            responsive: this.responsive,
        };
    }
}

export class BokehBlock extends PlotAssetBlock {
    public component = markRaw(VBokehBlock);

    protected fetchLocalAssetData(): string {
        const localAssetData = super.fetchLocalAssetData();
        return JSON.parse(localAssetData);
    }
}

export class VegaBlock extends PlotAssetBlock {
    public component = markRaw(VVegaBlock);

    protected fetchLocalAssetData() {
        const localAssetData = super.fetchLocalAssetData();
        return JSON.parse(localAssetData);
    }
}

export class PlotlyBlock extends PlotAssetBlock {
    public component = markRaw(VPlotlyBlock);

    protected fetchLocalAssetData(): any {
        return JSON.parse(JSON.parse(decodeBase64Asset(this.src)));
    }

    protected async fetchRemoteAssetData(): AssetResource {
        const res = await readGcsTextOrJsonFile<string>(this.src);
        return JSON.parse(res);
    }
}

export class SVGBlock extends PlotAssetBlock {
    public component = markRaw(VSVGBlock);

    protected async fetchRemoteAssetData(): AssetResource {
        return this.src;
    }

    protected fetchLocalAssetData(): string {
        return this.src;
    }
}
