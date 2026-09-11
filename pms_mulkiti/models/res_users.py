from odoo import _, api, models
from odoo.exceptions import ValidationError


class ResUsers(models.Model):
    _inherit = "res.users"

    # NOTE: Odoo 19 renamed res.users' old "groups_id" field to "group_ids"
    # (explicitly assigned groups) and added "all_group_ids" (group_ids +
    # everything they imply, transitively). A PMS Head only has an explicit
    # row for group_pms_head — group_pms_manager is *implied*, not directly
    # assigned — so membership checks below must use all_group_ids, not
    # group_ids. group_ids is still what a form/onchange can write to.

    @api.onchange("group_ids")
    def _onchange_pms_master_data_editor(self):
        """Live UI feedback (before Save): the moment the "Performance
        Management" selector is set to plain User (or cleared), the
        "Edit Master Data" extra-right checkbox unticks itself and a
        warning banner explains why. This is what makes it "feel" instant
        in the form; _check_pms_master_data_editor_requires_manager below
        is the hard backstop that still blocks Save for any path that
        bypasses this onchange (imports, API calls, the group's own Users
        tab)."""
        editor_group = self.env.ref(
            "pms_mulkiti.group_pms_master_data_editor", raise_if_not_found=False
        )
        if not editor_group or editor_group not in self.all_group_ids:
            return
        manager_group = self.env.ref(
            "pms_mulkiti.group_pms_manager", raise_if_not_found=False
        )
        head_group = self.env.ref(
            "pms_mulkiti.group_pms_head", raise_if_not_found=False
        )
        is_manager_or_head = (
            manager_group and manager_group in self.all_group_ids
        ) or (head_group and head_group in self.all_group_ids)
        if not is_manager_or_head:
            self.group_ids = [(3, editor_group.id)]
            return {
                "warning": {
                    "title": _("PMS right removed"),
                    "message": _(
                        '"%(right)s" was unticked because this user is not a '
                        "PMS Manager or PMS Head. Set their PMS access to "
                        "Manager or Head first, then grant this right.",
                        right=editor_group.name,
                    ),
                }
            }

    @api.constrains("group_ids")
    def _check_pms_master_data_editor_requires_manager(self):
        """The standalone "Edit Master Data" right (pms_mulkiti.group_pms_
        master_data_editor) must never be handed to a plain PMS User — only
        to someone who is already a PMS Manager or PMS Head. Unlike
        implied_ids, this does NOT silently upgrade the user; it blocks the
        save with a clear error instead."""
        editor_group = self.env.ref(
            "pms_mulkiti.group_pms_master_data_editor", raise_if_not_found=False
        )
        if not editor_group:
            return
        manager_group = self.env.ref(
            "pms_mulkiti.group_pms_manager", raise_if_not_found=False
        )
        head_group = self.env.ref(
            "pms_mulkiti.group_pms_head", raise_if_not_found=False
        )
        for user in self:
            if editor_group not in user.all_group_ids:
                continue
            is_manager_or_head = (
                manager_group and manager_group in user.all_group_ids
            ) or (head_group and head_group in user.all_group_ids)
            if not is_manager_or_head:
                raise ValidationError(
                    _(
                        '"%(right)s" can only be granted to a user who is already '
                        "a PMS Manager or PMS Head. Set their PMS access to "
                        "Manager or Head first, then grant this right.",
                        right=editor_group.name,
                    )
                )


class ResGroups(models.Model):
    _inherit = "res.groups"

    @api.constrains("user_ids")
    def _check_pms_master_data_editor_users(self):
        """Mirror of ResUsers._check_pms_master_data_editor_requires_manager
        for the other UI path: assigning users from the group's own "Users"
        tab (Settings > Users & Companies > Groups) instead of from the
        user's form."""
        editor_group = self.env.ref(
            "pms_mulkiti.group_pms_master_data_editor", raise_if_not_found=False
        )
        if not editor_group:
            return
        manager_group = self.env.ref(
            "pms_mulkiti.group_pms_manager", raise_if_not_found=False
        )
        head_group = self.env.ref(
            "pms_mulkiti.group_pms_head", raise_if_not_found=False
        )
        for group in self:
            if group != editor_group:
                continue
            for user in group.user_ids:
                is_manager_or_head = (
                    manager_group and manager_group in user.all_group_ids
                ) or (head_group and head_group in user.all_group_ids)
                if not is_manager_or_head:
                    raise ValidationError(
                        _(
                            '"%(right)s" can only be granted to a user who is '
                            "already a PMS Manager or PMS Head. Set their PMS "
                            "access to Manager or Head first, then grant this "
                            "right.",
                            right=editor_group.name,
                        )
                    )
