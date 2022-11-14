<script setup lang="ts">
import { ref } from "vue";
import BlockWrapper from "../layout/BlockWrapper.vue";
import { BlockFigureProps } from "../../data-model/blocks";
import { useRootStore } from "../../data-model/root-store";
import { storeToRefs } from "pinia";

const p = defineProps<{ fetchAssetData: any; figure: BlockFigureProps }>();
const rootStore = useRootStore();
const { singleBlockEmbed } = storeToRefs(rootStore);
const html = ref<string | null>(null);

(async () => {
    html.value = await p.fetchAssetData();
})();
</script>

<template>
    <block-wrapper :figure="p.figure">
        <x-table-block
            v-if="html"
            :html="html"
            :single-block-embed="singleBlockEmbed"
            class="w-full"
        />
    </block-wrapper>
</template>
