<script setup lang="ts">
import { computed, ComputedRef } from "vue";

const emit = defineEmits(["change"]);

const p = defineProps<{
    helpText?: string;
    name: string;
    required?: boolean;
}>();

const validation: ComputedRef = computed(() =>
    p.required ? [["+required"]] : []
);

// TODO - move to store?
const file2b64 = (file: File): Promise<string | null> =>
    new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => resolve(reader.result as string | null);
        reader.onerror = (error) => reject(error);
    });

const setupListeners = (node: any) => {
    node.on("input", async () => {
        if (node._value.length) {
            emit("change", {
                name: p.name,
                value: await file2b64(node._value[0].file),
            });
        } else {
            emit("change", { name: p.name, value: undefined });
        }
    });
};
</script>

<template>
    <form-kit
        type="file"
        :label="p.name"
        name="parameter_files"
        :help="helpText"
        :validation="validation"
        validation-visibility="live"
        form="params-form"
        data-cy="file-field"
        @node="setupListeners"
    />
</template>
