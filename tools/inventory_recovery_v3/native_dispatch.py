"""Select a stage's original runtime without relabeling historical receipts."""


def modules(plan):
    if "inventory_document_recovery" in plan:
        from tools.inventory_recovery_v3 import execution, runtime
    else:
        from tools.inventory_recovery_v2 import execution, runtime
    return execution, runtime


def validate_plan(plan):
    return modules(plan)[1].validate_plan(plan)
