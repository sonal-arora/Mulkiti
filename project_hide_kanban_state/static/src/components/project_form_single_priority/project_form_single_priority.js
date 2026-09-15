import { PrioritySwitchField, prioritySwitchField } from "@project/components/project_task_priority_switch_field/project_task_priority_switch_field";
import { registry } from "@web/core/registry";

/**
 * Same widget/behavior as the Form view's priority switch (star rating,
 * including its command-palette entries), but only shows a single star —
 * a Normal <-> High priority toggle — instead of one star per priority
 * level (Low/Medium/High/Urgent). Mirrors project_kanban_single_priority,
 * applied to the Form header instead of the Kanban card. The underlying
 * `priority` field itself is untouched (still 4 levels).
 */
export class ProjectFormSinglePriorityField extends PrioritySwitchField {
    get options() {
        const all = super.options;
        const normal = all[0];
        const high = all.find((option) => option[0] === "2") || all[all.length - 1];
        return [normal, high];
    }
}

export const projectFormSinglePriorityField = {
    ...prioritySwitchField,
    component: ProjectFormSinglePriorityField,
};

registry.category("fields").add("project_form_single_priority", projectFormSinglePriorityField);
