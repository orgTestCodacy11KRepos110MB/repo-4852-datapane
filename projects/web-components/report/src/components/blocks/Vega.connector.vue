<script setup lang="ts">
import { ref, defineAsyncComponent } from "vue";
import { BlockFigureProps } from "../../data-model/blocks";
import BlockWrapper from "../layout/BlockWrapper.vue";
const VegaBlock = defineAsyncComponent(() => import("./Vega.vue"));

const p = defineProps<{
    fetchAssetData: any;
    responsive: boolean;
    figure: BlockFigureProps;
}>();
const plotJson = ref<any>(null);

(async () => {
    plotJson.value = await p.fetchAssetData();
})();
</script>

<template>
    <block-wrapper :figure="p.figure">
        <vega-block
            v-if="plotJson"
            :plot-json="plotJson"
            :responsive="p.responsive"
        ></vega-block>
    </block-wrapper>
</template>
