"""Keep upstream identifiers with imported local resources."""
from alembic import op
import sqlalchemy as sa

revision = "0037_gallery_references"
down_revision = "0036_resource_size_bigint"
branch_labels = None
depends_on = None


def upgrade():
    table = op.create_table(
        "gallery_references",
        sa.Column("resource_id", sa.Integer(), sa.ForeignKey("resources.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("kind", sa.String(16), primary_key=True),
        sa.Column("item_id", sa.String(255), primary_key=True),
        sa.Column("variant", sa.String(16), primary_key=True),
        sa.Column("catalog_row", sa.JSON(), nullable=False),
    )
    # Older imports only recorded their source ID when a recipe was submitted.
    conn = op.get_bind()
    tasks = sa.table("tasks", sa.column("params", sa.JSON()), sa.column("user_id"))
    resources = sa.table("resources", sa.column("id"), sa.column("owner_id"))
    query = sa.select(tasks.c.params, tasks.c.user_id).where(
        tasks.c.params["__reference_recipe"]["version"].as_integer() == 1)
    seen = set()
    for params, owner in conn.execute(query):
        choices = params["__reference_recipe"].get("choices") or {}
        if not isinstance(choices, dict):
            continue
        for kind, choice in choices.items():
            if kind not in ("pose", "portrait", "costume") or not isinstance(choice, dict):
                continue
            rid, item = choice.get("id"), choice.get("itemId")
            variant = choice.get("variant", "original")
            if not isinstance(rid, int) or not isinstance(item, str) or not 0 < len(item) <= 255 or variant not in ("original", "depth"):
                continue
            key = (rid, kind, item, variant)
            if key in seen or not conn.scalar(sa.select(resources.c.id).where(resources.c.id == rid, resources.c.owner_id == owner)):
                continue
            seen.add(key)
            name = str(choice.get("name") or item)
            conn.execute(table.insert().values(resource_id=rid, kind=kind, item_id=item, variant=variant,
                         catalog_row={"id": item, "标题": name, "检索": name + " " + item}))


def downgrade():
    op.drop_table("gallery_references")
