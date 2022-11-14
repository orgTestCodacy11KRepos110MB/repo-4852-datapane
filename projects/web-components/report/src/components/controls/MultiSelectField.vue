<script setup lang="ts">
import { computed, ComputedRef } from "vue";

const emit = defineEmits(["change"]);

const p = defineProps<{
    initialValue: string[];
    helpText?: string;
    name: string;
    required?: boolean;
    choices: string[];
}>();

const validation: ComputedRef = computed(() =>
    p.required ? [["+required"]] : []
);

const onChange = (value: string[]) =>
    void emit("change", { name: p.name, value });
</script>

<template>
    <span data-cy="list-field-choices">
        <form-kit
            type="checkbox"
            :label="p.name"
            :name="p.name"
            :options="p.choices"
            :help="p.helpText"
            :validation="validation"
            :value="p.initialValue"
            @input="onChange"
        />
    </span>
</template>
