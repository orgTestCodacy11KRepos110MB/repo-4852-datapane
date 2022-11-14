<script setup lang="ts">
import { computed, ComputedRef } from "vue";

const emit = defineEmits(["change"]);

const p = defineProps<{
    initialValue?: string;
    helpText?: string;
    name: string;
    required?: boolean;
}>();

const onChange = (event: any) => {
    const { value } = event.target;
    emit("change", { name: p.name, value });
};

const validation: ComputedRef = computed(() =>
    p.required ? [["+required"]] : []
);
</script>

<template>
    <form-kit
        type="text"
        :help="p.helpText"
        :label="p.name"
        :name="p.name"
        :value="p.initialValue"
        :validation="validation"
        validation-visibility="live"
        @keyup="onChange"
        data-cy="string-field"
        outer-class="flex-1"
    />
</template>
