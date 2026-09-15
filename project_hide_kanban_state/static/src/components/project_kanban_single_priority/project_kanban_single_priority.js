import { PriorityField, priorityField } from "@web/views/fields/priority/priority_field";
import { registry } from "@web/core/registry";

/**
 * Same widget/behavior as the standard Priority field (star rating), but
 * only shows a single star — a Normal <-> High priority toggle — instead
 * of one star per priority level (Low/Medium/High/Urgent). The underlying
 * `priority` field itself is untouched (still 4 levels); this only limits
 * what's rendered/clickable here, on the Kanban card.
 */
export class ProjectKanbanSinglePriorityField extends PriorityField {
    get options() {
        const all = super.options;
        const normal = all[0];
        const high = all.find((option) => option[0] === "2") || all[all.length - 1];
        return [normal, high];
    }
}

export const projectKanbanSinglePriorityField = {
    ...priorityField,
    component: ProjectKanbanSinglePriorityField,
};

registry.category("fields").add("project_kanban_single_priority", projectKanbanSinglePriorityField);
