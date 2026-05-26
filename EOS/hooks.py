# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """
    Remove auto-copied default salary rules (BASIC, GROSS, NET) from EOS structure.
    Odoo automatically copies these from default_structure when any new structure
    is created — they are irrelevant for Final Settlement payslips.
    """
    struct = env.ref('EOS.hr_payroll_structure_eos_fnf', raise_if_not_found=False)
    if not struct:
        return

    unwanted = struct.rule_ids.filtered(lambda r: r.code in ('BASIC', 'GROSS', 'NET'))
    if unwanted:
        _logger.info('EOS: Removing %d auto-copied default rules from EOS structure: %s',
                     len(unwanted), unwanted.mapped('code'))
        unwanted.unlink()
