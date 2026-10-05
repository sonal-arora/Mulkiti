def migrate(cr, version):
    """Record rules used to be noupdate, so the new folder-based employee rule
    would never replace the old "public = everyone" rule on upgrade. Release
    them so the security XML (now noupdate="0") updates them."""
    if not version:
        return
    cr.execute("""
        UPDATE ir_model_data
           SET noupdate = false
         WHERE module = 'company_documents'
           AND model = 'ir.rule'
    """)
