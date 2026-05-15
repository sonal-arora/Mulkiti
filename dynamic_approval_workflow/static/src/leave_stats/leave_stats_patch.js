import { LeaveStatsComponent } from "@hr_holidays/leave_stats/leave_stats";
import { patch } from "@web/core/utils/patch";
import { formatFloatTime } from "@web/views/fields/formatters";
const { DateTime } = luxon;

patch(LeaveStatsComponent.prototype, {
    arrangeData(leaves) {
        leaves.forEach((leave) => {
            const date_from = DateTime.fromSQL(leave.date_from, { zone: "utc" });
            const date_to = DateTime.fromSQL(leave.date_to, { zone: "utc" });
            const date_from_local = date_from.toLocal();
            const date_to_local = date_to.toLocal();

            leave.date_from = date_from_local.toFormat("dd/MM/yyyy");
            leave.hour_from = date_from_local.toLocaleString(this.hour_format);

            leave.date_to = date_to_local.toFormat("dd/MM/yyyy");
            leave.hour_to = date_to_local.toLocaleString(this.hour_format);
            leave.number_of_hours = formatFloatTime(Number(leave.number_of_hours.toFixed(2)));
            leave.number_of_days = Number(leave.number_of_days.toFixed(2));
        });
        return leaves;
    },
});
