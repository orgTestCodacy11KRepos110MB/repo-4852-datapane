<script setup lang="ts">
import ReportComponent from "./ReportComponent.vue";
import { ReportProps } from "../data-model/types";
import { computed, onMounted, Ref } from "vue";
import {
    trackLocalReportView,
    trackReportView,
} from "../../../shared/dp-track";
import sanitizeHtml from "sanitize-html";
import { setTheme } from "../theme";
import { EmptyObject, useRootStore } from "../data-model/root-store";
import { storeToRefs } from "pinia";
import { isView, View } from "../data-model/blocks";

const p = defineProps<{
    isOrg: ReportProps["isOrg"];
    mode: ReportProps["mode"];
    htmlHeader?: ReportProps["htmlHeader"];
    report: ReportProps["report"];
}>();

const rootStore = useRootStore();
rootStore.setReportProps(p);

const storeProps = storeToRefs(rootStore);
const { singleBlockEmbed } = storeProps;
const deserializedReport: Ref<View | EmptyObject> = storeProps.report;

onMounted(() => {
    /* View tracking */
    if (window.dpLocal) {
        trackLocalReportView("CLI_REPORT_VIEW");
    } else if (window.dpServed) {
        trackLocalReportView("SERVED_REPORT_VIEW");
    } else {
        const { web_url, id, published, username, num_blocks } = p.report;
        trackReportView({
            id: id,
            web_url: web_url,
            published,
            author_username: username,
            num_blocks,
            is_embed: window.location.href.includes("/embed/"),
        });
    }
});

const htmlHeader = computed(() => {
    // HTML header is taken from the report object, unless overwritten via props
    const dirtyHeader = p.htmlHeader || p.report.output_style_header;
    return p.isOrg
        ? dirtyHeader
        : sanitizeHtml(dirtyHeader, {
              allowedTags: ["style"],
              allowedAttributes: {
                  style: [],
              },
              allowVulnerableTags: true, // Suppress warning for allowing `style`
          });
});

const htmlHeaderRef = (node: any) => {
    /**
     * Set report theme on HTML header node load
     */
    if (node !== null) {
        setTheme(p.report.output_is_light_prose);
    }
};
</script>

<template>
    <div
        v-if="!singleBlockEmbed"
        id="html-header"
        :ref="htmlHeaderRef"
        v-html="htmlHeader"
    />
    <report-component
        v-if="isView(deserializedReport)"
        :is-org="p.isOrg"
        :mode="p.mode"
        :report="deserializedReport"
    />
</template>
