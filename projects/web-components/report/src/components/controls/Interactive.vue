<script setup lang="ts">
import { storeToRefs } from "pinia";

const p = defineProps<{ store: any }>();

const { children } = storeToRefs(p.store);

const onChange = (v: any) => {
    p.store.setField(v.name, v.value);
};
</script>

<template>
    <div class="bg-gray-50 p-4 rounded-sm">
        <component
            :is="child.component"
            v-for="child in children"
            v-bind="child.componentProps"
            :key="child.refId"
            @change="onChange"
        />
        <button
            class="flex-initial h-11 mt-1 mx-2 dp-btn dp-btn-primary"
            @click="p.store.update()"
        >
            Go
        </button>
    </div>
</template>
