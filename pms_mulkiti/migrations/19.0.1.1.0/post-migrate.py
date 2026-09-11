"""Backfill pms.review.cycle for existing PMS data.

Runs once, automatically, when this module is upgraded past 19.0.1.1.0.

Every existing pms.financial.year gets one "Annual" pms.review.cycle
(created if it doesn't already exist), and every existing pms.appraisal /
pms.initialize record that has no review_cycle_id yet gets linked to it.
This is purely additive: it does not touch state, ratings, comments,
approvals or any other business data on existing records.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Cycle = env["pms.review.cycle"]

    financial_years = env["pms.financial.year"].search([])
    for fy in financial_years:
        cycle = Cycle.search([
            ("financial_year_id", "=", fy.id),
            ("period_type", "=", "annual"),
        ], limit=1)
        if not cycle:
            cycle = Cycle.create({
                "name": f"Annual {fy.name}",
                "financial_year_id": fy.id,
                "period_type": "annual",
                "sequence": 1,
                "date_start": fy.date_start,
                "date_end": fy.date_end,
            })
            _logger.info("PMS migration: created Annual review cycle '%s' for Financial Year '%s'.", cycle.name, fy.name)

        appraisals = env["pms.appraisal"].search([
            ("financial_year_id", "=", fy.id),
            ("review_cycle_id", "=", False),
        ])
        if appraisals:
            appraisals.write({"review_cycle_id": cycle.id})
            _logger.info("PMS migration: linked %d pms.appraisal record(s) for '%s' to cycle '%s'.", len(appraisals), fy.name, cycle.name)

        initializations = env["pms.initialize"].search([
            ("financial_year_id", "=", fy.id),
            ("review_cycle_id", "=", False),
        ])
        if initializations:
            initializations.write({"review_cycle_id": cycle.id})
            _logger.info("PMS migration: linked %d pms.initialize record(s) for '%s' to cycle '%s'.", len(initializations), fy.name, cycle.name)
