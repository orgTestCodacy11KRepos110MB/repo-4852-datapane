<script setup lang="ts">
const p = defineProps<{
    initialValue: boolean;
    helpText?: string;
    name: string;
}>();

const emit = defineEmits(["change"]);

const onChange = (value: boolean) => {
    emit("change", { name: p.name, value });
};
</script>

<template>
    <form-kit
        type="checkbox"
        :value="p.initialValue"
        :label="p.name"
        :name="p.name"
        :help="p.helpText"
        @input="onChange"
        data-cy="boolean-field"
    />
</template>

<style>
:root {
    --fk-font-weight-option: bold !important;
}
</style>
