from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "nila"

APPLICATION_PACKAGES = [
    "agent", "api", "automation", "core", "learning", "memory",
    "observation", "permissions", "tasks",
]


def python_files(package: str) -> list[Path]:
    return sorted((SOURCE / package).rglob("*.py"))


def test_sqlite_specific_sql_stays_inside_storage():
    begin_immediate = []
    full_text = []
    engine_creation = []
    for path in SOURCE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT).as_posix()
        if "BEGIN IMMEDIATE" in text:
            begin_immediate.append(relative)
        if "memory_fts" in text:
            full_text.append(relative)
        if 'URL.create("sqlite"' in text:
            engine_creation.append(relative)
    assert begin_immediate == ["src/nila/storage/dialects.py"]
    assert engine_creation == ["src/nila/storage/dialects.py"]
    assert full_text == [
        "src/nila/storage/migrations/versions/0001_foundation.py",
        "src/nila/storage/repositories/memory.py",
    ]


def test_application_layers_do_not_import_sqlalchemy_or_orm_models():
    offenders = []
    for package in APPLICATION_PACKAGES:
        for path in python_files(package):
            text = path.read_text(encoding="utf-8")
            if (
                "import sqlalchemy" in text
                or "from sqlalchemy" in text
                or "from nila.storage.models" in text
            ):
                offenders.append(path.relative_to(ROOT).as_posix())
    assert offenders == []
