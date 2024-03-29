<script setup lang="ts">
import { ref, computed, ComputedRef } from "vue";
import { BlockTree, Select } from "../../data-model/blocks";
import MultiSelect from "vue-multiselect";
import "vue-multiselect/dist/dist/vue-multiselect.esm.css";

const p = defineProps<{ select: Select }>();
const tabNumber = ref(0);

const sectionType: ComputedRef<string> = computed(() => {
    const { type, children } = p.select;
    if (type) return type;
    return children.length < 5 ? "tabs" : "dropdown";
});

const labels: ComputedRef<string[]> = computed(() =>
    p.select.children.map(
        (child: BlockTree, idx) => child.label || `Section ${idx + 1}`
    )
);

const tabNumbers: ComputedRef<number[]> = computed(() =>
    labels.value.map((_, idx) => idx)
);

// The subtree which should be rendered by the select block
const currentTree = computed(() => p.select.children[tabNumber.value]);

// Used by `vue-multiselect` to overwrite the default behaviour of displaying tab number only
const multiSelectCustomLabel = (tabNumber: number) => labels.value[tabNumber];
// Used by `vue-multiselect` to set tab number on change
const setTabNumber = (val: number) => (tabNumber.value = val);

const setTabNumberFromEvent = (ev: Event) =>
    void setTabNumber(+(ev.target as HTMLSelectElement).value);
</script>

<template>
    <div class="w-full" data-cy="section-tabs">
        <div :class="['w-full mb-2', { 'sm:hidden': sectionType === 'tabs' }]">
            <select
                v-if="p.select.children.length < 10"
                id="tabs"
                name="tabs"
                class="block mb-1 w-auto focus:ring-indigo-500 focus:border-indigo-500 border-gray-300 rounded-md"
                :value="tabNumber"
                @change="setTabNumberFromEvent"
            >
                <option v-for="(label, idx) in labels" :key="idx" :value="idx">
                    {{ label }}
                </option>
            </select>
            <MultiSelect
                v-else
                v-model="tabNumber"
                :options="tabNumbers"
                :preselect-first="true"
                :clear-on-select="false"
                :allow-empty="false"
                :custom-label="multiSelectCustomLabel"
            />
        </div>
        <div :class="['hidden', { 'sm:block': sectionType === 'tabs' }]">
            <nav class="flex space-x-4 mb-2">
                <a
                    v-for="(child, idx) in p.select.children"
                    role="button"
                    :key="idx"
                    :data-cy="`tab-${idx}`"
                    :class="[
                        'px-3 py-2 font-medium text-sm rounded-md',
                        {
                            'text-dp-accent bg-dp-accent-light':
                                tabNumber === idx,
                            'text-dp-light-gray hover:text-dp-dark-gray':
                                tabNumber !== idx,
                        },
                    ]"
                    @click="() => setTabNumber(idx)"
                >
                    {{ labels[idx] }}
                </a>
            </nav>
        </div>
        <div>
            <slot :tree="currentTree" />
        </div>
    </div>
</template>

<style>
.multiselect__option--highlight {
    background: var(--dp-accent-color);
    color: var(--dp-accent-text);
}

.multiselect__option--selected.multiselect__option--highlight {
    background: white;
    color: black;
}

.multiselect__option--highlight:after {
    display: none;
}

.multiselect__option--highlight.multiselect__option--selected {
    background: var(--dp-accent-color);
    color: var(--dp-accent-text);
}
</style>
