from alembic import context

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Run migrations through `nila db upgrade` or `nila serve`.")

context.configure(connection=connection, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
