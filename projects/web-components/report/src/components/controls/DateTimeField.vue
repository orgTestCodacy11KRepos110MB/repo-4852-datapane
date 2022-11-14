<script setup lang="ts">
import { computed, ComputedRef } from "vue";

const emit = defineEmits(["change"]);

const p = defineProps<{
    initialValue?: string;
    helpText?: string;
    required?: boolean;
    name: string;
    type: string;
}>();

const onChange = (event: Event) => {
    const target = event.target as HTMLInputElement;
    if (target) {
        emit("change", { name: p.name, value: target.value });
    }
};

const validation: ComputedRef = computed(() =>
    p.required ? [["+required"]] : []
);
</script>

<template>
    <form-kit
        :type="p.type"
        :data-cy="`${p.type}-field`"
        :value="p.initialValue"
        :help="helpText"
        :name="name"
        :label="name"
        :validation="validation"
        validation-visibility="live"
        @change="onChange"
        step="1"
    />
</template>
