export type IReport = {
    document: any;
    web_url: string;
    output_is_light_prose: boolean;
    output_style_header: string;
    num_blocks: number;
    username: string;
    published: boolean;
    id: string;
};

export type ReportProps = {
    isOrg: boolean;
    mode: "VIEW" | "EMBED";
    htmlHeader?: string;
    report: IReport;
};
