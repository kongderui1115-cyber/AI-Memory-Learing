"""Enforce the owner on both ends of tenant-owned foreign keys."""

from hashlib import sha256
from sqlalchemy import ForeignKeyConstraint, UniqueConstraint


def install_owner_constraints(metadata):
    for table in list(metadata.tables.values()):
        if "user_id" not in table.c:
            continue
        for foreign_key in list(table.foreign_keys):
            target = foreign_key.column
            if foreign_key.parent.name == "user_id" or "user_id" not in target.table.c:
                continue
            columns = ("user_id", target.name)
            suffix = sha256(f"{target.table.name}:{target.name}".encode()).hexdigest()[:8]
            unique_name = f"uq_owner_{target.table.name[:32]}_{suffix}"
            if not any(constraint.name == unique_name for constraint in target.table.constraints):
                target.table.append_constraint(UniqueConstraint(*columns, name=unique_name))
            suffix = sha256(f"{table.name}:{foreign_key.parent.name}".encode()).hexdigest()[:8]
            name = f"fk_owner_{table.name[:32]}_{suffix}"
            table.append_constraint(
                ForeignKeyConstraint(
                    ["user_id", foreign_key.parent.name],
                    [f"{target.table.name}.user_id", f"{target.table.name}.{target.name}"],
                    name=name,
                    deferrable=True,
                    initially="DEFERRED",
                )
            )
