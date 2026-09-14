import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { CheckboxItem } from "@web/core/dropdown/checkbox_item";
import { useService } from "@web/core/utils/hooks";

/**
 * Kanban-card "Stage" selector, styled like the built-in State dot/dropdown
 * (project_task_state_selection), but listing the task's own project Stages
 * instead of the fixed State values. Picking a stage updates stage_id only.
 */
export class ProjectStageKanbanSelection extends Component {
    static template = "project_hide_kanban_state.ProjectStageKanbanSelection";
    static components = { Dropdown, CheckboxItem };
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ stages: [] });
        onWillStart(() => this.loadStages());
    }

    async loadStages() {
        const projectIdValue = this.props.record.data.project_id;
        const projectId = projectIdValue && projectIdValue.id;
        if (!projectId) {
            this.state.stages = [];
            return;
        }
        this.state.stages = await this.orm.searchRead(
            "project.task.type",
            [["project_ids", "in", [projectId]]],
            ["id", "name", "color"],
            { order: "sequence" }
        );
    }

    get currentStage() {
        return this.props.record.data[this.props.name] || null;
    }

    get currentStageColorClass() {
        const current = this.currentStage;
        if (!current) {
            return "o_tag_color_0";
        }
        const match = this.state.stages.find((s) => s.id === current.id);
        return this.colorClass(match ? match.color : 0);
    }

    colorClass(color) {
        return `o_tag_color_${color || 0}`;
    }

    isCurrentStage(stage) {
        return Boolean(this.currentStage && this.currentStage.id === stage.id);
    }

    async selectStage(stage) {
        if (this.isCurrentStage(stage)) {
            return;
        }
        await this.props.record.update(
            { [this.props.name]: { id: stage.id, display_name: stage.name } },
            { save: true }
        );
        // Saving updates the record's data, but the Kanban board only
        // re-groups cards into columns on drag-and-drop (a different code
        // path). Reload the whole model so the card actually moves to its
        // new Stage column immediately, without the user refreshing.
        await this.props.record.model.load();
    }
}

export const projectStageKanbanSelection = {
    component: ProjectStageKanbanSelection,
    supportedTypes: ["many2one"],
    fieldDependencies: [{ name: "project_id", type: "many2one" }],
};

registry.category("fields").add("project_stage_kanban_selection", projectStageKanbanSelection);
