<script setup lang="ts">
/**
 * Centres block and adds caption below if necessary
 */
import { toRefs } from "vue";
import { BlockFigureProps } from "../../data-model/blocks";
import { useRootStore } from "../../data-model/root-store";
import { storeToRefs } from "pinia";

const p = defineProps<{
    figure: BlockFigureProps;
}>();

const rootStore = useRootStore();
const { singleBlockEmbed } = storeToRefs(rootStore);
const { caption, count, captionType } = toRefs(p.figure);
</script>

<template>
    <div
        :class="[
            'w-full relative flex flex-col justify-center items-center overflow-x-auto',
            { 'h-iframe': singleBlockEmbed },
            { 'py-3 px-1': !singleBlockEmbed },
        ]"
    >
        <slot />
        <div
            v-if="caption"
            class="text-sm text-dp-light-gray italic text-justify"
        >
            <b>{{ captionType }} {{ count }}</b>
            {{ caption }}
        </div>
    </div>
</template>
