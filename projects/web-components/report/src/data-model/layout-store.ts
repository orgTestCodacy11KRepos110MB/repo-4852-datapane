import { defineStore } from "pinia";
import { Block, isSelect, PageLayout } from "./blocks/index";
import { v4 as uuid4 } from "uuid";
import { computed, reactive, ref } from "vue";
import { useRootStore } from "./root-store";

const mkInitialParams = (initialChildren: Block[]): any => {
    const params: any = {};
    for (const c of initialChildren) {
        params[c.componentProps.name] = c.componentProps.initialValue;
    }
    return params;
};

const useActions = (initialChildren: Block[]) => {
    const children = reactive(initialChildren);
    const tabNumber = ref(0);

    function prepend(this: any, ...blocks: Block[]) {
        this.$patch(() => {
            children.unshift(...blocks);
            tabNumber.value += blocks.length;
        });
    }

    function append(this: any, ...blocks: Block[]) {
        this.$patch(() => {
            children.push(...blocks);
            tabNumber.value -= Math.min(blocks.length, 0);
        });
    }

    function swap(this: any, idx: number, ...blocks: Block[]) {
        this.$patch(() => {
            children.splice(idx, 1, ...blocks);
            tabNumber.value += blocks.length - 1;
        });
    }

    function setTab(this: any, n: number) {
        this.tabNumber = n;
    }

    function load(this: any, children: Block[]) {
        this.children = children;
    }

    return { children, tabNumber, prepend, append, swap, setTab, load };
};

export const useLayoutStore = (initialChildren: Block[]) =>
    defineStore(`layout-${uuid4()}`, () => {
        return useActions(initialChildren);
    });

export const useViewStore = (
    initialChildren: Block[],
    initialLayout?: PageLayout
) =>
    defineStore(`view-${uuid4()}`, () => {
        const actions = useActions(initialChildren);
        const { children } = actions;
        const _layout = ref(initialLayout);

        const hasPages = computed(
            () => children.length === 1 && isSelect(children[0])
        );

        const layout = computed(
            () => _layout.value || (children.length > 5 ? "side" : "top")
        );

        return { ...actions, hasPages, layout };
    });

export const useControlStore = (
    initialChildren: Block[],
    target: string,
    method: string // TODO - put target/method in block class?
) =>
    defineStore(`controls-${uuid4()}`, () => {
        const initialParams = mkInitialParams(initialChildren);
        const children = reactive(initialChildren);
        const parameters = reactive(initialParams);
        const rootStore = useRootStore();

        const setField = (k: string, v: any) => {
            parameters[k] = v;
        };

        const update = () => {
            rootStore.update(target, method, parameters);
        };

        return { children, setField, update };
    });
