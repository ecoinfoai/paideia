"""retro_mester.forward — US3 forward-contract planning subpackage.

Modules:
- ``baseline``: build per-(segment × chapter) baseline snapshot.
- ``ledger``:   build improvement ledger from covered recommendations.
- ``write``:    write 차년도방향.yaml + ``next_year`` helper.
- ``audit``:    compare prior-year ledger targets against current baseline.
- ``next_items``: propose next-year diagnostic items + write Markdown table.
"""
