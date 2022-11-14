<script setup lang="ts">
import { ref, watch } from "vue";

const emit = defineEmits(["change"]);

const p = defineProps<{
    initialValue?: number;
    helpText?: string;
    name: string;
    required?: boolean;
    min: number;
    max: number;
    step: number;
}>();

const onChange = (value?: string) => {
    emit("change", { name: p.name, value: value ? +value : undefined });
};

// Hold value in state so that it can be shown in input prefix
const inputValue = ref(p.initialValue);

// Cast inputValue to string to match the formkit type
watch(inputValue, () => void onChange(`${inputValue.value}`));
</script>

<template>
    <form-kit
        type="range"
        :help="p.helpText"
        :label="p.name"
        :name="p.name"
        v-model="inputValue"
        :min="p.min"
        :max="p.max"
        :step="p.step"
        data-cy="int-field-bounded"
        outer-class="flex-1"
    >
        <template #prefix>
            <div class="pr-2">{{ inputValue }}</div>
        </template>
    </form-kit>
</template>
