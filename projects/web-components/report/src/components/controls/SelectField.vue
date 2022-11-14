<script setup lang="ts">
const emit = defineEmits(["change"]);

const p = defineProps<{
    initialValue?: string;
    helpText?: string;
    name: string;
    required?: boolean;
    choices: string[];
}>();

const onChange = (value: string) => {
    emit("change", { name: p.name, value });
};
</script>

<template>
    <span data-cy="select-field">
        <form-kit
            type="select"
            :label="p.name"
            :name="p.name"
            :options="p.choices"
            :help="p.helpText"
            :value="p.initialValue"
            @input="onChange"
        />
    </span>
</template>
